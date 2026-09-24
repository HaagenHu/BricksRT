"""BricksRT logic tests. Run with `py -m pytest` or `py tests/test_game.py`."""

import os
import random
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")  # no speakers needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

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
    # The ball doesn't bounce on: it drops straight down, a spent shell
    assert p.alive and p.shell == "mine"
    assert p.vel.x == 0 and p.vel.y > 0
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


def test_hit_flash_shards_and_trail():
    gm = _fresh_game(wave=1)
    # A surviving hit flashes the brick; the flash decays away
    gm.bricks = [Brick(col=3, row=4, hp=5)]
    b = gm.bricks[0]
    rect = g.cell_rect_full(3, 4, "square", gm._brick_off(b))
    p = Projectile((rect.centerx, rect.top), (0, g.PROJECTILE_SPEED))
    gm._collide_bricks(p)
    assert b.hp == 4 and b.hit_t == g.HIT_FLASH_TIME
    for _ in range(6):  # > HIT_FLASH_TIME
        gm.update(1 / 60)
    assert b.hit_t == 0.0

    # A kill bursts into shards that fall and expire
    gm.shards.clear()
    state = random.getstate()
    gm._kill_brick(b)
    assert random.getstate() == state  # effects don't touch gameplay RNG
    lo, hi = g.SHARD_COUNT
    assert lo <= len(gm.shards) <= hi
    gm.bricks = []
    for _ in range(int(g.SHARD_LIFE[1] * 60) + 2):
        gm.update(1 / 60)
    assert not gm.shards

    # Projectiles remember their last TRAIL_LEN positions, oldest first
    p = Projectile((100, 300), (0, -60))
    for _ in range(g.TRAIL_LEN + 3):
        p.update(1 / 60)
    assert len(p.trail) == g.TRAIL_LEN
    assert p.trail[0][1] > p.trail[-1][1]  # moving up: older = lower


def test_explosion_fx_and_shake():
    gm = _fresh_game(wave=10)
    # A blast throws sparks + smoke and shakes the screen, all of which
    # drain away; effects never draw from the gameplay RNG
    gm.bricks = []
    state = random.getstate()
    gm._explode(200, 300)
    assert random.getstate() == state
    assert len(gm.sparks) == g.SPARK_COUNT
    assert len(gm.smoke) == g.SMOKE_PUFFS
    assert gm.shake == g.SHAKE_BOMB
    for _ in range(4):  # chained blasts stack but cap at 1
        gm._explode(200, 300)
    assert gm.shake == 1.0
    for _ in range(int(g.SMOKE_LIFE[1] * 60) + 2):
        gm.update(1 / 60)
    assert not gm.sparks and not gm.smoke and gm.shake == 0.0


def test_sound_cues_emitted():
    gm = _fresh_game(wave=10)
    gm.drain_events()
    # Kill, blast, pickup and mortar launch each queue their cue
    b = Brick(col=3, row=4, hp=1)
    gm.bricks = [b]
    gm._kill_brick(b)
    gm._explode(50, 300)
    gm._collect_pickup("ammo")
    gm.ammo_inv["bomb"] = 1
    gm.select_mortar(g.AMMO_TYPES.index("bomb"))
    gm.mortar_cooldown = 0
    assert gm.fire_mortar()
    ev = gm.drain_events()
    for cue in ("kill", "explode", "pickup", "mortar_launch"):
        assert cue in ev, cue
    assert gm.drain_events() == []  # draining empties the queue
    # Undrained (no frontend), the queue stays bounded
    for _ in range(g.EVENT_MAX * 3):
        gm._emit("kill")
    assert len(gm.events) == g.EVENT_MAX


