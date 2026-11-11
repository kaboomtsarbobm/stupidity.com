from types import SimpleNamespace
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .views import BallSelectView, BossBattleView, battle_embed
from .manager import BossManager

HARD_MAX_PLAYERS = 8


async def get_player_balls(discord_id):
    from bd_models.models import BallInstance

    balls = []
    async for ball in BallInstance.objects.filter(
        player__discord_id=discord_id
    ).select_related("ball"):
        balls.append(ball)
    return balls


async def get_settings():
    from boss.models import BossSettings

    settings, created = await BossSettings.objects.aget_or_create(pk=1)
    return settings


async def load_abilities(ball_ids):
    """BattleAbility rows (battle package) for these ball ids, if that package is installed."""
    try:
        from battle.models import BattleAbility
    except Exception:
        return {}

    abilities = {}
    try:
        queryset = BattleAbility.objects.filter(ball_id__in=set(ball_ids), enabled=True)
        async for ability in queryset.prefetch_related("restricted_targets"):
            ability.companion_ids = {b.pk for b in ability.restricted_targets.all()}
            abilities[ability.ball_id] = ability
    except Exception:
        return {}
    return abilities


async def find_ball(text):
    from bd_models.models import Ball

    text = text.strip()
    if text.isdigit():
        found = await Ball.objects.filter(pk=int(text)).afirst()
        if found:
            return found
    return await Ball.objects.filter(country__iexact=text).afirst()


class BossLobby:
    def __init__(self, host, cfg, settings):
        self.host = host
        self.cfg = cfg
        self.settings = settings
        self.max_players = min(settings.max_players, HARD_MAX_PLAYERS)
        self.players = {}  # user id -> [BallInstance]
        self.names = {}
        self.started = False
        self.message = None

    def embed(self):
        cfg = self.cfg
        if cfg.mode == "manual":
            mode = f"Manual: {self.host.display_name} picks the moves and the attack every turn"
        else:
            mode = f"Random moves, attack rolled each turn between {cfg.attack_min} and {cfg.attack_max}"

        embed = discord.Embed(
            title=f"Boss fight: {cfg.name}",
            description=f"HP {cfg.health:,}\n{mode}",
            color=discord.Color.dark_red(),
        )
        lines = [
            f"{self.names[user_id]}: {', '.join(str(b.ball) for b in balls)}"
            for user_id, balls in self.players.items()
        ]
        embed.add_field(
            name=f"Players ({len(self.players)}/{self.max_players})",
            value="\n".join(lines)[:1000] or "Nobody yet. Press Join.",
            inline=False,
        )
        embed.set_footer(text=f"{self.host.display_name} presses Start when everyone is in.")
        return embed

    async def selected(self, interaction, view):
        ids = {str(i) for i in view.selected_balls}
        chosen = [b for b in view.balls if str(b.id) in ids]
        if not chosen:
            return

        self.players[interaction.user.id] = chosen
        self.names[interaction.user.id] = interaction.user.display_name

        if self.message is not None and not self.started:
            await self.message.edit(embed=self.embed())


