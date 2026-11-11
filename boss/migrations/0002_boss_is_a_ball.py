import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def raise_lobby_size(apps, schema_editor):
    BossSettings = apps.get_model("boss", "BossSettings")
    BossSettings.objects.filter(max_players=4).update(max_players=8)


class Migration(migrations.Migration):

    dependencies = [
        ('boss', '0001_initial'),
        ('bd_models', '0019_guildconfig_tips_enabled'),
    ]

    operations = [
        migrations.DeleteModel(name='BossMove'),
        migrations.DeleteModel(name='Boss'),
        migrations.AlterField(
            model_name='bosssettings',
            name='max_players',
            field=models.PositiveSmallIntegerField(default=8, help_text='Lobbies hold 8 players at most.', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(8)]),
        ),
        migrations.AddField(
            model_name='bosssettings',
            name='attack_min',
            field=models.PositiveIntegerField(default=100, help_text='Random mode: lowest attack the boss can roll each turn.'),
        ),
        migrations.AddField(
            model_name='bosssettings',
            name='attack_max',
            field=models.PositiveIntegerField(default=400, help_text='Random mode: highest attack the boss can roll each turn.'),
        ),
        migrations.AddField(
            model_name='bosssettings',
            name='move_chance',
            field=models.FloatField(default=40, help_text='Random mode: percent chance per boss turn to use a move instead of a basic attack.'),
        ),
        migrations.RunPython(raise_lobby_size, migrations.RunPython.noop),
        migrations.CreateModel(
            name='BossMove',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=True)),
                ('ability_name', models.CharField(default='Move', max_length=100)),
                ('ability_type', models.CharField(choices=[('damage', 'flat damage (0 = the boss attack)'), ('attack_add', 'attack increase'), ('attack_multiply', 'attack multiplied'), ('timed_boost', 'attack multiplied for a few turns'), ('heal', 'heal'), ('heal_lost', 'heal a part of the lost health'), ('paralyze', 'stun'), ('burn', 'burn'), ('instant_kill', 'instant kill'), ('dodge', 'dodge'), ('protect', 'protect (half damage)'), ('max_health', 'max health plus'), ('summon', 'summon minions'), ('clone', 'copy a ball with scaled stats')], default='damage', max_length=30)),
                ('ability_message', models.TextField(default='{ball} used {ability} on {opponent}!')),
                ('effect_target', models.CharField(choices=[('other_team', 'The players'), ('self', 'The boss itself'), ('own_team', 'The boss side (boss + minions)'), ('both_teams', 'Everyone')], default='other_team', max_length=20)),
                ('value', models.FloatField(default=100)),
                ('effect_duration', models.PositiveIntegerField(default=1)),
                ('target_count', models.PositiveIntegerField(default=1, help_text='0 = everyone.')),
                ('stun_enabled', models.BooleanField(default=False)),
                ('stun_duration', models.PositiveIntegerField(default=1)),
                ('chance', models.FloatField(default=100)),
                ('cooldown_turns', models.PositiveIntegerField(default=0)),
                ('max_uses', models.PositiveIntegerField(default=0, help_text='0 = unlimited.')),
                ('start_delay', models.PositiveIntegerField(default=0)),
                ('hp_below_percent', models.FloatField(default=100, help_text='Random mode only: used only while the boss health is at or below this percent (phases).')),
                ('weight', models.PositiveIntegerField(default=1, help_text='Random mode only: higher = picked more often.')),
                ('summon_name', models.CharField(blank=True, default='Minion', max_length=100)),
                ('summon_attack', models.FloatField(default=30)),
                ('summon_health', models.FloatField(default=50)),
                ('ball', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='boss_moves', to='bd_models.ball')),
            ],
        ),
    ]