def test_sound_player():
    import sound
    try:
        pygame.mixer.init(sound.MIX_RATE, -16, 1, sound.MIX_BUFFER)
    except pygame.error:
        print("    (no audio driver - skipped)")
        return
    try:
        sfx = sound.Sounds()
        assert sfx.enabled
        # Every cue the game emits has a sound
        cues = ("kill", "explode", "mortar_launch", "mine_set", "acid",
                "tar", "wall_up", "wall_break", "pickup", "freeze",
                "reverse", "lightning", "skull", "gameover", "new_best",
                "shield_break", "paddle_up", "paddle_break")
        for cue in cues:
            assert sfx.cues[cue], cue
            assert all(s.get_length() > 0 for s in sfx.cues[cue])
        # Kills are rate-limited: a second burst 30ms later is dropped
        sfx.play_events(["kill"] * 5, now=10.0)
        assert sfx._last["kill"] == 10.0
        sfx.play_events(["kill"], now=10.03)
        assert sfx._last["kill"] == 10.0
        sfx.play_events(["kill"], now=10.1)
        assert sfx._last["kill"] == 10.1
        # Muted: nothing plays, nothing is recorded
        sfx.toggle_mute()
        sfx.play_events(["pickup"], now=11.0)
        assert "pickup" not in sfx._last
        sfx.play_events(["unknown_cue"], now=12.0)  # ignored, no crash
    finally:
        pygame.mixer.quit()


def test_trapezoid_orientations():
    # All four orientations spawn once trapezoids unlock
    dirs = set()
    for seed in range(300):
        random.seed(seed)
        gm = _fresh_game(wave=g.UNLOCK["trapezoid"])
        gm.bricks = []
        gm.spawn_wave()
        dirs |= {b.tri_dir for b in gm.bricks if b.shape == "trapezoid"}
    assert dirs == {"up", "down", "left", "right"}

    # Left/right: a ball rising near the bottom-left corner hits the
    # full-height left side of a right-pointing trapezoid, but is still
    # below the slanted underside of a left-pointing one
    def hits_low_left(tri_dir):
        gm = _fresh_game(wave=40)
        b = Brick(col=3, row=4, hp=10, shape="trapezoid", tri_dir=tri_dir)
        gm.bricks = [b]
        cx, cy = g.cell_rect(3, 4, "square", gm._brick_off(b)).center
        h = g.BRICK_SIZE / 2
        p = Projectile((cx - 0.9 * h, cy + 0.9 * h), (0, -g.PROJECTILE_SPEED))
        return gm._collide_trapezoid(p, b, gm._brick_off(b))

    assert hits_low_left("right")
    assert not hits_low_left("left")
    # Both wrap their shield band around the corners (curl)
    for d in ("left", "right"):
        assert g.shield_wraps("trapezoid", d) and not g.shield_half(
            "trapezoid", d)

    # Collision follows the orientation: a ball rising into the bottom
    # corner hits the wide base of an upright trapezoid, but passes the
    # narrow base of an upside-down one
    def rises_into_corner(tri_dir):
        gm = _fresh_game(wave=40)
        b = Brick(col=3, row=4, hp=10, shape="trapezoid", tri_dir=tri_dir)
        gm.bricks = [b]
        rect = g.cell_rect(3, 4, "square", gm._brick_off(b))
        x = rect.centerx + g.BRICK_SIZE * 0.42
        p = Projectile((x, rect.bottom + 2), (0, -g.PROJECTILE_SPEED))
        return gm._collide_trapezoid(p, b, gm._brick_off(b))

    assert rises_into_corner("up")
    assert not rises_into_corner("down")


