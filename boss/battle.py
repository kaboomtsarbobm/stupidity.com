import random

PASSIVE_TYPES = {
    "self_resurrect",
    "aura_health",
    "pair_boost",
    "round_growth",
    "death_growth",
    "damage_reduction",
    "death_revenge",
    "death_snipe",
    "no_attack",
    "bonus_vs",
    "kill_bonus",
    "respawn_weaker",
    "tank",
    "ally_assist",
}

MAX_TEAM_SIZE = 25


class SummonedBall:
    """Stand-in for a BallInstance so summons and clones can fight."""

    ball_id = None

    def __init__(self, name, attack, health):
        self.name = name
        self.attack = attack
        self.health = health

    def __str__(self):
        return self.name


class BattleBall:
    def __init__(self, ball, attack=None, health=None, ability=None):
        self.ball = ball
        self.ball_id = getattr(ball, "ball_id", None)
        self.ability = ability
        self.companion_ids = set(getattr(ability, "companion_ids", None) or ())
        self.killed_by = None
        self.death_done = False
        self.seen_deaths = 0
        self.applied = {}
        self.owner_id = None
        self.timed = []
        self.holding = []
        self.respawned = False
        self.last_stand_used = False
        self.last_stand_pending = False

        instance_attack = getattr(ball, "attack", None)
        instance_health = getattr(ball, "health", None)

        base_attack = getattr(getattr(ball, "ball", None), "attack", 10)
        base_health = getattr(getattr(ball, "ball", None), "health", 100)

        self.attack = float(
            instance_attack if instance_attack is not None else base_attack
        )
        self.health = float(
            instance_health if instance_health is not None else base_health
        )
        self.max_health = self.health
        self.alive = self.health > 0
        # protected / dodging are turn counters now (0 = off), so they wear off
        self.protected = 0
        self.dodging = 0
        self.stunned = 0
        self.burning = 0
        self.burn_damage = 30
        self.resurrections = 0

        # ability bookkeeping
        self.uses = 0
        start_delay = getattr(ability, "start_delay", 0) if ability else 0
        self.cooldown = start_delay
        self.just_resurrected = False

    def passive_type(self):
        ability = self.ability
        if ability is None or not getattr(ability, "enabled", True):
            return None
        return ability.ability_type

    def can_attack(self):
        return self.passive_type() != "no_attack"

    def take_damage(self, damage, source=None):
        if not self.alive or self.dodging > 0:
            return 0

        if self.passive_type() == "damage_reduction":
            damage = damage * self.ability.value

        if self.protected > 0:
            damage = damage / 2

        damage = max(0, damage)
        self.health = max(0, self.health - damage)

        if damage > 0:
            self.release_holds()

        if self.health <= 0 and self.passive_type() == "tank" and not self.last_stand_used:
            # survives on 1 health, the manager triggers the last stand
            self.health = 1
            self.last_stand_used = True
            self.last_stand_pending = True

        if self.health <= 0:
            self.alive = False
            self.killed_by = source
            self.passive_resurrect()

        return damage

    def release_holds(self):
        for held in self.holding:
            held.stunned = 0
        self.holding = []

    def passive_resurrect(self):
        ability = self.ability
        if ability is None or not getattr(ability, "enabled", True):
            return

        if ability.ability_type == "self_resurrect":
            if self.resurrect_if_allowed(ability):
                self.just_resurrected = True

        elif ability.ability_type == "respawn_weaker" and not self.respawned:
            self.respawned = True
            factor = ability.value if ability.value > 0 else 0.5
            self.attack *= factor
            self.max_health *= factor
            if self.revive(self.max_health):
                self.just_resurrected = True

    def heal(self, amount):
        if not self.alive:
            return

        self.health = min(self.max_health, self.health + amount)

    def revive(self, health=25):
        if self.alive:
            return False

        self.alive = True
        self.health = min(self.max_health, health)
        self.dodging = 0
        self.protected = 0
        self.stunned = 0
        self.burning = 0
        return True

    def attack_target(self, target):
        if not self.alive:
            return "Your beating a dead horse brother."

        if self.stunned > 0:
            self.stunned -= 1
            return f"{self.ball} is stunned and cannot attack!"

        if not self.can_attack():
            return f"{self.ball} doesnt attack."

        power = self.attack
        if self.passive_type() == "bonus_vs" and target.ball_id in self.companion_ids:
            power *= self.ability.value

        damage = target.take_damage(power, source=self)

        if damage == 0:
            return f"{target.ball} avoided the attack!"

        if target.just_resurrected:
            target.just_resurrected = False
            return (
                f"{self.ball} dealt {damage} damage to {target.ball}!\n"
                f"{target.ball} was resurrected."
            )

        if not target.alive:
            text = f"{self.ball} dealt {damage} damage and defeated {target.ball}!"
            if self.passive_type() == "kill_bonus":
                self.attack += self.ability.value
                text += f"\n{self.ball} got stronger from the kill."
            return text

        return f"{self.ball} dealt {damage} damage to {target.ball}!"

    def pick_targets(self, ability, own_team, other_team):
        if ability.effect_target == "self":
            return [self]

        if ability.effect_target == "own_team":
            pool = list(own_team)
        elif ability.effect_target == "other_team":
            pool = list(other_team)
        elif ability.effect_target == "both_teams":
            pool = list(own_team) + list(other_team)
        else:
            return [self]

        if ability.ability_type == "resurrect":
            pool = [t for t in pool if not t.alive]
        else:
            pool = [t for t in pool if t.alive]

        # a partner list on a normal ability means "can only hit these balls"
        if self.companion_ids and ability.ability_type not in PASSIVE_TYPES:
            pool = [t for t in pool if t.ball_id in self.companion_ids]

        if ability.ability_type in ("copy_stats", "swap_stats"):
            pool = [t for t in pool if t is not self]
            if not pool:
                return []
            if ability.effect_target == "other_team":
                return [max(pool, key=lambda b: b.attack)]
            return [random.choice(pool)]

        count = ability.target_count
        if count and len(pool) > count:
            pool = random.sample(pool, count)

        return pool

    def use_ability(self, ability, own_team, other_team):
        if not self.alive:
            return "Your beating a dead horse brother."

        stun_rider_only = ability.ability_type == "damage" and ability.stun_enabled
        chance = getattr(ability, "chance", 100)
        if chance < 100 and not stun_rider_only:
            if random.random() * 100 >= chance:
                return f"{self.ball} used {ability.ability_name} but it failed!"

        targets = self.pick_targets(ability, own_team, other_team)

        header = self.format_ability_message(ability, targets)
        messages = [header] if header else []

        for target in targets:
            # Resurrection is allowed to target dead balls.
            if ability.ability_type == "resurrect":
                if target.resurrect_if_allowed(ability):
                    messages.append(f"{target.ball} was resurrected.")
                continue

            if ability.ability_type == "self_resurrect":
                continue

            if not target.alive:
                continue

            if ability.ability_type == "attack_add":
                target.attack += ability.value
                messages.append(f"{target.ball} i think increased its attack.")

            elif ability.ability_type == "attack_multiply":
                target.attack *= ability.value
                messages.append(f"{target.ball} multiplied their attack somehow.")

            elif ability.ability_type == "heal":
                target.heal(ability.value)
                messages.append(f"{target.ball} healed themself.")

            elif ability.ability_type == "paralyze":
                target.stunned = ability.stun_duration
                messages.append(f"{target.ball} was paralyzed in an idiotic way.")

            elif ability.ability_type == "burn":
                target.burning = ability.effect_duration
                target.burn_damage = ability.value
                messages.append(f"{target.ball} got 3rd degree burns.")

            elif ability.ability_type == "instant_kill":
                target.health = 0
                target.alive = False
                messages.append(f"{target.ball} can now kill everyone in one hit!")

            elif ability.ability_type == "backflip":
                target.dodging = ability.effect_duration
                messages.append(f"{target.ball} did a awesome backflip that did nothing.")

            elif ability.ability_type == "dodge":
                target.dodging = ability.effect_duration
                messages.append(f"{target.ball} dodged the attack/ability.")

            elif ability.ability_type == "max_health":
                target.max_health += ability.value
                target.health += ability.value
                messages.append(f"{target.ball} gained more health.")

            elif ability.ability_type == "protect":
                target.protected = ability.effect_duration
                messages.append(f"{target.ball} somehow protected themself.")

            elif ability.ability_type == "kill_yourself":
                target.health = 0
                target.alive = False
                messages.append(f"{target.ball} killed themself.!")

            elif ability.ability_type == "damage":
                dealt = target.take_damage(ability.value or self.attack, source=self)
                if dealt == 0:
                    messages.append(f"{target.ball} avoided the ability!")
                elif target.just_resurrected:
                    target.just_resurrected = False
                    messages.append(f"{target.ball} took {dealt:g} damage and was resurrected.")
                elif not target.alive:
                    messages.append(f"{target.ball} took {dealt:g} damage and died.")
                else:
                    messages.append(f"{target.ball} took {dealt:g} damage.")

                if dealt and target.alive and ability.stun_enabled:
                    if random.random() * 100 < chance:
                        target.stunned = ability.stun_duration
                        messages.append(f"{target.ball} was stunned for {ability.stun_duration} turn(s).")

            elif ability.ability_type == "timed_boost":
                factor = ability.value if ability.value > 0 else 1
                target.attack *= factor
                # ticks down when the target's team acts, own team gets +1 because
                # the tick at the end of this very action doesnt count
                turns = ability.effect_duration + (1 if target in own_team else 0)
                target.timed.append([factor, turns])
                messages.append(f"{target.ball}'s attack was changed for {ability.effect_duration} turn(s).")

            elif ability.ability_type == "stun_until_hit":
                target.stunned = 999
                self.holding.append(target)
                messages.append(f"{target.ball} is stunned until {self.ball} gets hit.")

            elif ability.ability_type == "heal_lost":
                before = target.health
                target.heal((target.max_health - target.health) * ability.value)
                messages.append(f"{target.ball} regained {target.health - before:g} health.")

            elif ability.ability_type == "self_destruct_damage":
                dealt = target.take_damage(self.max_health * ability.value, source=self)
                if dealt:
                    messages.append(f"{target.ball} took {dealt:g} damage from the blast.")
                else:
                    messages.append(f"{target.ball} avoided the blast!")

            elif ability.ability_type == "summon":
                if len(own_team) >= MAX_TEAM_SIZE:
                    messages.append("There is no room for more.")
                    continue
                name = getattr(ability, "summon_name", "") or "Summon"
                minion = BattleBall(
                    SummonedBall(name, ability.summon_attack, ability.summon_health)
                )
                own_team.append(minion)
                messages.append(f"{name} joined {self.ball}'s team.")

            elif ability.ability_type == "clone":
                if len(own_team) >= MAX_TEAM_SIZE:
                    messages.append("There is no room for more.")
                    continue
                factor = ability.value if ability.value > 0 else 1
                copy = BattleBall(
                    SummonedBall(
                        f"{target.ball} (copy)",
                        target.attack * factor,
                        target.max_health * factor,
                    )
                )
                own_team.append(copy)
                messages.append(f"{target.ball} got a copy with {factor:g}x stats.")

            elif ability.ability_type == "copy_stats":
                self.attack = target.attack
                self.max_health = target.max_health
                self.health = target.health
                messages.append(f"{self.ball} copied the stats of {target.ball}.")

            elif ability.ability_type == "swap_stats":
                self.attack, target.attack = target.attack, self.attack
                self.health, target.health = target.health, self.health
                self.max_health, target.max_health = target.max_health, self.max_health
                messages.append(f"{self.ball} swapped stats with {target.ball}.")

        if ability.ability_type == "self_resurrect":
            if self.resurrect_if_allowed(ability):
                messages.append(f"{self.ball} was resurrected.")

        if ability.ability_type == "self_destruct_damage":
            self.health = 0
            self.alive = False
            messages.append(f"{self.ball} blew themself up.")

        return "\n".join(messages) if messages else "Nothing happened."

    def format_ability_message(self, ability, targets):
        template = getattr(ability, "ability_message", "") or ""
        if not template:
            return ""

        opponent = ", ".join(str(t.ball) for t in targets) if targets else "nobody"

        try:
            return template.format(
                ball=self.ball,
                ability=ability.ability_name,
                opponent=opponent,
            )
        except (KeyError, IndexError, ValueError):
            return template

    def resurrect_if_allowed(self, ability):
        if self.alive:
            return False

        limit = getattr(ability, "revive_limit", 0)
        if limit and self.resurrections >= limit:
            return False

        amount = getattr(ability, "revive_amount", 1)
        health = getattr(ability, "revive_health", 25)

        self.resurrections += amount
        return self.revive(health)
