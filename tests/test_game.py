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
