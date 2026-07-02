"""BricksRT logic tests. Run with `py -m pytest` or `py tests/test_game.py`."""

import os
import random
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game as g
from game import Brick, Game, Projectile

# Never touch the real highscores.json
g.HIGHSCORE_FILE = os.path.join(tempfile.gettempdir(), "bricksrt_test_hs.json")


def _fresh_game(wave: int = 1) -> Game:
    gm = Game()
    gm.start()
    gm.wave = wave
    gm.gun_cooldown = 0  # skip initial aim delay
    return gm


def test_projectile_speed_framerate_independent():
    gm = _fresh_game()
    gm.bricks.clear()
    gm.update_aim((240, 100))
    assert gm.fire_gun()
    p = gm.projectiles[0]
    start = p.pos.copy()
    for _ in range(6):
        p.update(1 / 60)
    d60 = (p.pos - start).length()
    p2 = Projectile(start, p.vel)
    for _ in range(2):
        p2.update(1 / 20)
    d20 = (p2.pos - start).length()
    assert abs(d60 - d20) < 1e-6
    assert abs(p.vel.length() - g.PROJECTILE_SPEED) < 1e-6


def test_long_simulation_runs_clean():
    random.seed(1)
    gm = _fresh_game(wave=35)  # past wide/hexagon unlocks
    frames = 0
    while gm.phase == "playing" and frames < 3600:
        gm.update_aim((random.randint(0, g.WIDTH),
                       random.randint(g.GRID_TOP, g.GRID_BOTTOM)))
        gm.fire_gun()
        gm.gun_ammo = 5  # keep firing to exercise collisions
        if frames % 90 == 0:
            mtype = random.choice(g.AMMO_TYPES)
            gm.ammo_inv[mtype] += 1
            gm.ammo_sel = g.AMMO_TYPES.index(mtype)
            gm.mortar_cooldown = 0
            gm.fire_mortar()
        if frames % 137 == 0:
            mtype = random.choice(sorted(g.GUN_CAPABLE))
            gm.ammo_inv[mtype] += 1
            gm.ammo_sel = g.AMMO_TYPES.index(mtype)
            gm.load_gun()
        gm.update(1 / 60)
        frames += 1
    assert frames == 3600 or gm.phase == "gameover"


def test_late_game_simulation_runs_clean():
    random.seed(2)
    gm = _fresh_game(wave=75)  # merging + all shapes unlocked
    gm.game_time = g.SKULL_START  # skulls active
    frames = 0
    while gm.phase == "playing" and frames < 1800:
        gm.update_aim((random.randint(0, g.WIDTH),
                       random.randint(g.GRID_TOP, g.GRID_BOTTOM)))
        gm.fire_gun()
        gm.gun_ammo = 5
        if frames % 300 == 0 and gm.bricks:
            gm._trigger_lightning(240.0, 400.0)
        if frames % 500 == 0:
            gm._trigger_skull(240.0, 400.0)
        gm.update(1 / 60)
        frames += 1
    assert frames == 1800 or gm.phase == "gameover"


def test_wide_bricks_never_overlap_row0():
    random.seed(7)
    for _ in range(300):
        gm = _fresh_game(wave=40)
        gm.spawn_wave()
        cells = set()
        for b in gm.bricks:
            if b.row != 0:
                continue
            for cell in b.cells():
                assert cell not in cells, f"overlap at {cell}"
                cells.add(cell)


def test_new_best_flag_tie_vs_beat():
    gm = _fresh_game()
    gm.highscore = 10
    gm.wave = 10
    gm.bricks = [Brick(col=0, row=g.MAX_ROWS, hp=1)]
    assert gm._check_game_over()
    assert not gm.new_best, "tie must not count as new best"

    gm2 = _fresh_game()
    gm2.highscore = 10
    gm2.wave = 11
    gm2.bricks = [Brick(col=0, row=g.MAX_ROWS, hp=1)]
    assert gm2._check_game_over()
    assert gm2.new_best


def test_volley_scales_with_ammo():
    gm = _fresh_game()
    gm.bricks.clear()
    gm.update_aim((240, 100))
    for ammo, expected in [(1, 1), (14, 1), (15, 2), (29, 2),
                           (30, 3), (45, 4), (100, 4)]:
        gm.projectiles.clear()
        gm.stop_fire()  # new burst
        gm.gun_ammo = ammo
        gm.gun_cooldown = 0
        assert gm.fire_gun()
        assert len(gm.projectiles) == expected, f"ammo {ammo}"
        assert gm.gun_ammo == ammo - expected
    # Spread is symmetric around the aim angle
    import math
    angles = sorted(math.atan2(p.vel.y, p.vel.x) for p in gm.projectiles)
    assert abs(sum(angles) / len(angles) - gm.aim_angle) < 1e-6
    step = math.radians(g.VOLLEY_SPREAD_DEG)
    for a1, a2 in zip(angles, angles[1:]):
        assert abs((a2 - a1) - step) < 1e-6


