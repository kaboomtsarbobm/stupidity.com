import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='BossSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('max_players', models.PositiveSmallIntegerField(default=4, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)])),
                ('max_balls_per_player', models.PositiveSmallIntegerField(default=3, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)])),
            ],
        ),
        migrations.CreateModel(
            name='Boss',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True, default='')),
                ('enabled', models.BooleanField(default=True)),
                ('attack', models.FloatField(default=300)),
                ('health', models.FloatField(default=20000)),
                ('attacks_per_turn', models.PositiveIntegerField(default=1, help_text='Basic attacks the boss does on its turn when it doesnt use a move.')),
                ('move_chance', models.FloatField(default=40, help_text='Percent chance per boss turn to use a move instead of attacking.')),
                ('enrage_after_round', models.PositiveIntegerField(default=0, help_text='After this many rounds the boss gets stronger. 0 = never.')),
                ('enrage_multiplier', models.FloatField(default=1.5)),
                ('turn_limit', models.PositiveIntegerField(default=0, help_text='Rounds before the boss wins by default. 0 = no limit.')),
                ('intro_message', models.TextField(default='{boss} appeared!')),
                ('win_message', models.TextField(default='{boss} was defeated!')),
                ('lose_message', models.TextField(default='{boss} wiped everyone out!')),
            ],
        ),
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
                ('hp_below_percent', models.FloatField(default=100, help_text='Only used while the boss health is at or below this percent (phases).')),
                ('weight', models.PositiveIntegerField(default=1, help_text='Higher = picked more often.')),
                ('summon_name', models.CharField(blank=True, default='Minion', max_length=100)),
                ('summon_attack', models.FloatField(default=30)),
                ('summon_health', models.FloatField(default=50)),
                ('boss', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moves', to='boss.boss')),
            ],
        ),
    ]
