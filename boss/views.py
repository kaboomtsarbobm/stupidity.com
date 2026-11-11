import discord

from .manager import BossManager


def hp_bar(current, maximum, width=12):
    if maximum <= 0:
        return ""
    filled = max(0, min(width, round(width * current / maximum)))
    return "█" * filled + "░" * (width - filled)


def flags(ball):
    out = []
    if ball.stunned > 0:
        out.append("stunned")
    if ball.burning > 0:
        out.append("burning")
    if ball.dodging > 0:
        out.append("dodging")
    if ball.protected > 0:
        out.append("protected")
    return f" ({', '.join(out)})" if out else ""


def battle_embed(manager: BossManager, names: dict, text: str, color=None):
    boss = manager.boss
    embed = discord.Embed(
        title=f"{boss.ball} | Round {manager.round}",
        description=text[:1800] if text else None,
        color=color or discord.Color.dark_red(),
    )

    embed.add_field(
        name=f"{boss.ball}: {int(boss.health)}/{int(boss.max_health)} HP",
        value=hp_bar(boss.health, boss.max_health) + flags(boss),
        inline=False,
    )

    minions = [b for b in manager.team_two if b is not boss and b.alive]
    if minions:
        lines = [f"{b.ball} {int(b.health)}/{int(b.max_health)}" for b in minions[:10]]
        embed.add_field(name="Minions", value="\n".join(lines)[:1000], inline=False)

    for user_id in manager.order:
        balls = [b for b in manager.team_one if b.owner_id == user_id]
        lines = []
        for b in balls[:10]:
            if b.alive:
                lines.append(f"{b.ball} {int(b.health)}/{int(b.max_health)}{flags(b)}")
            else:
                lines.append(f"~~{b.ball}~~")
        embed.add_field(
            name=names.get(user_id, str(user_id)),
            value=("\n".join(lines) or "-")[:300],
            inline=True,
        )

    current = manager.current_user()
    if current is not None:
        embed.set_footer(text=f"Turn: {names.get(current, current)}")
    elif manager.awaiting_boss:
        embed.set_footer(text="Boss turn: waiting for the admin to pick the move and attack.")

    return embed


class BallSelect(discord.ui.Select):
    def __init__(self, balls, max_balls=3):
        options = [
            discord.SelectOption(label=ball.ball.country[:100], value=str(ball.id))
            for ball in balls[:25]
        ]

        super().__init__(
            placeholder="Pick the balls you bring to the fight",
            min_values=1,
            max_values=min(max_balls, len(options)),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_balls = self.values

        await interaction.response.edit_message(
            content=f"Selected {len(self.values)} ball(s).",
            view=self.view,
        )

        if self.view.on_complete is not None:
            await self.view.on_complete(interaction, self.view)


class BallSelectView(discord.ui.View):
    def __init__(self, balls, max_balls=3, on_complete=None, allowed_user_id=None):
        super().__init__(timeout=120)
        self.balls = balls
        self.selected_balls = []
        self.on_complete = on_complete
        self.allowed_user_id = allowed_user_id

        self.add_item(BallSelect(balls, max_balls))

    async def interaction_check(self, interaction: discord.Interaction):
        if self.allowed_user_id is not None and interaction.user.id != self.allowed_user_id:
            await interaction.response.send_message("No.", ephemeral=True)
            return False
        return True


class BossAttackerSelect(discord.ui.Select):
    def __init__(self, view):
        self.battle_view = view
        super().__init__(
            placeholder="Choose one of your balls",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="-", value="-1")],
        )
        self.refresh_options()

    def refresh_options(self):
        manager = self.battle_view.manager
        user_id = manager.current_user()
        options = []
        for index, ball in enumerate(manager.team_one):
            if ball.alive and ball.owner_id == user_id:
                ability = ball.ability.ability_name if ball.ability else "no ability"
                label = f"{ball.ball} | HP {int(ball.health)} | ATK {int(ball.attack)} | {ability}"
                options.append(discord.SelectOption(label=label[:100], value=str(index)))
        if options:
            self.options = options[:25]

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        self.battle_view.selected_attacker = self.battle_view.manager.team_one[index]
        await interaction.response.defer()


class BossTargetSelect(discord.ui.Select):
    def __init__(self, view):
        self.battle_view = view
        super().__init__(
            placeholder="Target (default: the boss)",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="-", value="-1")],
        )
        self.refresh_options()

    def refresh_options(self):
        manager = self.battle_view.manager
        options = [
            discord.SelectOption(
                label=f"{ball.ball} | HP {int(ball.health)}/{int(ball.max_health)}"[:100],
                value=str(index),
            )
            for index, ball in enumerate(manager.team_two)
            if ball.alive
        ]
        if options:
            self.options = options[:25]

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        self.battle_view.selected_target = self.battle_view.manager.team_two[index]
        await interaction.response.defer()