def test_volley_locks_while_firing():
    gm = _fresh_game()
    gm.bricks.clear()
    gm.update_aim((240, 100))
    gm.gun_ammo = 16  # starts as a 2-shot volley
    burst_sizes = []
    while gm.gun_ammo > 0:
        gm.projectiles.clear()
        gm.gun_cooldown = 0
        gm.fire_gun()
        burst_sizes.append(len(gm.projectiles))
    # Held fire: stays at 2 even after ammo drops below the threshold
    assert burst_sizes == [2] * 8
    # Pool hit 0 -> lock cleared; refilled pool computes fresh
    assert gm.volley_lock is None
    gm.gun_ammo = 45
    gm.gun_cooldown = 0
    gm.projectiles.clear()
    gm.fire_gun()
    assert len(gm.projectiles) == 4
    # Release resets too
    gm.stop_fire()
    gm.gun_ammo = 5
    gm.gun_cooldown = 0
    gm.projectiles.clear()
    gm.fire_gun()
    assert len(gm.projectiles) == 1
    # Pool grows mid-fire (pickup) -> burst grows without releasing
    gm.gun_ammo += 30  # above the 3-shot threshold
    gm.gun_cooldown = 0
    gm.projectiles.clear()
    gm.fire_gun()
    assert len(gm.projectiles) == 3
    # ...but draining below the threshold again doesn't shrink it
    gm.gun_ammo = 10
    gm.gun_cooldown = 0
    gm.projectiles.clear()
    gm.fire_gun()
    assert len(gm.projectiles) == 3
    # Pool emptied externally (skull penalty) mid-hold: lock clears on
    # the next trigger attempt instead of surviving the drain
    gm.gun_ammo = 0
    gm.gun_cooldown = 0
    assert not gm.fire_gun()
    assert gm.volley_lock is None


def test_volley_charges_center_shot_only():
    gm = _fresh_game()
    gm.bricks.clear()
    gm.update_aim((240, 100))
    gm.gun_ammo = 30  # 3-shot volley
    gm.gun_cooldown = 0
    gm.ammo_inv["bomb"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("bomb"))
    assert gm.load_gun()  # 1 unit -> 5 fire bullets queued
    assert gm.gun_queue == ["bomb"] * 5
    assert gm.ammo_inv["bomb"] == 0
    assert gm.fire_gun()
    # One loaded bullet per trigger, on the center shot only
    assert [p.fireball for p in gm.projectiles] == [False, True, False]
    assert len(gm.gun_queue) == 4
    # Draining the load reverts the gun to normal bullets
    for _ in range(4):
        gm.gun_cooldown = 0
        gm.projectiles.clear()
        assert gm.fire_gun()
    assert not gm.gun_queue
    gm.gun_cooldown = 0
    gm.projectiles.clear()
    gm.fire_gun()
    assert not any(p.fireball for p in gm.projectiles)


def test_load_gun_queues_and_panic_gun_loads_all():
    gm = _fresh_game()
    gm.ammo_inv.update({"tar": 2, "bomb": 1, "mine": 1, "homing": 1})
    gm.select_mortar(g.AMMO_TYPES.index("tar"))
    assert gm.load_gun()
    gm.select_mortar(g.AMMO_TYPES.index("bomb"))
    assert gm.load_gun()  # queues behind the tar load
    assert gm.gun_queue == ["tar"] * 5 + ["bomb"] * 5
    # Panic gun (W): one unit of every stocked type at once (all six
    # types are gun-capable), in AMMO_TYPES order
    assert gm.panic_gun()  # mine 1, tar 1, homing 1 in stock
    assert gm.gun_queue == (["tar"] * 5 + ["bomb"] * 5 + ["mine"] * 5
                            + ["tar"] * 5 + ["homing"] * 5)
    assert (gm.ammo_inv["mine"] == 0 and gm.ammo_inv["tar"] == 0
            and gm.ammo_inv["homing"] == 0)
    assert not gm.panic_gun()  # nothing left


