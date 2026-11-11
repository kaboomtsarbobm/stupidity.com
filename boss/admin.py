from django.contrib import admin

from .models import BossMove, BossSettings


@admin.register(BossMove)
class BossMoveAdmin(admin.ModelAdmin):
    """Moves of a boss ball. The boss itself is picked with /boss, any ball can be one."""

    list_display = (
        "ball", "ability_name", "ability_type", "effect_target", "value",
        "cooldown_turns", "max_uses", "enabled",
    )
    list_editable = ("enabled",)
    list_filter = ("enabled", "ability_type", "effect_target")
    search_fields = ("ball__country", "ability_name")
    raw_id_fields = ("ball",)

    fieldsets = (
        (
            "Basics",
            {
                "fields": ("ball", "enabled", "ability_name"),
                "description": (
                    "The ball is the boss this move belongs to. A ball can have as many moves as you like. "
                    "The ball's own ability from the battle package is used automatically, it is not set here."
                ),
            },
        ),
        (
            "What it does",
            {
                "fields": ("ability_type", "effect_target", "value", "target_count"),
                "description": (
                    "Value depends on the type: damage dealt (0 = the boss attack of that turn), "
                    "attack change, multiplier, health healed... Target count 0 = everyone."
                ),
            },
        ),
        (
            "Limits",
            {
                "fields": ("cooldown_turns", "max_uses", "start_delay", "chance"),
                "description": (
                    "Cooldown and start delay count boss turns. Chance is in percent. "
                    "Max uses 0 = unlimited. These apply in both modes."
                ),
            },
        ),
        (
            "Random mode only",
            {
                "fields": ("hp_below_percent", "weight"),
                "description": (
                    "Phases: the move is only picked while the boss health is at or below the percent "
                    "(100 = always). Weight = how often it is picked. In manual mode the admin picks."
                ),
            },
        ),
        (
            "Extra details",
            {
                "classes": ("collapse",),
                "fields": (
                    "ability_message", "effect_duration", "stun_enabled", "stun_duration",
                    "summon_name", "summon_attack", "summon_health",
                ),
                "description": "Message can use {ball}, {ability} and {opponent}. The summon fields are for summon moves.",
            },
        ),
    )


@admin.register(BossSettings)
class BossSettingsAdmin(admin.ModelAdmin):
    list_display = ("max_players", "max_balls_per_player", "attack_min", "attack_max", "move_chance")
