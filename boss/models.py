from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from bd_models.models import Ball

# only active types make sense as boss moves
MOVE_TYPES = [
    ("damage", "flat damage (0 = the boss attack)"),
    ("attack_add", "attack increase"),
    ("attack_multiply", "attack multiplied"),
    ("timed_boost", "attack multiplied for a few turns"),
    ("heal", "heal"),
    ("heal_lost", "heal a part of the lost health"),
    ("paralyze", "stun"),
    ("burn", "burn"),
    ("instant_kill", "instant kill"),
    ("dodge", "dodge"),
    ("protect", "protect (half damage)"),
    ("max_health", "max health plus"),
    ("summon", "summon minions"),
    ("clone", "copy a ball with scaled stats"),
]

MOVE_TARGETS = [
    ("other_team", "The players"),
    ("self", "The boss itself"),
    ("own_team", "The boss side (boss + minions)"),
    ("both_teams", "Everyone"),
]


class BossSettings(models.Model):
    max_players = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(1), MaxValueValidator(8)],
        help_text="Lobbies hold 8 players at most.",
    )
    max_balls_per_player = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    attack_min = models.PositiveIntegerField(
        default=100, help_text="Random mode: lowest attack the boss can roll each turn."
    )
    attack_max = models.PositiveIntegerField(
        default=400, help_text="Random mode: highest attack the boss can roll each turn."
    )
    move_chance = models.FloatField(
        default=40, help_text="Random mode: percent chance per boss turn to use a move instead of a basic attack."
    )

    def __str__(self):
        return "Boss settings"


class BossMove(models.Model):
    """A move of a boss ball. The boss itself is just a ball an admin picks with /boss."""

    ball = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="boss_moves")
    enabled = models.BooleanField(default=True)

    ability_name = models.CharField(max_length=100, default="Move")
    ability_type = models.CharField(max_length=30, choices=MOVE_TYPES, default="damage")
    ability_message = models.TextField(default="{ball} used {ability} on {opponent}!")
    effect_target = models.CharField(max_length=20, choices=MOVE_TARGETS, default="other_team")

    value = models.FloatField(default=100)
    effect_duration = models.PositiveIntegerField(default=1)
    target_count = models.PositiveIntegerField(default=1, help_text="0 = everyone.")
    stun_enabled = models.BooleanField(default=False)
    stun_duration = models.PositiveIntegerField(default=1)
    chance = models.FloatField(default=100)

    cooldown_turns = models.PositiveIntegerField(default=0)
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = unlimited.")
    start_delay = models.PositiveIntegerField(default=0)

    hp_below_percent = models.FloatField(
        default=100, help_text="Random mode only: used only while the boss health is at or below this percent (phases)."
    )
    weight = models.PositiveIntegerField(default=1, help_text="Random mode only: higher = picked more often.")

    summon_name = models.CharField(max_length=100, blank=True, default="Minion")
    summon_attack = models.FloatField(default=30)
    summon_health = models.FloatField(default=50)

    def __str__(self):
        return f"{self.ball.country} - {self.ability_name}"