class LobbyView(discord.ui.View):
    def __init__(self, lobby: BossLobby):
        super().__init__(timeout=300)
        self.lobby = lobby

    async def on_timeout(self):
        if self.lobby.message is not None and not self.lobby.started:
            try:
                await self.lobby.message.edit(content="The lobby timed out.", embed=None, view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Join / change balls", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.lobby
        user = interaction.user

        if user.id not in lobby.players and len(lobby.players) >= lobby.max_players:
            await interaction.response.send_message("The lobby is full.", ephemeral=True)
            return

        balls = await get_player_balls(user.id)
        if not balls:
            await interaction.response.send_message("NO COLLECTED BALLS?", ephemeral=True)
            return

        view = BallSelectView(
            balls,
            max_balls=lobby.settings.max_balls_per_player,
            on_complete=lobby.selected,
            allowed_user_id=user.id,
        )
        await interaction.response.send_message(
            "Pick the balls you bring.", view=view, ephemeral=True
        )

    @discord.ui.button(label="Start", style=discord.ButtonStyle.danger)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.lobby

        if interaction.user.id != lobby.host.id:
            await interaction.response.send_message("Only the admin who opened it can start.", ephemeral=True)
            return

        if not lobby.players or lobby.started:
            await interaction.response.send_message("Nobody has joined yet.", ephemeral=True)
            return

        lobby.started = True

        from boss.models import BossMove

        moves = []
        async for move in BossMove.objects.filter(ball_id=lobby.cfg.ball_id, enabled=True):
            move.companion_ids = set()
            moves.append(move)

        ball_ids = [ball.ball_id for balls in lobby.players.values() for ball in balls]
        abilities = await load_abilities(ball_ids)

        manager = BossManager(
            lobby.cfg,
            moves,
            list(lobby.players.items()),
            abilities,
        )
        battle_view = BossBattleView(manager, lobby.names, lobby.host.id)
        battle_view.message = interaction.message

        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=battle_embed(manager, lobby.names, f"{lobby.cfg.name} appeared with {lobby.cfg.health:,} HP!"),
            view=battle_view,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.lobby.host.id:
            await interaction.response.send_message("Only the admin who opened it can cancel.", ephemeral=True)
            return

        self.lobby.started = True
        self.stop()
        await interaction.response.edit_message(content="Boss fight cancelled.", embed=None, view=None)


class BossCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def is_admin(self, interaction: discord.Interaction):
        permissions = getattr(interaction.user, "guild_permissions", None)
        if permissions is not None and permissions.administrator:
            return True
        try:
            return await self.bot.is_owner(interaction.user)
        except Exception:
            return False

    @app_commands.command(name="boss", description="Start a boss fight (admins only)")
    @app_commands.describe(
        ball="The ball that is the boss",
        health="The boss health for this fight (its own stats are not used)",
        mode="Random: the bot picks the moves. Manual: you pick the moves and the attack every turn",
        attack_min="Random mode: lowest attack per turn (default from the admin settings)",
        attack_max="Random mode: highest attack per turn (default from the admin settings)",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Random moves", value="random"),
            app_commands.Choice(name="Manual (admin picks the moves)", value="manual"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def boss(
        self,
        interaction: discord.Interaction,
        ball: str,
        health: app_commands.Range[int, 1, 1_000_000_000],
        mode: app_commands.Choice[str],
        attack_min: Optional[app_commands.Range[int, 0, 1_000_000_000]] = None,
        attack_max: Optional[app_commands.Range[int, 0, 1_000_000_000]] = None,
    ):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return

        boss_ball = await find_ball(ball)
        if boss_ball is None:
            await interaction.response.send_message(
                "I cant find that ball, pick one from the list.", ephemeral=True
            )
            return

        settings = await get_settings()
        low = settings.attack_min if attack_min is None else attack_min
        high = settings.attack_max if attack_max is None else attack_max
        low, high = sorted((low, high))

        abilities = await load_abilities([boss_ball.pk])

        cfg = SimpleNamespace(
            name=boss_ball.country,
            ball_id=boss_ball.pk,
            health=health,
            mode=mode.value,
            attack_min=low,
            attack_max=high,
            move_chance=settings.move_chance,
            ability=abilities.get(boss_ball.pk),
        )

        lobby = BossLobby(interaction.user, cfg, settings)
        view = LobbyView(lobby)

        await interaction.response.send_message(embed=lobby.embed(), view=view)
        lobby.message = await interaction.original_response()

    @boss.autocomplete("ball")
    async def ball_autocomplete(self, interaction: discord.Interaction, current: str):
        from bd_models.models import Ball

        choices = []
        async for ball in Ball.objects.filter(country__icontains=current).order_by("country")[:25]:
            choices.append(app_commands.Choice(name=ball.country[:100], value=str(ball.pk)))
        return choices


async def setup(bot):
    await bot.add_cog(BossCog(bot))