def test_shield_covers_its_band():
    """Shields block exactly where the band is drawn: downward faces,
    plus the wrap around the end corners on wrapping shapes."""
    R, S = g.PROJECTILE_RADIUS, g.PROJECTILE_SPEED
    tri_n = (2 / 5 ** 0.5, 1 / 5 ** 0.5)        # tri-down right face
    trap_n = (2 / 4.16 ** 0.5, 0.4 / 4.16 ** 0.5)  # trap-down right face
    # name -> (point on the face in half-size units, its outward normal)
    FACE_POINTS = {
        "tri_upper": ((0.75, -0.5), tri_n), "tri_lower": ((0.25, 0.5), tri_n),
        "trap_upper": ((0.9, -0.5), trap_n),
        "trap_lower": ((0.7, 0.5), trap_n),
    }

    def strike(shape, tri_dir, where):
        """Fire one ball at the brick; 'shield' or 'hp' took the hit."""
        gm = _fresh_game(wave=60)
        b = Brick(col=3, row=4, hp=10, shield=5, shape=shape, tri_dir=tri_dir)
        gm.bricks = [b]
        off = gm._brick_off(b)
        full = g.cell_rect_full(3, 4, shape, off)
        cx, cy = g.cell_rect(3, 4, "square", off).center
        h = g.BRICK_SIZE / 2
        # Rect bricks collide on the full cell; others on their outline
        right = full.right if shape == "square" else cx + h
        top = full.top if shape == "square" else cy - h
        if where == "below":        # straight up into the underside
            pos, vel = (cx, cy + h + R - 1), (0, -S)
        elif where == "top":        # falling onto the top
            pos, vel = (cx, top - R + 1), (0, S)
        elif where == "side_low":   # into the right side, near the bottom
            pos, vel = (right + R - 1, full.bottom - 4), (-S, 0)
        elif where == "side_mid":   # into the right side, halfway up
            pos, vel = (right + R - 1, cy), (-S, 0)
        elif where in FACE_POINTS:  # into a face, along its normal
            (fx, fy), n = FACE_POINTS[where]
            px, py = cx + fx * h, cy + fy * h
            pos = (px + n[0] * (R - 1), py + n[1] * (R - 1))
            vel = (-n[0] * S, -n[1] * S)
        p = Projectile(pos, vel)
        gm._collide_bricks(p)
        assert (b.shield, b.hp) != (5, 10), f"{shape} {where}: no hit"
        return "shield" if b.shield < 5 else "hp"

    assert strike("square", "up", "below") == "shield"
    assert strike("square", "up", "side_low") == "shield"  # corner wrap
    assert strike("square", "up", "side_mid") == "hp"
    assert strike("square", "up", "top") == "hp"
    assert strike("round", "up", "below") == "shield"
    assert strike("round", "up", "side_mid") == "hp"
    # Downward triangle / trapezoid: the band stops at the center line,
    # so only the lower half of the slanted faces is covered
    assert strike("triangle", "down", "tri_lower") == "shield"
    assert strike("triangle", "down", "tri_upper") == "hp"
    assert strike("triangle", "down", "top") == "hp"
    assert strike("trapezoid", "down", "trap_lower") == "shield"
    assert strike("trapezoid", "down", "trap_upper") == "hp"
    assert strike("trapezoid", "down", "below") == "shield"
    # Left-pointing triangle: its band wraps up the right side at the
    # bottom corner now, so a side hit low on that edge is shielded,
    # one halfway up is not
    assert strike("triangle", "left", "side_low") == "shield"
    assert strike("triangle", "left", "side_mid") == "hp"
    # Upward triangle wraps up its slants at the bottom corners; the
    # downward one is a plain V (nothing below its top corners to wrap)
    assert strike("triangle", "up", "side_low") == "shield"
    for d in ("up", "left", "right"):
        assert g.shield_wraps("triangle", d), d
    assert g.shield_wraps("trapezoid", "up")
    for s in ("triangle", "trapezoid"):
        assert not g.shield_wraps(s, "down") and g.shield_half(s, "down")
    assert not g.shield_wraps("round", "up")


def test_shield_flash_and_break():
    gm = _fresh_game(wave=60)
    b = Brick(col=3, row=4, hp=50, shield=2)
    gm.bricks, gm.pickups = [b], []
    gm.update(1 / 60)  # first frame just records the shield
    assert b.shield_hit_t == 0.0
    gm.drain_events()

    b.shield -= 1  # any source: absorbed one hit
    gm.update(1 / 60)
    assert b.shield_hit_t > 0 and "shield_break" not in gm.drain_events()
    sparks = len(gm.sparks)

    b.shield = 0  # worn through
    gm.update(1 / 60)
    assert "shield_break" in gm.drain_events()
    assert len(gm.sparks) > sparks  # burst along the edge
    for _ in range(30):
        gm.update(1 / 60)
    assert b.shield_hit_t == 0.0
    assert "shield_break" not in gm.drain_events()  # breaks only once


def _paddle(gm, x=240.0, y=400.0, deg=0.0, kind="still", turn=0.0):
    pd = {"x": x, "y": y, "angle": g.math.radians(deg),
          "timer": g.PADDLE_LIFE, "flash": 0.0, "kind": kind, "turn": turn}
    gm.paddles = [pd]
    return pd


