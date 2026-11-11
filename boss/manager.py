from random import choice, choices, random, uniform

from .battle import PASSIVE_TYPES, BattleBall, SummonedBall


class BossManager:
    """Co-op fight: every player's balls are team_one, the boss (and its minions) team_two."""

    def __init__(self, cfg, moves, players, abilities=None):
        # cfg: name, ball_id, health, mode ("random" / "manual"), attack_min, attack_max,
        #      move_chance, ability (the boss ball's BattleAbility or None)
        # players: [(user_id, [BallInstance, ...]), ...] in turn order
        # abilities: {ball_id: BattleAbility} for the players balls (optional)
        abilities = abilities or {}

        self.cfg = cfg
        self.moves = [m for m in moves if m.enabled]
        self.order = []
        self.team_one = []

        for user_id, balls in players:
            self.order.append(user_id)
            for ball in balls:
                fighter = BattleBall(
                    ball, ability=abilities.get(getattr(ball, "ball_id", None))
                )
                fighter.owner_id = user_id
                self.team_one.append(fighter)

        # the health is the one chosen at the start, not the ball's own stats
        self.boss = BattleBall(
            SummonedBall(cfg.name, cfg.attack_min, cfg.health), ability=cfg.ability
        )
        self.boss.ball_id = cfg.ball_id
        self.team_two = [self.boss]

        self.move_uses = {m.pk: 0 for m in self.moves}
        self.move_cd = {m.pk: m.start_delay for m in self.moves}

        self.round = 1
        self.acted = set()
        self.awaiting_boss = False  # manual mode: waiting for the admin
        self.last_attack = None
        self.refresh_passives()

    # ---- helpers -------------------------------------------------------

    def get_alive(self, team):
        return [ball for ball in team if ball.alive]

    def teams_for(self, ball):
        if ball in self.team_one:
            return self.team_one, self.team_two
        if ball in self.team_two:
            return self.team_two, self.team_one
        return None, None

    def active_users(self):
        return [
            user_id for user_id in self.order
            if any(b.alive and b.owner_id == user_id for b in self.team_one)
        ]

    def current_user(self):
        if self.outcome() is not None or self.awaiting_boss:
            return None
        for user_id in self.active_users():
            if user_id not in self.acted:
                return user_id
        return None

    def player_balls(self, user_id):
        return [b for b in self.team_one if b.alive and b.owner_id == user_id]

    def outcome(self):
        """None while fighting, else "players" or "boss"."""
        if not self.boss.alive:
            return "players"
        if not self.get_alive(self.team_one):
            return "boss"
        return None

    def manual(self):
        return self.cfg.mode == "manual"

    def round_done(self):
        """All players have acted: run the boss turn (random) or wait for the admin (manual)."""
        if self.outcome() is not None or self.current_user() is not None:
            return []
        if self.manual():
            self.awaiting_boss = True
            return []
        return self.boss_turn()

    # ---- ticking -------------------------------------------------------

    def tick(self, own_balls, own_team, enemy_balls):
        """Counters that move after a side has acted."""
        messages = []

        for ball in own_balls:
            if ball.alive and ball.passive_type() == "round_growth":
                partners = [
                    b for b in own_team
                    if b.alive and b is not ball and b.ball_id in ball.companion_ids
                ]
                if partners:
                    ball.attack *= ball.ability.value
                    messages.append(f"{ball.ball} got stronger.")

        for ball in own_balls:
            for entry in list(ball.timed):
                entry[1] -= 1
                if entry[1] <= 0:
                    ball.attack /= entry[0]
                    ball.timed.remove(entry)

            if ball.cooldown > 0:
                ball.cooldown -= 1

        for ball in enemy_balls:
            if ball.dodging > 0:
                ball.dodging -= 1
            if ball.protected > 0:
                ball.protected -= 1

        return messages


    # ---- player actions --------------------------------------------------

    def finish_player_action(self, actor, result):
        own_balls = [b for b in self.team_one if b.owner_id == actor.owner_id]
        messages = list(self.tick(own_balls, self.team_one, self.team_two))

        messages.extend(self.apply_status_effects(self.team_one))
        messages.extend(self.apply_status_effects(self.team_two))
        messages.extend(self.refresh_passives())

        self.acted.add(actor.owner_id)

        messages.extend(self.round_done())

        if messages:
            result += "\n" + "\n".join(messages)

        return result

    def player_attack(self, attacker, target):
        if self.outcome() is not None:
            return "#ITSSOOVER"

        if not attacker.alive:
            return "they look dead but idk"

        if not attacker.can_attack():
            return f"{attacker.ball} doesnt attack."

        if not target.alive:
            return "#son"

        # a tank on the boss side takes every hit
        for ball in self.get_alive(self.team_two):
            if ball is not target and ball.passive_type() == "tank":
                target = ball
                break

        was_stunned = attacker.stunned > 0
        result = attacker.attack_target(target)

        if not was_stunned and target.alive:
            for ball in self.get_alive(self.team_one):
                if ball is attacker or ball.passive_type() != "ally_assist":
                    continue
                if ball.can_attack() and target.alive:
                    result += "\n" + ball.attack_target(target)

        return self.finish_player_action(attacker, result)

    def player_ability(self, user):
        if self.outcome() is not None:
            return "#ITSSOOVER"

        if not user.alive:
            return "they look dead but idk"

        blocked = self.ability_blocked(user)
        if blocked:
            return blocked

        if user.stunned > 0:
            user.stunned -= 1
            result = f"{user.ball} is stunned and cannot use its ability!"
        else:
            ability = user.ability
            result = user.use_ability(ability, self.team_one, self.team_two)
            user.uses += 1
            user.cooldown = ability.cooldown_turns + 1 if ability.cooldown_turns else 0

        return self.finish_player_action(user, result)

    def skip_turn(self, user_id):
        self.acted.add(user_id)
        result = "Turn skipped."
        messages = self.round_done()
        if messages:
            result += "\n" + "\n".join(messages)
        return result

    # ---- boss turn -------------------------------------------------------

    def move_available(self, move):
        if move.max_uses and self.move_uses[move.pk] >= move.max_uses:
            return False
        return self.move_cd[move.pk] <= 0

    def pick_move(self):
        boss = self.boss
        percent = boss.health / boss.max_health * 100 if boss.max_health else 0

        eligible = [
            m for m in self.moves
            if percent <= m.hp_below_percent and self.move_available(m)
        ]

        if not eligible or random() * 100 >= self.cfg.move_chance:
            return None

        return choices(eligible, weights=[max(1, m.weight) for m in eligible])[0]

    def boss_act(self, chosen_move=None):
        boss = self.boss

        if boss.stunned > 0:
            boss.stunned -= 1
            return [f"{boss.ball} is stunned and cannot act!"]

        out = []

        # the ball's own ability is automatic, it goes off whenever it is ready
        ability = boss.ability
        if ability is not None and ability.enabled and self.ability_blocked(boss) is None:
            out.append(boss.use_ability(ability, self.team_two, self.team_one))
            boss.uses += 1
            boss.cooldown = ability.cooldown_turns + 1 if ability.cooldown_turns else 0

        move = chosen_move if self.manual() else self.pick_move()
        if move is not None and not self.get_alive(self.team_one):
            move = None

        if move is not None:
            out.append(boss.use_ability(move, self.team_two, self.team_one))
            self.move_uses[move.pk] += 1
            self.move_cd[move.pk] = move.cooldown_turns + 1 if move.cooldown_turns else 0
            return out

        alive = self.get_alive(self.team_one)
        if alive:
            out.append(boss.attack_target(choice(alive)))
        return out

    def boss_turn(self, attack=None, move=None):
        """attack = the attack chosen for this turn (None = random roll), move = manual choice."""
        messages = []
        cfg = self.cfg

        if attack is None:
            low, high = sorted((cfg.attack_min, cfg.attack_max))
            attack = round(uniform(low, high))

        self.last_attack = attack
        self.boss.attack = float(attack)
        self.awaiting_boss = False
        messages.append(f"{self.boss.ball} goes for {attack:g} attack this turn.")

        for unit in list(self.get_alive(self.team_two)):
            if not unit.alive or not self.get_alive(self.team_one):
                continue

            if unit is self.boss:
                messages.extend(self.boss_act(move))
            elif unit.can_attack():
                messages.append(unit.attack_target(choice(self.get_alive(self.team_one))))

        messages.extend(self.tick(self.team_two, self.team_two, self.team_one))

        for key in self.move_cd:
            if self.move_cd[key] > 0:
                self.move_cd[key] -= 1

        self.round += 1
        self.acted = set()

        messages.extend(self.apply_status_effects(self.team_one))
        messages.extend(self.apply_status_effects(self.team_two))
        messages.extend(self.refresh_passives())

        return messages

    # ---- shared pieces (same rules as the battle package) ---------------

    def sync_boost(self, owner, wanted, value, health_only=False):
        """Applies/reverts a multiplier on the balls that should (not) have it."""
        if value <= 0:
            value = 1

        for key, ball in list(owner.applied.items()):
            if not any(ball is w for w in wanted):
                if not health_only:
                    ball.attack /= value
                ball.max_health /= value
                ball.health = min(ball.health, ball.max_health)
                del owner.applied[key]

        for ball in wanted:
            if id(ball) not in owner.applied:
                if not health_only:
                    ball.attack *= value
                ball.max_health *= value
                ball.health *= value
                owner.applied[id(ball)] = ball

    def refresh_passives(self):
        messages = []
        dead_total = sum(1 for b in self.team_one + self.team_two if not b.alive)

        for own_team, enemy_team in (
            (self.team_one, self.team_two),
            (self.team_two, self.team_one),
        ):
            for owner in own_team:
                kind = owner.passive_type()
                if kind is None:
                    continue

                value = owner.ability.value

                if kind == "aura_health":
                    wanted = [
                        b for b in own_team
                        if owner.alive and b.alive and b is not owner
                        and b.ball_id in owner.companion_ids
                    ]
                    self.sync_boost(owner, wanted, value, health_only=True)

                elif kind == "pair_boost":
                    partners = [
                        b for b in own_team
                        if b.alive and b is not owner and b.ball_id in owner.companion_ids
                    ]
                    wanted = [owner] + partners if owner.alive and partners else []
                    self.sync_boost(owner, wanted, value)

                elif kind == "no_attack":
                    wanted = [owner] if owner.alive else []
                    self.sync_boost(owner, wanted, value, health_only=True)

                elif kind == "death_growth":
                    delta = dead_total - owner.seen_deaths
                    if delta > 0 and owner.alive:
                        owner.attack *= value ** delta
                    owner.seen_deaths = dead_total

                elif kind == "tank":
                    if owner.last_stand_pending:
                        owner.last_stand_pending = False
                        alive = self.get_alive(enemy_team)
                        if alive:
                            victim = choice(alive)
                            victim.health = 0
                            victim.alive = False
                            messages.append(f"{owner.ball} did a last stand and took {victim.ball} out!")

                elif kind in ("death_revenge", "death_snipe"):
                    if owner.alive or owner.death_done:
                        continue
                    owner.death_done = True

                    if kind == "death_revenge":
                        victim = owner.killed_by
                    else:
                        alive = self.get_alive(enemy_team)
                        victim = max(alive, key=lambda b: b.attack) if alive else None

                    if victim is not None and victim.alive:
                        victim.health = 0
                        victim.alive = False
                        messages.append(f"{owner.ball} took {victim.ball} down with them!")

        return messages

    def ability_blocked(self, ball):
        """Returns why the ball cant use its ability right now, or None."""
        ability = ball.ability

        if ability is None:
            return "This ball has no ability."

        if not ability.enabled:
            return "This ability is disabled."

        if ability.ability_type in PASSIVE_TYPES:
            return "That ability is passive, it works on its own."

        if ability.max_uses and ball.uses >= ability.max_uses:
            return f"{ability.ability_name} has no uses left."

        if ball.cooldown > 0:
            return f"{ability.ability_name} is on cooldown for {ball.cooldown} more turn(s)."

        return None

    def apply_status_effects(self, team):
        messages = []

        for ball in team:
            if not ball.alive:
                continue

            if ball.burning > 0:
                ball.take_damage(ball.burn_damage)
                ball.burning -= 1
                messages.append(f"{ball.ball} got 3rd degree burns all over them!")

        return messages