class BossBattleView(discord.ui.View):
    def __init__(self, manager: BossManager, names: dict, host_id: int):
        super().__init__(timeout=300)
        self.manager = manager
        self.names = names
        self.host_id = host_id
        self.selected_attacker = None
        self.selected_target = None
        self.message = None

        self.add_item(BossAttackerSelect(self))
        self.add_item(BossTargetSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.manager.current_user():
            await interaction.response.send_message(
                "Not your turn.",
                ephemeral=True,
            )
            return False
        self.message = interaction.message
        return True

    async def on_timeout(self):
        if self.message is not None:
            try:
                await self.message.edit(content="Nobody played for a while, the fight is over.", view=None)
            except discord.HTTPException:
                pass

    def pick_attacker(self, interaction):
        """The selected ball, if it is one of the current player's living balls."""
        ball = self.selected_attacker
        if ball is None or not ball.alive or ball.owner_id != interaction.user.id:
            return None
        return ball

    async def refresh(self, interaction: discord.Interaction, result: str):
        await show_next(self, interaction, result)

    @discord.ui.button(label="Attack", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        attacker = self.pick_attacker(interaction)
        if attacker is None:
            await interaction.response.send_message(
                "Pick one of your balls first.", ephemeral=True
            )
            return

        if not attacker.can_attack():
            await interaction.response.send_message(
                f"{attacker.ball} doesnt attack, pick another ball.", ephemeral=True
            )
            return

        target = self.selected_target
        if target is None or not target.alive:
            target = self.manager.boss

        result = self.manager.player_attack(attacker, target)
        await self.refresh(interaction, result)

    @discord.ui.button(label="Ability", style=discord.ButtonStyle.primary)
    async def ability_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        attacker = self.pick_attacker(interaction)
        if attacker is None:
            await interaction.response.send_message(
                "Pick one of your balls first.", ephemeral=True
            )
            return

        blocked = self.manager.ability_blocked(attacker)
        if blocked:
            await interaction.response.send_message(blocked, ephemeral=True)
            return

        result = self.manager.player_ability(attacker)
        await self.refresh(interaction, result)

    @discord.ui.button(label="Skip turn", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = self.manager.skip_turn(interaction.user.id)
        await self.refresh(interaction, result)


async def show_next(view, interaction: discord.Interaction, result: str):
    """Edits the fight message: ending screen, the admin's controls, or the next player turn."""
    manager = view.manager
    names = view.names

    if len(result) > 1500:
        result = result[:1500] + "\n..."

    outcome = manager.outcome()
    if outcome is not None:
        boss_name = str(manager.boss.ball)
        if outcome == "players":
            ending = f"{boss_name} was defeated!"
            color = discord.Color.green()
        else:
            ending = f"{boss_name} wiped everyone out!"
            color = discord.Color.red()

        embed = battle_embed(manager, names, f"{result}\n\n**{ending}**", color)
        embed.set_footer(text="The fight is over.")
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        view.stop()
        return

    if manager.awaiting_boss:
        next_view = BossControlView(manager, names, view.host_id)
    else:
        next_view = BossBattleView(manager, names, view.host_id)

    next_view.message = interaction.message
    embed = battle_embed(manager, names, result)
    await interaction.response.edit_message(content=None, embed=embed, view=next_view)
    view.stop()


class AttackModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Boss attack this turn")
        self.control = view
        self.attack_input = discord.ui.TextInput(
            label="Attack for this turn",
            placeholder="e.g. 250",
            default=str(int(view.manager.last_attack)) if view.manager.last_attack else None,
            max_length=9,
        )
        self.add_item(self.attack_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            attack = float(self.attack_input.value.replace(",", "."))
        except ValueError:
            attack = -1

        if attack < 0:
            await interaction.response.send_message(
                "The attack has to be a number, 0 or more.", ephemeral=True
            )
            return

        manager = self.control.manager
        if not manager.awaiting_boss:
            await interaction.response.send_message("The boss already moved.", ephemeral=True)
            return

        result = manager.boss_turn(attack=attack, move=self.control.selected_move)
        await show_next(self.control, interaction, result)


class BossMoveSelect(discord.ui.Select):
    def __init__(self, view):
        self.control = view
        options = [
            discord.SelectOption(
                label="Basic attack",
                value="-1",
                description="Hit a random player ball.",
                default=True,
            )
        ]
        for index, move in enumerate(view.manager.moves):
            if view.manager.move_available(move):
                options.append(
                    discord.SelectOption(label=move.ability_name[:100], value=str(index))
                )

        super().__init__(
            placeholder="Choose the boss move",
            min_values=1,
            max_values=1,
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        self.control.selected_move = (
            self.control.manager.moves[index] if index >= 0 else None
        )
        for option in self.options:
            option.default = option.value == self.values[0]
        await interaction.response.edit_message(view=self.control)


class BossControlView(discord.ui.View):
    """Manual mode: the admin picks the boss move and types the attack."""

    def __init__(self, manager: BossManager, names: dict, host_id: int):
        super().__init__(timeout=600)
        self.manager = manager
        self.names = names
        self.host_id = host_id
        self.selected_move = None
        self.message = None

        self.add_item(BossMoveSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.host_id:
            await interaction.response.send_message(
                "Only the admin running the boss can do this.", ephemeral=True
            )
            return False
        self.message = interaction.message
        return True

    async def on_timeout(self):
        if self.message is not None:
            try:
                await self.message.edit(content="The admin took too long, the fight is over.", view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Set attack and go", style=discord.ButtonStyle.danger)
    async def go_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AttackModal(self))