def test_paddle_kinds_turn():
    gm = _fresh_game(wave=60)
    gm.bricks, gm.pickups = [], []
    # Spinner turns steadily
    spin = g.math.radians(g.PADDLE_SPIN)
    pd = _paddle(gm, kind="spin", turn=spin)
    for _ in range(30):  # 0.5s
        gm.update(1 / 60)
    assert abs(pd["angle"] - spin * 0.5) < 1e-6
    # Kicker only turns when hit, one notch per hit, same way each time
    kick = -g.math.radians(g.PADDLE_KICK)
    pd = _paddle(gm, kind="kick", turn=kick)
    gm.update(1 / 60)
    assert pd["angle"] == 0.0
    for n in (1, 2):
        p = Projectile((240, 400), (0, -g.PROJECTILE_SPEED))
        p.prev.update(240, 412)
        gm._collide_paddles(p)
        assert abs(pd["angle"] - kick * n) < 1e-9
    # All three kinds show up
    kinds = set()
    for seed in range(300):
        random.seed(seed)
        gm2 = _fresh_game(wave=g.UNLOCK["paddle"] + 5)
        gm2.spawn_wave()
        kinds |= {p["kind"] for p in gm2.paddles}
    assert kinds == {"still", "spin", "kick"}


def test_paddle_spawns_from_its_wave_clear_of_bricks():
    seen_early = seen_late = 0
    for seed in range(200):
        random.seed(seed)
        early = _fresh_game(wave=g.UNLOCK["paddle"] - 2)
        early.spawn_wave()  # -> unlock wave - 1: never
        seen_early += len(early.paddles)
        late = _fresh_game(wave=g.UNLOCK["paddle"] + 5)
        late.spawn_wave()
        seen_late += len(late.paddles)
        for pd in late.paddles:
            assert not late._paddle_blocked(pd, margin=0)
            assert g.GRID_TOP < pd["y"] < g.GRID_BOTTOM - g.CELL_SIZE
            assert abs(g.math.degrees(pd["angle"])) <= g.PADDLE_MAX_TILT
    assert seen_early == 0
    # ~PADDLE_CHANCE of waves (loose bounds for 200 samples)
    assert 0.5 * g.PADDLE_CHANCE < seen_late / 200 < 1.6 * g.PADDLE_CHANCE


def test_paddle_mirror_bounce():
    S = g.PROJECTILE_SPEED
    gm = _fresh_game(wave=60)
    gm.bricks = []
    # Flat paddle, ball rising into its underside: vy flips, vx kept
    pd = _paddle(gm, deg=0)
    p = Projectile((250, 400 + g.PROJECTILE_RADIUS - 1), (100, -S))
    p.prev.update(250, 420)
    gm._collide_paddles(p)
    assert p.vel.y > 0 and p.vel.x == 100
    assert p.pos.y > 400  # pushed back out below
    assert p.border_hits == 1 and pd["flash"] > 0  # counts vs anti-loop
    # 45 degree paddle turns a straight-up shot sideways
    _paddle(gm, deg=45)
    p = Projectile((240, 400), (0, -S))
    p.prev.update(240, 412)
    gm._collide_paddles(p)
    assert abs(p.vel.y) < 1e-6 and abs(abs(p.vel.x) - S) < 1e-6
    # Swept: a shot that jumped clean through the bar this frame still
    # bounces (no tunnelling), off the side it came from
    _paddle(gm, deg=0)
    p = Projectile((240, 380), (0, -S))  # now 20px above the paddle
    p.prev.update(240, 420)              # was 20px below it
    gm._collide_paddles(p)
    assert p.vel.y > 0 and p.pos.y > 400
    # Missing the bar's end: no bounce
    p = Projectile((240 + g.PADDLE_LEN, 400), (0, -S))
    p.prev.update(240 + g.PADDLE_LEN, 420)
    gm._collide_paddles(p)
    assert p.vel.y < 0


def test_paddle_overrun_expiry_and_shells():
    gm = _fresh_game(wave=60)
    gm.bricks, gm.pickups = [], []
    gm.drain_events()
    # Overrun: a brick covering it shatters it at once
    rect = g.cell_rect_full(3, 5, "square", gm.brick_offset)
    _paddle(gm, x=rect.centerx, y=rect.centery)
    gm.bricks = [Brick(col=3, row=5, hp=10)]
    gm.update(1 / 60)
    assert not gm.paddles and "paddle_break" in gm.drain_events()
    # Expiry after PADDLE_LIFE
    gm.bricks = []
    _paddle(gm)
    for _ in range(round(g.PADDLE_LIFE * 60) + 2):
        gm.freeze_timer = 1.0  # keep new rows from spawning mid-test
        gm.update(1 / 60)
    assert not gm.paddles
    # Spent shells fall straight through
    _paddle(gm, deg=0)
    p = Projectile((240, 380), (0, 0))
    g.Game._spend(p, "acid")
    gm.projectiles = [p]
    for _ in range(30):
        gm.update(1 / 60)
    assert p.pos.y > 400 and p.vel.y > 0


