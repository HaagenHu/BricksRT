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
            mtype = random.choice(g.MORTAR_TYPES)
            gm.mortar_ammo[mtype] += 1
            gm.mortar_sel = g.MORTAR_TYPES.index(mtype)
            gm.mortar_cooldown = 0
            gm.fire_mortar()
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


def test_mortar_cooldown_and_selection():
    gm = _fresh_game()
    gm.mortar_ammo["bomb"] = 2
    gm.mortar_ammo["acid"] = 1
    gm.select_mortar(g.MORTAR_TYPES.index("acid"))
    assert gm.fire_mortar()
    assert gm.mortar_ammo["acid"] == 0
    assert gm.mortar_shells[-1]["type"] == "acid"
    # Cooldown blocks immediate second shot
    assert not gm.fire_mortar()
    gm.mortar_cooldown = 0
    # Selected type empty -> falls back to a type with ammo
    assert gm.fire_mortar()
    assert gm.mortar_ammo["bomb"] == 1
    assert gm.mortar_shells[-1]["type"] == "bomb"
    # No ammo at all -> refuses
    gm.mortar_cooldown = 0
    gm.mortar_ammo = {t: 0 for t in g.MORTAR_TYPES}
    assert not gm.fire_mortar()


def test_cycle_mortar_wraps():
    gm = _fresh_game()
    gm.mortar_sel = 0
    gm.cycle_mortar(-1)
    assert gm.mortar_sel == len(g.MORTAR_TYPES) - 1
    gm.cycle_mortar(1)
    assert gm.mortar_sel == 0


def test_pickup_collection_effects():
    gm = _fresh_game()
    gm.bricks.clear()
    cases = [
        ("ammo", lambda: gm.gun_ammo),
        ("bomb", lambda: gm.mortar_ammo["bomb"]),
        ("fireball", lambda: gm.fireball_charges),
        ("homing", lambda: gm.homing_charges),
    ]
    for ptype, getter in cases:
        gm.pickups = [{"col": 3, "row": 4, "type": ptype}]
        rect = g.cell_rect(3, 4, "square", gm.brick_offset)
        p = Projectile((rect.centerx, rect.centery), (0, -1))
        before = getter()
        gm._collide_pickups(p)
        assert getter() > before, f"{ptype} pickup had no effect"
        assert not gm.pickups, f"{ptype} pickup not removed"


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


def test_lightning_strikes_random_bricks():
    random.seed(11)
    gm = _fresh_game(wave=20)
    gm.bricks = [Brick(col=c, row=2, hp=100) for c in range(8)]
    gm._trigger_lightning(240.0, 400.0)
    struck = [b for b in gm.bricks if b.hp < 100]
    assert len(struck) == g.LIGHTNING_STRIKES
    assert all(b.hp == 100 - gm.wave for b in struck)
    assert len(gm.lightning_bolts) == 1
    # Bolt path visits trigger point + one center per strike (jagged between)
    assert len(gm.lightning_bolts[0]["points"]) > g.LIGHTNING_STRIKES

    # Lethal strikes remove bricks
    gm2 = _fresh_game(wave=20)
    gm2.bricks = [Brick(col=0, row=2, hp=1), Brick(col=1, row=2, hp=1)]
    gm2._trigger_lightning(240.0, 400.0)
    assert not gm2.bricks


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
    assert tall.hp == 75 + 5  # spawn HP + absorbed brick's HP
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