def test_sticky_charge_blows_after_fuse():
    gm = _fresh_game(wave=10)  # blast damage = wave // 2 = 5
    host = Brick(col=3, row=4, hp=100)
    neighbor = Brick(col=4, row=4, hp=3)
    gm.bricks = [host, neighbor]
    gm.ammo_inv["mine"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("mine"))
    assert gm.load_gun()
    gm.update_aim((240, 100))
    gm.gun_ammo = 1
    gm.gun_cooldown = 0
    gm.fire_gun()
    p = gm.projectiles[0]
    assert p.mine
    rect = g.cell_rect_full(3, 4, "square", gm._brick_off(host))
    p.pos.update(rect.centerx, rect.top)
    p.vel.update(0, 100)
    gm._collide_bricks(p)
    assert not p.mine  # one charge per bullet
    assert len(gm.sticky_charges) == 1
    assert gm.sticky_charges[0]["brick"] is host
    assert p.alive  # the ball bounced on
    hp_before = host.hp
    # Fuse runs down -> explosion at the host's position
    for _ in range(int(g.STICKY_FUSE * 60) + 5):
        gm.update(1 / 60)
    assert not gm.sticky_charges
    assert host.hp == hp_before - max(1, gm.wave // 2)  # blast on host...
    assert neighbor not in gm.bricks  # ...and the neighbor in the blast


def test_mortar_cooldown_and_selection():
    gm = _fresh_game()
    gm.ammo_inv["bomb"] = 2
    gm.ammo_inv["acid"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("acid"))
    assert gm.fire_mortar()
    assert gm.ammo_inv["acid"] == 0
    assert gm.mortar_shells[-1]["type"] == "acid"
    # Cooldown blocks immediate second shot
    assert not gm.fire_mortar()
    gm.mortar_cooldown = 0
    # Selected type empty -> falls back to a type with ammo
    assert gm.fire_mortar()
    assert gm.ammo_inv["bomb"] == 1
    assert gm.mortar_shells[-1]["type"] == "bomb"
    # No ammo at all -> refuses
    gm.mortar_cooldown = 0
    gm.ammo_inv = {t: 0 for t in g.AMMO_TYPES}
    assert not gm.fire_mortar()


def test_mortar_highlight_follows_ammo():
    gm = _fresh_game()
    idx = {t: i for i, t in enumerate(g.AMMO_TYPES)}
    # Firing the last shell moves the highlight to the next stocked type
    gm.ammo_inv = {t: 0 for t in g.AMMO_TYPES}
    gm.ammo_inv.update({"bomb": 1, "acid": 2})
    gm.select_mortar(idx["bomb"])
    assert gm.fire_mortar()
    assert gm.ammo_sel == idx["acid"]
    # Firing with an empty selection syncs the highlight to the fallback
    gm.mortar_cooldown = 0
    gm.select_mortar(idx["wall"])
    assert gm.fire_mortar()  # falls back to acid
    assert gm.mortar_shells[-1]["type"] == "acid"
    assert gm.ammo_sel == idx["acid"]
    # Everything empty: selection stays put
    gm.mortar_cooldown = 0
    assert gm.fire_mortar()  # last acid, nothing left to advance to
    assert gm.ammo_sel == idx["acid"]
    gm.mortar_cooldown = 0
    assert not gm.fire_mortar()


def test_cycle_mortar_wraps():
    gm = _fresh_game()
    gm.ammo_sel = 0
    gm.cycle_mortar(-1)
    assert gm.ammo_sel == len(g.AMMO_TYPES) - 1
    gm.cycle_mortar(1)
    assert gm.ammo_sel == 0


def test_pickup_collection_effects():
    gm = _fresh_game()
    gm.bricks.clear()
    cases = [
        ("ammo", lambda: gm.gun_ammo),
        ("bomb", lambda: gm.ammo_inv["bomb"]),
        ("tar", lambda: gm.ammo_inv["tar"]),
        ("homing", lambda: gm.ammo_inv["homing"]),
        ("wall", lambda: gm.ammo_inv["wall"]),
    ]
    for ptype, getter in cases:
        gm.pickups = [{"col": 3, "row": 4, "type": ptype}]
        rect = g.cell_rect(3, 4, "square", gm.brick_offset)
        p = Projectile((rect.centerx, rect.centery), (0, -1))
        before = getter()
        gm._collide_pickups(p)
        assert getter() > before, f"{ptype} pickup had no effect"
        assert not gm.pickups, f"{ptype} pickup not removed"


def test_spawn_and_death_animations():
    gm = _fresh_game(wave=1)
    # New bricks carry the slide-in timer; it decays and stays visual-only
    assert gm.bricks and all(b.spawn_t == g.SPAWN_ANIM_TIME
                             for b in gm.bricks)
    b = gm.bricks[0]
    off_before = gm._brick_off(b)
    gm.update(1 / 60)
    assert b.spawn_t < g.SPAWN_ANIM_TIME
    # Physics offset unaffected by the animation (moved only by advance)
    assert abs(gm._brick_off(b) - off_before) < 1.0

    # Killing a brick leaves a shrinking ghost that expires
    gm.bricks = [Brick(col=3, row=4, hp=1)]
    rect = g.cell_rect_full(3, 4, "square", gm._brick_off(gm.bricks[0]))
    p = Projectile((rect.centerx, rect.top - g.PROJECTILE_RADIUS - 1),
                   (0, g.PROJECTILE_SPEED))
    p.pos.y = rect.top  # inside the expanded hitbox
    gm._collide_bricks(p)
    assert not gm.bricks
    assert len(gm.dying_bricks) == 1
    assert gm.dying_bricks[0]["timer"] == g.DEATH_ANIM_TIME

    # A brick killed mid-slide-in leaves its ghost where it was DRAWN
    # (one cell up at spawn_t == SPAWN_ANIM_TIME), not at the logical cell
    gm.dying_bricks.clear()
    b = Brick(col=3, row=4, hp=1, spawn_t=g.SPAWN_ANIM_TIME)
    gm.bricks = [b]
    logical_cy = g.cell_rect(3, 4, "square", gm._brick_off(b)).centery
    gm._kill_brick(b)
    assert gm.dying_bricks[0]["cy"] == logical_cy - g.CELL_SIZE
    for _ in range(12):  # > DEATH_ANIM_TIME
        gm.update(1 / 60)
    assert not gm.dying_bricks


def test_tar_slows_bricks_in_zone():
    gm = _fresh_game(wave=6)
    gm.bricks = [
        Brick(col=0, row=3, hp=5),  # inside the tar zone
        Brick(col=6, row=3, hp=5),  # far away, full speed
    ]
    tarred, free = gm.bricks
    rect = g.cell_rect(0, 3, "square", gm.brick_offset)
    gm.placed_tars = [{"x": float(rect.centerx), "y": float(rect.centery),
                       "timer": 100.0}]

    def top_of(b):
        return g.GRID_TOP + b.row * g.CELL_SIZE + gm._brick_off(b)

    t_before, f_before = top_of(tarred), top_of(free)
    for _ in range(60):  # 1 second
        gm.update(1 / 60)
    t_moved = top_of(tarred) - t_before
    f_moved = top_of(free) - f_before
    assert f_moved > 1
    assert abs(t_moved - f_moved * g.TAR_SLOW) < 0.5, \
        f"tarred moved {t_moved:.2f}, free {f_moved:.2f}"

    # Stun inside tar: full stop, not 150%
    tarred.stun = 100.0
    t_before = top_of(tarred)
    for _ in range(30):
        gm.update(1 / 60)
    assert abs(top_of(tarred) - t_before) < 1e-6

    # Zone expires
    gm.placed_tars[0]["timer"] = 0.001
    gm.update(1 / 60)
    assert not gm.placed_tars


def test_tar_mortar_lands_as_zone():
    gm = _fresh_game(wave=10)
    gm.ammo_inv["tar"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("tar"))
    gm.crosshair = (240, 300)
    assert gm.fire_mortar()
    shell = gm.mortar_shells[-1]
    assert shell["type"] == "tar"
    gm._land_mortar(shell)
    assert len(gm.placed_tars) == 1
    assert gm.placed_tars[0]["timer"] == g.TAR_DURATION


def test_bricks_stack_on_stunned_brick():
    gm = _fresh_game(wave=5)
    gm.bricks = [
        Brick(col=0, row=3, hp=5, stun=10.0),  # stunned, stands still
        Brick(col=0, row=2, hp=5),             # directly above: must stop
        Brick(col=4, row=2, hp=5),             # other column: keeps moving
    ]
    stunned, above, free = gm.bricks

    def top_of(b):
        return g.GRID_TOP + b.row * g.CELL_SIZE + gm._brick_off(b)

    free_top_before = top_of(free)
    for _ in range(60):  # 1 second
        gm.update(1 / 60)
    assert stunned.lag > 1
    # The brick above sits flush on the stunned brick — no overlap
    above_bottom = top_of(above) + g.CELL_SIZE
    assert abs(above_bottom - top_of(stunned)) < 0.5
    assert above.held > 0
    # Unrelated column advanced normally
    assert top_of(free) > free_top_before + 1


def test_wall_blocking_pins_and_stacks():
    gm = _fresh_game()
    gm.bricks = [
        Brick(col=2, row=5, hp=3),  # just above the wall
        Brick(col=2, row=4, hp=2),  # stacked on top of it
        Brick(col=5, row=5, hp=1),  # different column: unaffected... same wall
    ]
    # Wall exactly at the bottom of row 5, minus 10px so bricks overshoot
    wall_y = g.GRID_TOP + 6 * g.CELL_SIZE - 10
    gm.placed_walls = [{"y": wall_y, "max_weight": 999,
                        "grace": 2.0, "ttl": 12.0}]
    gm.brick_offset = 0.0
    gm._update_wall_blocking()
    assert gm.bricks[0].held == 10  # pinned at the wall
    assert gm.bricks[1].held == 10  # stacked: held by the brick below
    assert gm.bricks[2].held == 10  # wall spans full width


def test_distribute_blocked_hp_conserves_total():
    gm = _fresh_game()
    # Two separate held containers: cols 0-1 connected, col 5 alone
    gm.bricks = [
        Brick(col=0, row=3, hp=1, held=5.0),
        Brick(col=1, row=3, hp=1, held=5.0),
        Brick(col=5, row=2, hp=1, held=5.0),
    ]
    before = sum(b.hp for b in gm.bricks)
    gm._distribute_blocked_hp({0: 10, 5: 7})
    after = sum(b.hp for b in gm.bricks)
    assert after == before + 17
    # Container 0-1 shares the 10; col 5 gets its own 7
    assert gm.bricks[0].hp + gm.bricks[1].hp == 2 + 10
    assert gm.bricks[2].hp == 1 + 7


def test_advance_rows_moves_bricks_and_pickups():
    gm = _fresh_game()
    gm.bricks = [Brick(col=0, row=2, hp=5)]
    gm.pickups = [{"col": 1, "row": 3, "type": "ammo"}]
    wave_before = gm.wave
    gm._advance_rows()
    assert gm.bricks[0].row == 3
    assert gm.pickups[0]["row"] == 4
    assert gm.wave == wave_before + 1  # advancing spawns a wave


def test_lightning_zaps_and_stuns():
    random.seed(11)
    gm = _fresh_game(wave=20)
    gm.bricks = [Brick(col=c, row=2, hp=100) for c in range(8)]
    gm._trigger_lightning(240.0, 400.0)
    struck = [b for b in gm.bricks if b.hp < 100]
    assert len(struck) == g.LIGHTNING_STRIKES
    assert all(b.hp == 100 - gm.wave // 5 for b in struck)
    assert all(b.stun == g.LIGHTNING_STUN for b in struck)
    assert all(b.stun == 0 for b in gm.bricks if b.hp == 100)
    assert len(gm.lightning_bolts) == 1
    # Bolt path visits trigger point + one center per strike (jagged between)
    assert len(gm.lightning_bolts[0]["points"]) > g.LIGHTNING_STRIKES

    # Lethal strikes remove bricks
    gm2 = _fresh_game(wave=20)
    gm2.bricks = [Brick(col=0, row=2, hp=1), Brick(col=1, row=2, hp=1)]
    gm2._trigger_lightning(240.0, 400.0)
    assert not gm2.bricks


def test_stunned_brick_stops_advancing():
    gm = _fresh_game(wave=5)
    gm.bricks = [
        Brick(col=0, row=2, hp=5, stun=10.0),  # stunned (long, for the test)
        Brick(col=5, row=2, hp=5),             # moving normally
    ]
    stunned, normal = gm.bricks
    y_stunned = g.GRID_TOP + stunned.row * g.CELL_SIZE + gm._brick_off(stunned)
    y_normal = g.GRID_TOP + normal.row * g.CELL_SIZE + gm._brick_off(normal)
    for _ in range(30):  # 0.5s
        gm.update(1 / 60)
    y_stunned2 = g.GRID_TOP + stunned.row * g.CELL_SIZE + gm._brick_off(stunned)
    y_normal2 = g.GRID_TOP + normal.row * g.CELL_SIZE + gm._brick_off(normal)
    assert abs(y_stunned2 - y_stunned) < 1e-6, "stunned brick moved"
    assert y_normal2 > y_normal + 1, "normal brick did not move"
    # Stun expires and the brick keeps its lag but resumes moving
    stunned.stun = 0.0
    lag_before = stunned.lag
    y_before = g.GRID_TOP + stunned.row * g.CELL_SIZE + gm._brick_off(stunned)
    for _ in range(30):
        gm.update(1 / 60)
    assert stunned.lag == lag_before
    y_after = g.GRID_TOP + stunned.row * g.CELL_SIZE + gm._brick_off(stunned)
    assert y_after > y_before + 1, "brick did not resume after stun"


def test_skull_halves_hp_shields_and_ammo():
    gm = _fresh_game(wave=80)
    gm.bricks = [
        Brick(col=0, row=2, hp=10, shield=4),
        Brick(col=1, row=2, hp=1),
        Brick(col=2, row=2, hp=7),
    ]
    gm.gun_ammo = 9
    gm._trigger_skull(240.0, 400.0)
    assert [b.hp for b in gm.bricks] == [5, 1, 3]  # floors at 1
    assert gm.bricks[0].shield == 2
    assert gm.gun_ammo == 4
    assert gm.skull_wave is not None
    # Ammo floors at 1
    gm.gun_ammo, gm.gun_reloading, gm.ammo_debt = 1, 0, 0
    gm._trigger_skull(240.0, 400.0)
    assert gm.gun_ammo == 1 and gm.ammo_debt == 0


def test_skull_halves_total_pool_no_dodge():
    # Halving spans available + reload queue + in-flight
    gm = _fresh_game(wave=80)
    gm.bricks.clear()
    gm.gun_ammo = 4
    gm.gun_reloading = 3
    flying = [Projectile((240, 300), (0, -g.PROJECTILE_SPEED))
              for _ in range(2)]
    gm.projectiles = list(flying)
    gm._trigger_skull(240.0, 400.0)  # total 9 -> keep 4, destroy 5
    assert gm.gun_ammo == 0
    assert gm.gun_reloading == 2
    assert gm.ammo_debt == 0

    # Everything airborne: destruction becomes debt that eats returns
    gm2 = _fresh_game(wave=80)
    gm2.bricks.clear()
    gm2.gun_ammo = 0
    flying = [Projectile((240, 300), (0, -g.PROJECTILE_SPEED))
              for _ in range(4)]
    gm2.projectiles = list(flying)
    gm2._trigger_skull(240.0, 400.0)  # total 4 -> keep 2, debt 2
    assert gm2.ammo_debt == 2
    for p in flying:  # all shots exit the bottom
        p.alive = False
        p.exited_bottom = True
    gm2.update(1 / 60)
    assert gm2.ammo_debt == 0
    assert gm2.gun_reloading == 2  # only the kept half returns


def test_skull_spawns_after_ten_minutes_in_bottom_rows():
    gm = _fresh_game()
    gm.bricks.clear()
    gm.game_time = g.SKULL_START + 1
    gm.update(1 / 60)
    assert len(gm.placed_skulls) == 1
    # Next one only after the interval
    gm.update(1 / 60)
    assert len(gm.placed_skulls) == 1
    gm.skull_timer = 0.001
    gm.update(1 / 60)
    assert len(gm.placed_skulls) == 2
    for sk in gm.placed_skulls:
        row = int((sk["y"] - g.GRID_TOP - gm.brick_offset) // g.CELL_SIZE)
        assert row >= g.MAX_ROWS - g.SKULL_ROWS, f"skull too high: row {row}"


def test_grazing_bounce_leaves_border():
    import math
    min_n = math.sin(math.radians(g.MIN_BOUNCE_ANGLE))
    # Nearly vertical shot grazing the left wall
    p = Projectile((g.PROJECTILE_RADIUS + 0.5, 400),
                   (-60, -g.PROJECTILE_SPEED))
    speed = p.vel.length()
    p.update(1 / 60)
    assert p.vel.x >= speed * min_n - 1e-6  # kicked off the wall
    assert abs(p.vel.length() - speed) < 1e-6  # speed preserved
    assert p.vel.y < 0  # still heading up
    # Nearly horizontal shot grazing the ceiling
    p = Projectile((240, g.GRID_TOP + g.PROJECTILE_RADIUS + 0.5),
                   (g.PROJECTILE_SPEED, -60))
    speed = p.vel.length()
    p.update(1 / 60)
    assert p.vel.y >= speed * min_n - 1e-6  # kicked off the ceiling
    assert abs(p.vel.length() - speed) < 1e-6
    assert p.vel.x > 0  # still heading right


def test_tarshot_slows_accumulatively():
    gm = _fresh_game()
    gm.bricks = [Brick(col=3, row=4, hp=100)]
    b = gm.bricks[0]
    gm.ammo_inv["tar"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("tar"))
    assert gm.load_gun()
    gm.update_aim((240, 100))
    gm.gun_ammo = 1
    gm.gun_cooldown = 0
    gm.fire_gun()
    p = gm.projectiles[0]
    assert p.tar  # loaded tar bullet
    assert len(gm.gun_queue) == 4
    rect = g.cell_rect_full(3, 4, "square", gm._brick_off(b))
    for _ in range(3):
        p.pos.update(rect.centerx, rect.top)
        p.vel.update(0, 100)
        gm._collide_bricks(p)
    assert abs(b.slow_pct - 0.45) < 1e-9  # 15% per hit
    assert b.slow_t == g.TARSHOT_TIME
    # Slowed brick falls behind the field
    lag0 = b.lag
    gm.update(1 / 60)
    assert b.lag > lag0
    # More hits cap at a full stop
    for _ in range(7):
        p.pos.update(rect.centerx, rect.top)
        p.vel.update(0, 100)
        gm._collide_bricks(p)
    assert b.slow_pct == 1.0
    # Expires 3s after the LAST hit and the stacks reset
    for _ in range(200):
        gm.update(1 / 60)
    assert b.slow_t == 0.0 and b.slow_pct == 0.0


def test_skull_hp_cut_is_permanent_and_stacks():
    gm = _fresh_game(wave=110)
    gm.bricks = [Brick(col=0, row=5, hp=110)]
    gm._trigger_skull(100, 400)
    assert gm.skull_hp_cut == 55  # half the spawn HP at trigger time
    assert gm.bricks[0].hp == 55  # on-field halving unchanged
    # New bricks spawn reduced from now on
    gm.bricks.clear()
    gm.pickups.clear()
    random.seed(3)
    gm.spawn_wave()  # wave 111 -> base hp 111 - 55 = 56
    assert gm.bricks
    assert all(b.hp % 56 == 0 for b in gm.bricks)  # wide/double multiply
    # The next skull stacks: adds half of the CURRENT spawn HP
    gm._trigger_skull(100, 400)
    assert gm.skull_hp_cut == 55 + (111 - 55) // 2


def test_board_clear_drops_reward():
    gm = _fresh_game(wave=35)
    gm.bricks = [Brick(col=3, row=4, hp=1)]
    gm.pickups.clear()
    rect = g.cell_rect_full(3, 4, "square", gm._brick_off(gm.bricks[0]))
    p = Projectile((rect.centerx, rect.centery), (0, 1))
    gm.projectiles = [p]
    gm.update(1 / 60)
    assert not gm.bricks
    assert len(gm.pickups) == 1
    pu = gm.pickups[0]
    assert pu["row"] <= 3  # dropped high enough to react to
    assert pu["type"] in ("ammo", "mine", "wall", "bomb")  # wave-35 pool
    # No repeat drop while the board stays empty
    gm.update(1 / 60)
    assert len(gm.pickups) == 1


def test_skull_sweep_flashes_bricks():
    gm = _fresh_game()
    near = Brick(col=4, row=5, hp=10)   # close to the trigger point
    far = Brick(col=0, row=0, hp=10)    # swept a few frames later
    gm.bricks = [near, far]
    rect = g.cell_rect(4, 5, "square", gm._brick_off(near))
    gm._trigger_skull(rect.centerx, rect.centery)
    assert gm.ammo_flash == g.AMMO_FLASH_TIME  # HUD pulse armed
    gm.update(1 / 60)
    assert near.flash > 0  # ring covered the near brick first
    assert far.flash == 0
    far_flashed = False
    for _ in range(120):
        gm.update(1 / 60)
        far_flashed = far_flashed or far.flash > 0
    assert far_flashed  # ring reached the far brick on its way out
    assert gm.skull_wave is None  # sweep finished
    assert near.flash == 0  # flash decayed back to zero


def test_panic_barrage():
    gm = _fresh_game()
    gm.bricks = [Brick(col=1, row=2, hp=50), Brick(col=3, row=6, hp=5),
                 Brick(col=6, row=6, hp=9)]
    gm.ammo_inv = {"mine": 2, "wall": 3, "bomb": 1, "tar": 1, "acid": 0,
                   "homing": 0}
    gm.mortar_cooldown = 0.6  # panic ignores the cooldown
    assert gm.panic()
    # One of each stocked type except wall; acid/homing were empty
    assert gm.ammo_inv == {"mine": 1, "wall": 3, "bomb": 0,
                           "tar": 0, "acid": 0, "homing": 0}
    shells = gm.mortar_shells
    assert sorted(s["type"] for s in shells) == ["bomb", "mine", "tar"]
    # Targets sit on the lowest occupied row (row 6); mines a cell below
    row_y = g.GRID_TOP + 6.5 * g.CELL_SIZE + gm.brick_offset
    for s in shells:
        expect = row_y + g.CELL_SIZE if s["type"] == "mine" else row_y
        assert abs(s["ty"] - min(g.GRID_BOTTOM, expect)) < 1.0
    # Crosshair snapped to the biggest brick ON THE LOWEST ROW (col 6,
    # hp 9) — not the hp-50 brick further up
    expect_rect = g.cell_rect(6, 6, "square", gm._brick_off(gm.bricks[2]))
    assert gm.crosshair == (expect_rect.centerx, expect_rect.centery)
    # Second press fires what's left; then the stock is dry
    assert gm.panic()
    assert gm.ammo_inv["mine"] == 0
    assert not gm.panic()  # only walls left -> refuses
    gm.ammo_inv["acid"] = 1
    gm.bricks.clear()
    assert not gm.panic()  # no bricks -> nothing to target


def test_wall_break_no_jump():
    gm = _fresh_game()
    gm.bricks.clear()
    gm.pickups.clear()
    b = Brick(col=3, row=5, hp=5)
    gm.bricks = [b]
    bottom0 = g.GRID_TOP + 6 * g.CELL_SIZE + gm.brick_offset
    wall_y = bottom0 - 10  # wall line 10px above the brick's free bottom
    gm.placed_walls = [{"y": wall_y, "max_weight": 10 ** 6,
                        "grace": 0.0, "ttl": 10.0}]
    gm._update_wall_blocking()
    assert b.held > 9  # pinned at the wall
    held_bottom = g.GRID_TOP + 6 * g.CELL_SIZE + gm._brick_off(b)
    assert abs(held_bottom - wall_y) < 0.01
    # Wall expires this frame — the brick must resume from the wall
    # line, not jump forward by the held amount
    gm.placed_walls[0]["ttl"] = 1e-6
    gm.update(1 / 60)
    assert not gm.placed_walls
    new_bottom = g.GRID_TOP + 6 * g.CELL_SIZE + gm._brick_off(b)
    assert new_bottom - wall_y < 1.0
    assert b.lag > 9  # hold-back preserved as lag
    # ...and it advances normally from there
    for _ in range(60):
        gm.update(1 / 60)
    later_bottom = g.GRID_TOP + 6 * g.CELL_SIZE + gm._brick_off(b)
    assert later_bottom > new_bottom


def test_wallshot_stops_brick():
    gm = _fresh_game()
    b = Brick(col=3, row=4, hp=100)
    gm.bricks = [b]
    gm.ammo_inv["wall"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("wall"))
    assert gm.load_gun()
    gm.update_aim((240, 100))
    gm.gun_ammo = 1
    gm.gun_cooldown = 0
    gm.fire_gun()
    p = gm.projectiles[0]
    assert p.wallshot
    rect = g.cell_rect_full(3, 4, "square", gm._brick_off(b))
    p.pos.update(rect.centerx, rect.top)
    p.vel.update(0, 100)
    gm._collide_bricks(p)
    assert b.stun == g.WALLSHOT_STUN  # full stop, like a lightning stun


def test_acidshot_dot_dissolves():
    gm = _fresh_game()
    b = Brick(col=3, row=4, hp=3)
    gm.bricks = [b]
    gm.ammo_inv["acid"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("acid"))
    assert gm.load_gun()
    gm.update_aim((240, 100))
    gm.gun_ammo = 1
    gm.gun_cooldown = 0
    gm.fire_gun()
    p = gm.projectiles[0]
    assert p.acid
    rect = g.cell_rect_full(3, 4, "square", gm._brick_off(b))
    p.pos.update(rect.centerx, rect.top)
    p.vel.update(0, 100)
    gm._collide_bricks(p)
    assert b.hp == 2  # direct hit
    assert b.acid_dot == g.ACIDSHOT_DOT
    # DoT ticks 1 dmg/s: 2 hp gone within 2.5s
    for _ in range(150):
        gm.update(1 / 60)
    assert b not in gm.bricks


def test_effects_damage_shields():
    gm = _fresh_game(wave=20)
    b = Brick(col=3, row=4, hp=100, shield=8)
    gm.bricks = [b]
    rect = g.cell_rect(3, 4, "square", gm._brick_off(b))
    # Explosion halves the shield in addition to hp damage
    hp0 = b.hp
    gm._explode(rect.centerx, rect.centery)
    assert b.shield == 4
    assert b.hp < hp0
    # Fire bullet chips 1 shield along with its hp damage
    p = Projectile((rect.centerx, rect.centery), (0, -1))
    p.fireball = True
    hp1 = b.hp
    gm._collide_bricks(p)
    assert b.hp == hp1 - 1 and b.shield == 3
    # Acid zone tick melts shield BEFORE hp (wave 20 -> 2 per tick)
    gm.placed_acids = [{"x": rect.centerx, "y": rect.centery,
                        "timer": 5.0, "tick": 0.0}]
    hp2 = b.hp
    gm._update_acids(0.01)
    assert b.shield == 1 and b.hp == hp2
    # Acid-bullet DoT: shield absorbs the tick, then hp burns
    b.shield = 1
    b.acid_dot = g.ACIDSHOT_DOT
    b.acid_tick = 0.0
    gm.placed_acids.clear()
    hp3 = b.hp
    for _ in range(150):  # 2.5s -> two ticks
        gm.update(1 / 60)
    assert b.shield == 0 and b.hp == hp3 - 1


def test_homing_rocket_hits_nearest_to_gun():
    gm = _fresh_game()
    near = Brick(col=4, row=8, hp=5)   # closest to the gun (bottom center)
    far = Brick(col=0, row=0, hp=5)
    gm.bricks = [near, far]
    gm.ammo_inv["homing"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("homing"))
    gm.crosshair = (30, 80)  # aimed elsewhere — rocket ignores it
    assert gm.fire_mortar()
    shell = gm.mortar_shells[-1]
    assert shell["type"] == "homing"
    assert shell["target"] is near
    for _ in range(60):
        gm.update(1 / 60)
        if not gm.mortar_shells:
            break
    assert not gm.mortar_shells  # landed
    assert near not in gm.bricks or near.hp < 5  # explosion hit it
    # No bricks -> rocket refuses and keeps its ammo
    gm.bricks.clear()
    gm.ammo_inv["homing"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("homing"))
    gm.mortar_cooldown = 0
    assert not gm.fire_mortar()
    assert gm.ammo_inv["homing"] == 1


def test_wall_bounce_no_stick():
    gm = _fresh_game()
    gm.bricks.clear()
    wall = {"y": 400.0, "max_weight": 50, "grace": 2.0, "ttl": 12.0}
    gm.placed_walls = [wall]
    # Grazing shot from above: bounces once, then leaves the band —
    # no per-frame re-bounce chipping the wall
    p = Projectile((100, 400 - g.PROJECTILE_RADIUS - 1.5),
                   (g.PROJECTILE_SPEED, 30))
    gm.projectiles = [p]
    gm._collide_walls(p)
    assert wall["max_weight"] == 49  # one chip
    assert p.vel.y < 0  # heading away
    for _ in range(10):
        p.update(1 / 60)
        gm._collide_walls(p)
    assert wall["max_weight"] == 49  # still just the one chip


def test_double_hp_spawns():
    # Below the wide unlock, spawn HP is wave or (5% chance) double it
    hps = set()
    for seed in range(200):
        random.seed(seed)
        gm = Game()
        gm.wave = 20
        gm.spawn_wave()  # bumps to 21
        hps.update(b.hp for b in gm.bricks)
    assert hps == {21, 42}


def test_merging_creates_tall_brick():
    merged = None
    for seed in range(200):
        random.seed(seed)
        gm = _fresh_game(wave=74)  # spawn_wave bumps to 75
        gm.bricks = [Brick(col=c, row=1, hp=5) for c in range(8)]
        gm.spawn_wave()
        talls = [b for b in gm.bricks if b.shape == "tall"]
        if talls:
            merged = (gm, talls[0])
            break
    assert merged is not None, "no merge in 200 seeds"
    gm, tall = merged
    assert tall.row == 0
    # Spawn HP (5% chance doubled) + absorbed brick's HP
    assert tall.hp - 5 in (75, 150)
    # No slide-in replay: the bottom half was already on screen
    assert tall.spawn_t == 0
    # The absorbed brick is gone and nothing overlaps the tall's cells
    for b in gm.bricks:
        if b is tall:
            continue
        assert not (set(b.cells()) & set(tall.cells()))


def test_esc_save_if_record():
    gm = _fresh_game()
    gm.highscore = 5
    gm.wave = 8
    gm.save_if_record()
    assert gm.highscore == 8
    assert g.load_highscore("realtime") >= 8


def _run_all():
    mod = sys.modules[__name__]
    tests = [getattr(mod, n) for n in dir(mod)
             if n.startswith("test_") and callable(getattr(mod, n))]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"ALL PASS ({len(tests)} tests)")


if __name__ == "__main__":
    _run_all()