def test_reload_feeder_caps_rate():
    gm = _fresh_game(wave=5)
    gm.bricks, gm.pickups = [], []
    gm.gun_ammo = 0
    gm.gun_reloading = 30  # a big volley just came back at once
    assert gm.gun_reloading == 30

    def run(seconds):
        for _ in range(round(seconds * 60)):
            gm.update(1 / 60)

    run(g.GUN_RELOAD_DELAY - 0.1)
    assert gm.gun_ammo == 0  # still inside the delay
    run(0.1 + 1.0)  # delay over, then one second of feeding
    assert abs(gm.gun_ammo - g.GUN_FEED_RATE) <= 1  # ~10, not all 30
    assert gm.gun_reloading == 30 - gm.gun_ammo
    run(30 / g.GUN_FEED_RATE)
    assert gm.gun_ammo == 30 and gm.gun_reloading == 0

    # Idling can't bank a burst: after a long pause, a fresh batch still
    # feeds at the rate
    run(5.0)
    gm.gun_ammo = 0
    gm.gun_reloading = 20
    run(g.GUN_RELOAD_DELAY + 0.5)
    assert gm.gun_ammo <= g.GUN_FEED_RATE * 0.5 + 1


def test_extra_ball_chance_tapers():
    assert g.extra_ball_chance(1) == g.EXTRA_BALL_CHANCE_START
    end = g.EXTRA_BALL_CHANCE_END
    assert abs(g.extra_ball_chance(g.EXTRA_BALL_TAPER_WAVES) - end) < 1e-9
    assert g.extra_ball_chance(500) == end  # flat after the taper
    chances = [g.extra_ball_chance(w) for w in range(1, 120)]
    assert all(a >= b for a, b in zip(chances, chances[1:]))  # never rises


def test_practice_start():
    gm = Game()
    gm.start(60)
    assert gm.practice and gm.wave == 60
    assert gm.bricks and all(b.hp >= 60 for b in gm.bricks)  # wave HP
    # 1 starting ball + the expected extra balls of waves 1..59
    expected = sum(g.extra_ball_chance(w) for w in range(1, 60))
    assert gm.gun_ammo == 1 + round(expected)
    for t in g.AMMO_TYPES:  # stock of exactly the types unlocked by 60
        expect = g.PRACTICE_STOCK if 60 >= g.PICKUP_UNLOCK[t] else 0
        assert gm.ammo_inv[t] == expect, t
    # Never records a highscore, however far it gets
    gm.highscore = 5
    gm.save_if_record()
    assert gm.highscore == 5 and not gm.new_best
    # A normal start clears practice mode
    gm.start()
    assert not gm.practice and gm.wave == 1


def test_gun_kick_on_fire():
    gm = _fresh_game(wave=1)
    gm.gun_cooldown = 0
    assert gm.gun_kick == 0.0
    assert gm.fire_gun()
    assert gm.gun_kick == g.GUN_KICK_TIME
    # Recoil settles before the next shot is allowed, so held fire pulses
    assert g.GUN_KICK_TIME < g.GUN_COOLDOWN
    for _ in range(int(g.GUN_KICK_TIME * 60) + 1):
        gm.update(1 / 60)
    assert gm.gun_kick == 0.0


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
    # Route: trigger point, then each struck center, nearest-first
    nodes = gm.lightning_bolts[0]["nodes"]
    assert len(nodes) == g.LIGHTNING_STRIKES + 1
    assert nodes[0] == (240.0, 400.0)
    hop = lambda a, b: ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5  # noqa
    for i in range(1, len(nodes) - 1):  # each hop is the shortest left
        assert all(hop(nodes[i - 1], nodes[i]) <= hop(nodes[i - 1], n) + 1e-9
                   for n in nodes[i + 1:])
    assert all(b.zap_t == g.LIGHTNING_STUN for b in struck)
    assert gm.lightning_flash == g.LIGHTNING_FLASH_TIME
    # Visuals don't consume the gameplay RNG
    state = random.getstate()
    gm._trigger_lightning(240.0, 400.0)
    after = random.getstate()
    random.setstate(state)
    random.sample(gm.bricks, min(g.LIGHTNING_STRIKES, len(gm.bricks)))
    assert random.getstate() == after  # only the target pick used it

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
    assert p.shell == "acid" and p.vel.x == 0  # spent: drops, no bounce
    # First burn tick (2 dmg, 1s in) takes the last 2 hp
    for _ in range(66):
        gm.update(1 / 60)
    assert b not in gm.bricks


def test_spent_shell_falls_through_everything():
    gm = _fresh_game(wave=60)
    below = Brick(col=3, row=6, hp=10)
    gm.bricks, gm.pickups = [below], [{"col": 3, "row": 5, "type": "ammo"}]
    rect = g.cell_rect(3, 3, "square", gm.brick_offset)
    p = Projectile((rect.centerx, rect.centery), (0, 0))
    g.Game._spend(p, "acid")
    gm.projectiles = [p]
    gm.gun_ammo = 0
    for _ in range(240):  # 4s: long enough to fall out
        gm.update(1 / 60)
        if not p.alive:
            break
    assert not p.alive and p.exited_bottom
    assert below.hp == 10              # passed through the brick below
    assert len(gm.pickups) == 1        # didn't collect the pickup
    assert gm.gun_reloading + gm.gun_ammo == 1  # still returns to pool


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
    # Acid zone tick melts shield BEFORE hp, at double rate against
    # shields (wave 20 -> max(1, 20 // 15) = 1 per tick -> 2 off)
    pool = max(1, gm.wave // g.ACID_POOL_DIV)
    gm.placed_acids = [{"x": rect.centerx, "y": rect.centery,
                        "timer": 5.0, "tick": 0.0}]
    b.shield = 5
    hp2 = b.hp
    gm._update_acids(0.01)
    assert b.shield == 5 - pool * g.ACID_SHIELD_MULT and b.hp == hp2
    b.shield = 1
    gm.placed_acids[0]["tick"] = 0.0
    gm._update_acids(0.01)  # finishing the shield doesn't spill onto hp
    assert b.shield == 0 and b.hp == hp2
    # Acid-bullet burn, 1 tick/s: each tick takes 2x its damage off the
    # shield, then ACIDSHOT_TICK_DMG hp once it's gone
    b.shield = 3
    b.acid_dot = g.ACIDSHOT_DOT
    b.acid_tick = 0.0
    gm.placed_acids.clear()
    hp3 = b.hp
    for _ in range(70):  # ~1.17s: one tick (3 - 2*2 -> 0), all on shield
        gm.update(1 / 60)
    assert b.shield == 0 and b.hp == hp3
    for _ in range(56):  # ~2.1s: the second tick reaches hp
        gm.update(1 / 60)
    assert b.hp == hp3 - g.ACIDSHOT_TICK_DMG
    for _ in range(60):  # ~3.1s: the third and last tick lands on time
        gm.update(1 / 60)
    assert b.hp == hp3 - 2 * g.ACIDSHOT_TICK_DMG and b.acid_dot == 0


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


def test_wall_blocks_fast_steps():
    """A shot whose frame step carries it past the wall line (or right
    over the thin catch band) still bounces back — no leaks, at 60 fps
    or on a 30 fps hitch, from either side."""
    for dt in (1 / 60, 1 / 30):
        for direction in (-1, 1):  # rising from below / falling onto it
            for k in range(40):
                gm = _fresh_game()
                gm.bricks, gm.pickups = [], []
                wall = {"y": 400.0, "max_weight": 10**6, "grace": 0.0,
                        "ttl": 99.0}
                gm.placed_walls = [wall]
                start = 400.0 - direction * (60 + k * 0.37)
                p = Projectile((240.0, start),
                               (0.0, direction * g.PROJECTILE_SPEED))
                for _ in range(20):
                    p.update(dt)
                    gm._collide_walls(p)
                assert (p.pos.y - 400.0) * direction < 0, (dt, direction, k)
                assert wall["max_weight"] == 10**6 - 1  # exactly one bounce


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
