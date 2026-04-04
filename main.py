"""Ballz-style brick breaker game built with Pygame."""

import json
import math
import os
import random
import pygame

# ---------------------------------------------------------------------------
# High score persistence
# ---------------------------------------------------------------------------
HIGHSCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "highscores.json")


def _load_all() -> dict:
    try:
        with open(HIGHSCORE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def load_highscore(mode: str) -> int:
    return _load_all().get(mode, 0)


def save_highscore(mode: str, score: int):
    data = _load_all()
    data[mode] = score
    with open(HIGHSCORE_FILE, "w") as f:
        json.dump(data, f)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 480, 720
FPS = 60
COLS = 8
TOP_UI_HEIGHT = 50
BOTTOM_AREA_HEIGHT = 60
GRID_TOP = TOP_UI_HEIGHT
GRID_BOTTOM = HEIGHT - BOTTOM_AREA_HEIGHT
CELL_SIZE = WIDTH // COLS
BRICK_GAP = 2
BRICK_SIZE = CELL_SIZE - BRICK_GAP * 2
MAX_ROWS = (GRID_BOTTOM - GRID_TOP) // CELL_SIZE

# Unlock levels
UNLOCK = {
    "bombs": 10, "shapes": 25, "lightning": 40, "cage": 40,
    "fireball": 60, "paddle": 60, "hexagon": 80, "trapezoid": 80,
    "wide": 80, "laser": 110, "freeze": 110, "triangle": 140,
    "homing": 140, "shields": 170, "merging": 190, "skull": 200,
    "skull_interval": 200, "acid": 250, "wall": 300,
}

BALL_RADIUS = 5
BALL_SPEED = 10  # px per frame
FIRE_DELAY = 0.10  # seconds between successive ball launches

# Colors
BG_COLOR = (20, 20, 30)
TEXT_COLOR = (255, 255, 255)
AIM_DOT_COLOR = (200, 200, 200)
COLLECTIBLE_COLOR = (100, 255, 130)
BOMB_COLOR = (255, 80, 50)
CAGE_COLOR = (180, 120, 255)
LIGHTNING_COLOR = (100, 200, 255)
PADDLE_COLOR = (255, 200, 100)
FIREBALL_COLOR = (255, 100, 0)
FIREBALL_GLOW = (255, 200, 50)
SKULL_COLOR = (180, 50, 180)
LASER_H_COLOR = (255, 50, 50)
LASER_V_COLOR = (50, 150, 255)
FREEZE_COLOR = (150, 230, 255)
HOMING_COLOR = (0, 255, 150)
SHIELD_COLOR = (0, 220, 255)
ACID_COLOR = (120, 255, 0)
WALL_COLOR = (255, 160, 40)
PADDLE_LENGTH = BRICK_SIZE * 0.8
PADDLE_THICKNESS = 4
BOMB_RADIUS_CELLS = 1.5  # explosion radius in cell units
GAMEOVER_OVERLAY = (0, 0, 0, 180)

import colorsys


def brick_color(hp: int) -> tuple[int, int, int]:
    """Map HP to a smooth rainbow gradient. Low HP = green, high HP = red/violet."""
    # Hue goes from 0.33 (green) down through yellow, orange, red, to 0.83 (violet)
    # Normalize: HP 1 = green end, higher HP moves toward violet
    # Use a log scale so early levels change faster and high levels change slowly
    t = min(1.0, math.log(1 + hp) / math.log(1 + 100))  # saturates around HP 100
    # Hue: green (0.33) -> yellow (0.16) -> red (0.0) -> pink/violet (0.83)
    # We go green -> red -> violet: 0.33 -> 0.0 -> -0.17 (wrapped to 0.83)
    hue = 0.33 - t * 0.5
    if hue < 0:
        hue += 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.95)
    return (int(r * 255), int(g * 255), int(b * 255))


# Brick shapes: "square", "wide" (2 cols), "round" (circle)

# ---------------------------------------------------------------------------
# Helper: grid position <-> pixel rect
# ---------------------------------------------------------------------------

def cell_rect(col: int, row: int, shape: str = "square", y_offset: float = 0) -> pygame.Rect:
    """Return the pixel Rect for a brick at (col, row) in the grid (visual, with gaps)."""
    x = col * CELL_SIZE + BRICK_GAP
    y = GRID_TOP + row * CELL_SIZE + BRICK_GAP + y_offset
    if shape == "wide":
        return pygame.Rect(x, y, CELL_SIZE * 2 - BRICK_GAP * 2, BRICK_SIZE)
    if shape == "tall":
        return pygame.Rect(x, y, BRICK_SIZE, CELL_SIZE * 2 - BRICK_GAP * 2)
    return pygame.Rect(x, y, BRICK_SIZE, BRICK_SIZE)


def cell_rect_full(col: int, row: int, shape: str = "square") -> pygame.Rect:
    """Return the full cell Rect (no gaps) for collision detection."""
    x = col * CELL_SIZE
    y = GRID_TOP + row * CELL_SIZE
    if shape == "wide":
        return pygame.Rect(x, y, CELL_SIZE * 2, CELL_SIZE)
    if shape == "tall":
        return pygame.Rect(x, y, CELL_SIZE, CELL_SIZE * 2)
    return pygame.Rect(x, y, CELL_SIZE, CELL_SIZE)


# ---------------------------------------------------------------------------
# Ball class
# ---------------------------------------------------------------------------

class Ball:
    def __init__(self, pos: pygame.math.Vector2, vel: pygame.math.Vector2):
        self.pos = pygame.math.Vector2(pos)
        self.vel = pygame.math.Vector2(vel)
        self.alive = True  # still moving
        self.border_hits = 0  # consecutive border bounces without hitting a brick
        self.cage_immune = 0  # frames of immunity from cage capture
        self.fireball = False  # passes through bricks
        self.fireball_in_bricks = False  # currently passing through bricks
        self.homing = False  # gently seeks nearest brick
        self.homing_timer = 0.0  # seconds remaining

    def update(self, speed_mult: float = 1.0):
        if not self.alive:
            return
        self.pos += self.vel * speed_mult

        # Wall reflections (left / right)
        if self.pos.x - BALL_RADIUS < 0:
            self.pos.x = BALL_RADIUS
            self.vel.x = abs(self.vel.x)
            self.border_hits += 1
        elif self.pos.x + BALL_RADIUS > WIDTH:
            self.pos.x = WIDTH - BALL_RADIUS
            self.vel.x = -abs(self.vel.x)
            self.border_hits += 1

        # Ceiling reflection
        if self.pos.y - BALL_RADIUS < TOP_UI_HEIGHT:
            self.pos.y = TOP_UI_HEIGHT + BALL_RADIUS
            self.vel.y = abs(self.vel.y)
            self.border_hits += 1

        # Floor — ball stops
        if self.pos.y + BALL_RADIUS >= HEIGHT - BOTTOM_AREA_HEIGHT:
            self.pos.y = HEIGHT - BOTTOM_AREA_HEIGHT - BALL_RADIUS
            self.alive = False


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------

def _apply_gravity(ball: Ball):
    """Nudge ball 0.1 degrees toward straight down."""
    current_angle = math.atan2(ball.vel.y, ball.vel.x)
    target = math.pi / 2
    diff = target - current_angle
    while diff > math.pi:
        diff -= 2 * math.pi
    while diff < -math.pi:
        diff += 2 * math.pi
    pull = max(-math.radians(0.1), min(math.radians(0.1), diff))
    new_angle = current_angle + pull
    speed = ball.vel.length()
    ball.vel.x = math.cos(new_angle) * speed
    ball.vel.y = math.sin(new_angle) * speed


class Game:
    def __init__(self):
        self.mode = "classic"  # "classic" or "advanced"
        self.highscore = load_highscore(self.mode)
        self.reset()

    def reset(self):
        self.round = 0
        self.ball_count = 1
        self.highscore = load_highscore(self.mode)
        self.hp_level = 0  # effective HP for new bricks (halved by skull)
        self.launch_x: float = WIDTH / 2
        self.bricks: list[dict] = []       # {col, row, hp, shape}
        self.collectibles: list[dict] = []  # {col, row}
        self.bombs: list[dict] = []         # {col, row}
        self.cages: list[dict] = []         # {col, row, hp, captured, timer, active}
        self.lightnings: list[dict] = []    # {col, row, hp}
        self.paddles: list[dict] = []       # {col, row, angle, speed, rounds_left}
        self.fireballs: list[dict] = []     # {col, row, charges}
        self.skulls: list[dict] = []        # {col, row}
        self.lasers: list[dict] = []        # {col, row, hp, direction} "h" or "v"
        self.freezes: list[dict] = []       # {col, row}
        self.acids: list[dict] = []         # {col, row}
        self.wall_pus: list[dict] = []      # {col, row} PU on field
        self.walls: list[dict] = []         # {col, row, hp} active walls
        self.acid_active = False            # bricks losing HP over time
        self.acid_timer = 0.0               # time until next acid tick
        self.acid_duration = 0.0            # seconds remaining
        self.acid_center = (0, 0)           # center of acid effect
        self.acid_bricks: set = set()       # ids of affected bricks
        self.homings: list[dict] = []       # {col, row, charges}
        self.frozen_rounds = 0              # rounds to skip advance
        self.is_frozen_round = False        # currently in a frozen round
        self.freeze_wave: dict | None = None  # {x, y, radius, max_radius, speed}
        self.laser_beams: list[dict] = []   # {x, y, direction, timer} for visual
        self.explosions: list[dict] = []    # {x, y, timer} for visual effect
        self.lightning_bolts: list[dict] = []  # {x1,y1,x2,y2,timer} for visual
        self.lightning_queue: list[dict] = []  # {lx, ly, strikes, damage, delay}
        self.balls: list[Ball] = []
        self.phase = "menu"  # menu | spawn | aim | fire | running | gameover
        self.fire_timer = 0.0
        self.balls_to_fire = 0
        self.aim_angle: float = -math.pi / 2  # straight up
        self.first_landed_x: float | None = None
        self.pending_collect = 0  # collectibles picked up this round
        self.round_hits = 0      # brick hits this round
        self.round_balls = 0     # balls at start of round
        self.last_efficiency: float = 0.0  # hits/balls ratio from last round
        self.bonus_text_timer = 0.0  # countdown for bonus text display
        self.bonus_extra_ball = False  # spawn extra collectible next round
        self.skull_flash = 0.0  # full board flash timer
        self.unlock_text = ""   # "NEW: X unlocked!"
        self.unlock_timer = 0.0
        self.skull_wave: dict | None = None  # {x, y, radius, max_radius, speed}
        self.advance_anim = 0.0  # 0 = no animation, >0 = animating (counts down)
        self.advance_duration = 0.3  # seconds for advance animation

    # ------------------------------------------------------------------
    # Phase: spawn + advance
    # ------------------------------------------------------------------

    def start_round(self):
        self.first_landed_x = None
        self.pending_collect = 0
        self.round_hits = 0
        self._board_clear_spawned = not self.bricks  # True if starting with no bricks
        self.acid_active = False
        self.acid_timer = 0.0
        self.acid_duration = 0.0
        self.acid_bricks.clear()
        self.round_balls = self.ball_count

        # Frozen round: no advance, no new bricks, no round/hp increment, no +ball
        if self.frozen_rounds > 0:
            self.frozen_rounds -= 1
            self.is_frozen_round = True
            # Honor bonus collectible from previous board clear
            if self.bonus_extra_ball:
                self.bonus_extra_ball = False
                occupied = self._build_occupied()
                all_empty = [(c, r) for r in range(1, MAX_ROWS) for c in range(COLS)
                             if (c, r) not in occupied]
                if all_empty:
                    bc, br = random.choice(all_empty)
                    self.collectibles.append({"col": bc, "row": br})
            self.phase = "aim"
            return

        self.is_frozen_round = False
        self.round += 1
        self.hp_level += 1

        # Check for unlocks (not in simple mode)
        unlocks = {
            UNLOCK["bombs"]: "Bombs", UNLOCK["shapes"]: "New shapes",
            UNLOCK["lightning"]: "Lightning & Cage",
            UNLOCK["fireball"]: "Fireball & Paddle",
            UNLOCK["hexagon"]: "Hexagon & Trapezoid",
            UNLOCK["laser"]: "Laser & Freeze",
            UNLOCK["triangle"]: "Triangle & Homing",
            UNLOCK["shields"]: "Shields", UNLOCK["merging"]: "Brick merging",
            UNLOCK["skull"]: "Skull", UNLOCK["acid"]: "Acid",
            UNLOCK["wall"]: "Wall Blocker",
        }
        if self.mode != "simple" and self.round in unlocks:
            self.unlock_text = f"NEW: {unlocks[self.round]}!"
            self.unlock_timer = 2.5

        # Spawn new row at row 0
        cols = list(range(COLS))
        random.shuffle(cols)
        brick_count = random.randint(3, 6)
        brick_cols = sorted(cols[:brick_count])
        remaining = [c for c in cols if c not in brick_cols]

        if self.mode in ("classic", "simple"):
            for c in brick_cols:
                brick = {"col": c, "row": 0, "hp": max(1, self.hp_level), "shape": "square"}
                if self.round >= UNLOCK["shields"] and random.random() < 0.15:
                    brick["shield"] = max(2, self.round // 5)
                self.bricks.append(brick)
        else:
            # Advanced: mix of square, wide, round
            occupied = set()
            for c in brick_cols:
                if c in occupied:
                    continue
                # Shapes unlock with progression
                shapes = ["square"]
                weights = [30]
                if self.round >= UNLOCK["shapes"]:
                    shapes += ["round", "diamond"]
                    weights += [18, 13]
                if self.round >= UNLOCK["hexagon"]:
                    shapes += ["hexagon", "trapezoid"]
                    weights += [13, 14]
                    shapes.append("wide")
                    weights.append(12)
                if self.round >= UNLOCK["triangle"]:
                    shapes += ["triangle"]
                    weights += [18]
                shape = random.choices(shapes, weights=weights)[0]
                # Wide needs an adjacent free column
                if shape == "wide" and c + 1 < COLS and c + 1 not in occupied and c + 1 not in brick_cols:
                    occupied.add(c)
                    occupied.add(c + 1)
                    # Remove c+1 from remaining if present
                    if c + 1 in remaining:
                        remaining.remove(c + 1)
                elif shape == "wide":
                    shape = "square"  # fallback
                if shape != "wide":
                    occupied.add(c)
                base_hp = max(1, self.hp_level)
                hp = base_hp * 2 if shape == "wide" else base_hp
                brick = {"col": c, "row": 0, "hp": hp, "shape": shape}
                if shape == "triangle":
                    brick["tri_dir"] = random.choice(["up", "down", "left", "right"])
                if self.round >= UNLOCK["shields"] and shape in ("square", "wide", "tall", "trapezoid", "round", "diamond", "triangle") and random.random() < 0.15:
                    brick["shield"] = max(2, self.round // 5)
                self.bricks.append(brick)

        # Advance everything down by 1 row (start animation)
        self.advance_anim = self.advance_duration
        # Build wall positions for blocking
        wall_blocks = {}  # col -> lowest wall row
        for w in self.walls:
            c = w["col"]
            if c not in wall_blocks or w["row"] < wall_blocks[c]:
                wall_blocks[c] = w["row"]
        for b in self.bricks:
            new_row = b["row"] + 1
            shape = b.get("shape", "square")
            # Check if any column this brick occupies is blocked
            cols_occupied = [b["col"]]
            if shape == "wide":
                cols_occupied.append(b["col"] + 1)
            blocked = False
            for c in cols_occupied:
                if c in wall_blocks and new_row >= wall_blocks[c]:
                    blocked = True
                    break
            if not blocked:
                b["row"] = new_row
        for c in self.collectibles:
            c["row"] += 1
        # Bombs don't advance — but get pushed down if a brick lands on them
        brick_cells = set()
        for b in self.bricks:
            brick_cells.add((b["col"], b["row"]))
            if b.get("shape") == "wide":
                brick_cells.add((b["col"] + 1, b["row"]))
            if b.get("shape") == "tall":
                brick_cells.add((b["col"], b["row"] + 1))
        for b in self.bombs:
            while (b["col"], b["row"]) in brick_cells:
                b["row"] += 1
        for lg in self.lightnings:
            lg["row"] += 1
        for cg in self.cages:
            cg["row"] += 1
        for pd in self.paddles:
            pd["row"] += 1
            pd["rounds_left"] -= 1
        self.paddles = [p for p in self.paddles if p["rounds_left"] > 0]
        for fb in self.fireballs:
            fb["row"] += 1
        for sk in self.skulls:
            sk["row"] += 1
        for ls in self.lasers:
            ls["row"] += 1
        for fz in self.freezes:
            fz["row"] += 1
        # Acids don't advance — pushed down by bricks like bombs
        for ac in self.acids:
            while (ac["col"], ac["row"]) in brick_cells:
                ac["row"] += 1
        # Wall PUs don't advance — pushed by bricks
        for wp in self.wall_pus:
            while (wp["col"], wp["row"]) in brick_cells:
                wp["row"] += 1
        # Active walls don't advance

        for hm in self.homings:
            hm["row"] += 1

        # Chance for new bricks to merge (unlocks round 150)
        new_bricks = [b for b in self.bricks if b["row"] == 1] if (self.mode != "simple" and self.round >= UNLOCK["merging"]) else []
        for nb in new_bricks:
            if random.random() < 0.15:  # 15% merge chance
                below = [b for b in self.bricks
                         if b["row"] == 2 and b["col"] == nb["col"]
                         and b is not nb and b.get("shape") != "tall"]
                if below:
                    target = below[0]
                    if target.get("shape") == "wide":
                        # Wide becomes tall square, halve HP first
                        target["hp"] = target["hp"] // 2
                    target["hp"] += nb["hp"]
                    target["shape"] = "tall"
                    target["row"] = 1  # tall brick starts at upper row
                    self.bricks.remove(nb)

        # Find empty cells on rows with bricks (for powerup placement)
        occupied_cells = self._build_occupied()
        brick_rows = set(b["row"] for b in self.bricks)
        empty = [(c, r) for r in brick_rows for c in range(COLS)
                 if (c, r) not in occupied_cells]

        # Spawn 1 +ball collectible on the new top row (fallback: any empty, then overlap)
        top_empty = [(c, r) for c, r in empty if r == 1]
        if top_empty:
            cc, cr = random.choice(top_empty)
            self.collectibles.append({"col": cc, "row": cr})
            empty.remove((cc, cr))
        elif empty:
            cc, cr = random.choice(empty)
            self.collectibles.append({"col": cc, "row": cr})
            empty.remove((cc, cr))
        else:
            # All cells full — place on top row anyway
            cc = random.randint(0, COLS - 1)
            self.collectibles.append({"col": cc, "row": 1})

        # Bonus: extra collectible from clearing the board — anywhere on the grid
        if self.bonus_extra_ball:
            self.bonus_extra_ball = False
            all_empty = [(c, r) for r in range(1, MAX_ROWS) for c in range(COLS)
                         if (c, r) not in occupied_cells]
            if all_empty:
                bc, br = random.choice(all_empty)
                self.collectibles.append({"col": bc, "row": br})
                if (bc, br) in empty:
                    empty.remove((bc, br))

        # PU chance: base * 0.5, boosted by efficiency up to +20%
        eff_bonus = min(0.20, self.last_efficiency * 0.01)
        def pu_chance(base):
            return base * 0.5 + eff_bonus

        # Simple mode: only skull
        spawn_pus = self.mode != "simple"

        # Spawn bomb (unlocks round 5)
        if spawn_pus and self.round >= UNLOCK["bombs"]:
            brick_cells = set((b["col"], b["row"]) for b in self.bricks)
            adjacent_empty = [
                (c, r) for c, r in empty
                if any((c + dc, r + dr) in brick_cells
                       for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1)])
            ]
            if adjacent_empty and random.random() < pu_chance(0.25):
                bc, br = random.choice(adjacent_empty)
                self.bombs.append({"col": bc, "row": br})
                empty.remove((bc, br))

        # Spawn cage (unlocks round 20)
        if spawn_pus and self.round >= UNLOCK["cage"] and empty and random.random() < pu_chance(0.20):
            cc, cr = random.choice(empty)
            cage_hp = max(6, self.hp_level)
            cage_cap = max(2, self.round // 10)
            self.cages.append({
                "col": cc, "row": cr, "hp": cage_hp,
                "max_capture": cage_cap, "captured": [],
                "timer": 0.0, "active": True,
            })
            empty.remove((cc, cr))

        # Spawn lightning (unlocks round 20)
        if spawn_pus and self.round >= UNLOCK["lightning"] and empty and random.random() < pu_chance(0.20):
            lc, lr = random.choice(empty)
            lg_hp = max(1, self.round // 10)
            self.lightnings.append({"col": lc, "row": lr, "hp": lg_hp})
            empty.remove((lc, lr))

        # Spawn rotating paddle (unlocks round 35)
        if spawn_pus and self.round >= UNLOCK["paddle"] and empty and random.random() < pu_chance(0.15):
            pc, pr = random.choice(empty)
            rot_speed = random.choice([-1, 1]) * random.uniform(1.5, 3.0)
            self.paddles.append({
                "col": pc, "row": pr,
                "angle": random.uniform(0, math.pi),
                "speed": rot_speed,
                "rounds_left": 1,
            })
            empty.remove((pc, pr))

        # Spawn fireball PU (unlocks round 35)
        if spawn_pus and self.round >= UNLOCK["fireball"] and empty and random.random() < pu_chance(0.15):
            fc, fr = random.choice(empty)
            self.fireballs.append({"col": fc, "row": fr, "charges": max(1, self.round // 10)})
            empty.remove((fc, fr))

        # Spawn skull PU
        if empty and self.round >= UNLOCK["skull"] and self.round % UNLOCK["skull_interval"] == 0:
            sc, sr = random.choice(empty)
            self.skulls.append({"col": sc, "row": sr})
            empty.remove((sc, sr))

        # Spawn laser PU (unlocks round 75)
        if spawn_pus and self.round >= UNLOCK["laser"] and empty and random.random() < pu_chance(0.15):
            lc, lr = random.choice(empty)
            direction = random.choice(["h", "v"])
            self.lasers.append({"col": lc, "row": lr, "hp": max(1, self.round // 10), "direction": direction})
            empty.remove((lc, lr))

        # Spawn freeze PU (unlocks round 75)
        if spawn_pus and self.round >= UNLOCK["freeze"] and empty and random.random() < pu_chance(0.10):
            fc, fr = random.choice(empty)
            self.freezes.append({"col": fc, "row": fr})
            empty.remove((fc, fr))

        # Spawn homing PU (unlocks round 100)
        if spawn_pus and self.round >= UNLOCK["homing"] and empty and random.random() < pu_chance(0.10):
            hc, hr = random.choice(empty)
            self.homings.append({"col": hc, "row": hr, "charges": max(1, self.round // 10)})
            empty.remove((hc, hr))

        # Spawn acid PU
        if spawn_pus and self.round >= UNLOCK["acid"] and empty and random.random() < pu_chance(0.10):
            ac, ar = random.choice(empty)
            self.acids.append({"col": ac, "row": ar})
            empty.remove((ac, ar))

        # Spawn wall PU
        if spawn_pus and self.round >= UNLOCK["wall"] and empty and random.random() < pu_chance(0.10):
            wc, wr = random.choice(empty)
            if wr > 1:  # no wall in row 1
                self.wall_pus.append({"col": wc, "row": wr})
                empty.remove((wc, wr))

        # Remove collectibles, bombs, cages, lightnings, skulls, lasers, freezes that scrolled off
        self.collectibles = [c for c in self.collectibles if c["row"] < MAX_ROWS]
        self.bombs = [b for b in self.bombs if b["row"] < MAX_ROWS]
        self.cages = [c for c in self.cages if c["row"] < MAX_ROWS]
        self.lightnings = [l for l in self.lightnings if l["row"] < MAX_ROWS]
        self.paddles = [p for p in self.paddles if p["row"] < MAX_ROWS]
        self.fireballs = [f for f in self.fireballs if f["row"] < MAX_ROWS]
        self.skulls = [s for s in self.skulls if s["row"] < MAX_ROWS]
        self.lasers = [l for l in self.lasers if l["row"] < MAX_ROWS]
        self.freezes = [f for f in self.freezes if f["row"] < MAX_ROWS]
        self.homings = [h for h in self.homings if h["row"] < MAX_ROWS]
        self.acids = [a for a in self.acids if a["row"] < MAX_ROWS]
        self.wall_pus = [w for w in self.wall_pus if w["row"] < MAX_ROWS]
        self.walls = [w for w in self.walls if w["row"] < MAX_ROWS and w["hp"] > 0]

        # Game over check
        for b in self.bricks:
            bottom_row = b["row"] + (1 if b.get("shape") == "tall" else 0)
            if bottom_row >= MAX_ROWS:
                self.phase = "gameover"
                if self.round > self.highscore:
                    self.highscore = self.round
                    save_highscore(self.mode, self.highscore)
                return

        self.phase = "advancing"

    # ------------------------------------------------------------------
    # Phase: aim
    # ------------------------------------------------------------------

    def update_aim(self, mouse_pos: tuple[int, int]):
        mx, my = mouse_pos
        my = max(my, TOP_UI_HEIGHT + CELL_SIZE * 3)  # clamp to 3 rows from top
        launch_y = HEIGHT - BOTTOM_AREA_HEIGHT
        dx = mx - self.launch_x
        dy = my - launch_y
        if dy >= -5:
            dy = -5  # clamp to upward
        angle = math.atan2(dy, dx)
        # Clamp to between ~10 and ~170 degrees upward
        angle = max(angle, -math.pi + 0.15)
        angle = min(angle, -0.15)
        self.aim_angle = angle

    def _build_occupied(self) -> set:
        """Build set of all occupied (col, row) cells."""
        cells = set()
        for b in self.bricks:
            cells.add((b["col"], b["row"]))
            if b.get("shape") == "wide":
                cells.add((b["col"] + 1, b["row"]))
            if b.get("shape") == "tall":
                cells.add((b["col"], b["row"] + 1))
        for items in (self.collectibles, self.bombs, self.cages, self.lightnings,
                      self.paddles, self.fireballs, self.skulls, self.lasers,
                      self.freezes, self.homings, self.acids, self.wall_pus, self.walls):
            for item in items:
                cells.add((item["col"], item["row"]))
        return cells

    def begin_fire(self):
        self.phase = "fire"
        self.balls_to_fire = self.ball_count
        self.fire_timer = 0.0
        self.balls.clear()
        self.balls_fired_this_aim = 0

    def update_aim_live(self, mouse_pos: tuple[int, int]):
        """Update aim angle while firing (mouse held down)."""
        self.update_aim(mouse_pos)

    # ------------------------------------------------------------------
    # Phase: fire (launch balls one by one)
    # ------------------------------------------------------------------

    def update_fire(self, dt: float):
        self.fire_timer -= dt
        if self.fire_timer <= 0 and self.balls_to_fire > 0:
            vel = pygame.math.Vector2(
                math.cos(self.aim_angle) * BALL_SPEED,
                math.sin(self.aim_angle) * BALL_SPEED,
            )
            launch_y = HEIGHT - BOTTOM_AREA_HEIGHT - BALL_RADIUS
            pos = pygame.math.Vector2(self.launch_x, launch_y)
            self.balls.append(Ball(pos, vel))
            self.balls_to_fire -= 1
            self.fire_timer = FIRE_DELAY

        if self.balls_to_fire <= 0:
            self.phase = "running"

    # ------------------------------------------------------------------
    # Phase: running (simulate balls)
    # ------------------------------------------------------------------

    def update_running(self, speed_mult: float = 1.0):
        for ball in self.balls:
            if not ball.alive:
                continue

            ball.update(speed_mult)

            # --- Homing steering ---
            if ball.homing:
                ball.homing_timer -= 1.0 / FPS * speed_mult
                if ball.homing_timer <= 0:
                    ball.homing = False
            if ball.homing and self.bricks:
                # Find nearest brick
                bx, by = ball.pos.x, ball.pos.y
                best_dist = float('inf')
                best_tx, best_ty = bx, by - 100
                for brick in self.bricks:
                    shape = brick.get("shape", "square")
                    rect = cell_rect(brick["col"], brick["row"], shape)
                    cx, cy = rect.center
                    d = math.hypot(cx - bx, cy - by)
                    if d < best_dist:
                        best_dist = d
                        best_tx, best_ty = cx, cy
                # Steer toward target (max ~3 degrees per frame)
                dx = best_tx - bx
                dy = best_ty - by
                target_angle = math.atan2(dy, dx)
                current_angle = math.atan2(ball.vel.y, ball.vel.x)
                diff = target_angle - current_angle
                # Normalize to [-pi, pi]
                while diff > math.pi:
                    diff -= 2 * math.pi
                while diff < -math.pi:
                    diff += 2 * math.pi
                max_steer = math.radians(2)
                steer = max(-max_steer, min(max_steer, diff))
                new_angle = current_angle + steer
                speed = ball.vel.length()
                ball.vel.x = math.cos(new_angle) * speed
                ball.vel.y = math.sin(new_angle) * speed

            # --- Gravity pull after 10 border bounces ---
            if ball.border_hits >= 10:
                _apply_gravity(ball)

            # --- Fireball PU collisions (before bricks so it activates first) ---
            self._collide_fireballs(ball)

            # --- Brick collisions ---
            self._collide_bricks(ball)

            # --- Collectible collisions ---
            self._collide_collectibles(ball)

            # --- Bomb collisions ---
            self._collide_bombs(ball)

            # --- Cage collisions ---
            self._collide_cages(ball)

            # --- Lightning collisions ---
            self._collide_lightnings(ball)

            # --- Paddle collisions ---
            self._collide_paddles(ball)

            # --- Skull collisions ---
            self._collide_skulls(ball)

            # --- Laser collisions ---
            self._collide_lasers(ball)

            # --- Freeze collisions ---
            self._collide_freezes(ball)

            # --- Acid collisions ---
            self._collide_acids(ball)

            # --- Wall PU and active wall collisions ---
            self._collide_wall_pus(ball)
            self._collide_walls(ball)

            # --- Homing collisions ---
            self._collide_homings(ball)

            # When last brick destroyed, spawn a bonus collectible
            if not self.bricks and not self.collectibles and not hasattr(self, '_board_clear_spawned'):
                self._board_clear_spawned = True
                bc = random.randint(0, COLS - 1)
                br = random.randint(2, MAX_ROWS - 2)
                self.collectibles.append({"col": bc, "row": br})
                self.bonus_text_timer = 1.5

            # If no bricks and no collectibles left, send all balls straight down
            if not self.bricks and not self.collectibles and ball.alive:
                ball.vel.x = 0
                ball.vel.y = BALL_SPEED

            # Track first ball to land
            if not ball.alive and self.first_landed_x is None:
                self.first_landed_x = ball.pos.x

        # Update paddle rotation
        self._update_paddles(speed_mult)

        # Force-release all cages if no balls are in play
        alive_in_play = any(b.alive for b in self.balls)
        if not alive_in_play and self.balls_to_fire <= 0:
            for cage in self.cages:
                if cage["captured"]:
                    self._release_cage(cage)

        # Update cage timers and release captured balls
        self._update_cages(speed_mult)

        # Acid tick: affected bricks lose 1 HP per second for 10 sec
        if self.acid_active:
            dt_game = 1.0 / FPS * speed_mult
            self.acid_duration -= dt_game
            if self.acid_duration <= 0:
                self.acid_active = False
                self.acid_bricks.clear()
            else:
                self.acid_timer -= dt_game
                if self.acid_timer <= 0:
                    self.acid_timer = 1.0
                    acid_dmg = max(1, self.hp_level * 2 // 100)
                    for b in self.bricks:
                        if id(b) in self.acid_bricks:
                            b["hp"] -= acid_dmg
                    self.bricks = [b for b in self.bricks if b["hp"] > 0]

        # Process queued lightning strikes
        self._process_lightning_queue(1.0 / FPS * speed_mult)

        # Check if all balls done (and no cages/lightning pending)
        cages_holding = any(len(c["captured"]) > 0 for c in self.cages)
        if (self.phase == "running"
                and all(not b.alive for b in self.balls)
                and self.balls_to_fire <= 0
                and not cages_holding
                and not self.lightning_queue):
            # Save efficiency before starting next round
            if self.round_balls > 0:
                self.last_efficiency = self.round_hits / self.round_balls
            # Bonus: extra ball if board was cleared (only if there were bricks)
            if not self.bricks and not self._board_clear_spawned:
                self.pending_collect += 1
                self.bonus_text_timer = 1.5
                self.bonus_extra_ball = True
            # Restore full ball count: landed balls + pending collectibles
            landed = sum(1 for b in self.balls if not b.alive)
            self.ball_count = landed + self.pending_collect
            if self.first_landed_x is not None:
                self.launch_x = self.first_landed_x
            # Clamp launch_x
            self.launch_x = max(BALL_RADIUS, min(WIDTH - BALL_RADIUS, self.launch_x))
            self.balls.clear()
            self.start_round()

    # ------------------------------------------------------------------
    # Collision helpers
    # ------------------------------------------------------------------

    def _collide_bricks(self, ball: Ball):
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []

        if ball.fireball:
            # Fireball: pass through all bricks, deal 1 damage, no bounce
            hit_any = False
            for i, brick in enumerate(self.bricks):
                shape = brick.get("shape", "square")
                rect = cell_rect_full(brick["col"], brick["row"], shape)
                expanded = rect.inflate(BALL_RADIUS * 2, BALL_RADIUS * 2)
                if expanded.collidepoint(bx, by):
                    hit_any = True
                    brick["hp"] -= 1
                    self.round_hits += 1
                    ball.border_hits = 0
                    if brick["hp"] <= 0:
                        to_remove.append(i)
            if hit_any:
                ball.fireball_in_bricks = True
            elif ball.fireball_in_bricks:
                # Check if any brick is within one cell distance
                nearby = False
                for brick in self.bricks:
                    shape = brick.get("shape", "square")
                    rect = cell_rect_full(brick["col"], brick["row"], shape)
                    if rect.inflate(CELL_SIZE, CELL_SIZE).collidepoint(bx, by):
                        nearby = True
                        break
                if not nearby:
                    # Clear of bricks — revert to normal
                    ball.fireball = False
                    ball.fireball_in_bricks = False
        else:
            # Normal: bounce off first brick hit
            for i, brick in enumerate(self.bricks):
                shape = brick.get("shape", "square")
                pre_vel_y = ball.vel.y  # save before collision
                pre_pos_y = ball.pos.y
                pre_pos_x = ball.pos.x

                if shape == "round":
                    hit = self._collide_round(ball, brick)
                elif shape == "diamond":
                    hit = self._collide_diamond(ball, brick)
                elif shape == "hexagon":
                    hit = self._collide_hexagon(ball, brick)
                elif shape == "trapezoid":
                    hit = self._collide_trapezoid(ball, brick)
                elif shape == "triangle":
                    hit = self._collide_triangle(ball, brick)
                else:
                    hit = self._collide_rect(ball, brick)

                if hit:
                    # Check shield
                    shield = brick.get("shield", 0)
                    rect_check = cell_rect_full(brick["col"], brick["row"],
                                                brick.get("shape", "square"))
                    if shape in ("round", "diamond", "triangle"):
                        # Bottom hemisphere — ball below center, going up
                        hit_from_below = (pre_vel_y < 0
                                          and pre_pos_y > rect_check.centery)
                    else:
                        # Rectangular: directly below — ball below center, within width, going up
                        hit_from_below = (pre_vel_y < 0
                                          and pre_pos_y > rect_check.centery
                                          and rect_check.left <= pre_pos_x <= rect_check.right)
                    if shield > 0 and hit_from_below:
                        brick["shield"] -= 1
                        if brick["shield"] <= 0:
                            del brick["shield"]
                    else:
                        brick["hp"] -= 1
                        self.round_hits += 1
                    ball.border_hits = 0
                    if brick["hp"] <= 0:
                        to_remove.append(i)
                    break  # one collision per frame per ball

        for i in reversed(to_remove):
            self.bricks.pop(i)

    def _collide_rect(self, ball: Ball, brick: dict) -> bool:
        """AABB collision for square and wide bricks. Returns True if hit."""
        bx, by = ball.pos.x, ball.pos.y
        shape = brick.get("shape", "square")
        rect = cell_rect_full(brick["col"], brick["row"], shape)
        expanded = rect.inflate(BALL_RADIUS * 2, BALL_RADIUS * 2)
        if not expanded.collidepoint(bx, by):
            return False

        cx = rect.centerx
        cy = rect.centery
        dx = bx - cx
        dy = by - cy
        half_w = rect.width / 2 + BALL_RADIUS
        half_h = rect.height / 2 + BALL_RADIUS

        ox = half_w - abs(dx)
        oy = half_h - abs(dy)

        if ox <= 0 or oy <= 0:
            return False

        buf = 1  # buffer to clear adjacent bricks
        if ox < oy:
            if dx > 0:
                ball.pos.x = rect.right + BALL_RADIUS + buf
            else:
                ball.pos.x = rect.left - BALL_RADIUS - buf
            ball.vel.x = -ball.vel.x
        else:
            if dy > 0:
                ball.pos.y = rect.bottom + BALL_RADIUS + buf
            else:
                ball.pos.y = rect.top - BALL_RADIUS - buf
            ball.vel.y = -ball.vel.y
        return True

    def _collide_round(self, ball: Ball, brick: dict) -> bool:
        """Circle-circle collision for round bricks. Returns True if hit."""
        bx, by = ball.pos.x, ball.pos.y
        rect = cell_rect(brick["col"], brick["row"], "square")
        cx, cy = rect.center
        brick_radius = BRICK_SIZE / 2

        dx = bx - cx
        dy = by - cy
        dist = math.hypot(dx, dy)
        min_dist = brick_radius + BALL_RADIUS

        if dist >= min_dist or dist == 0:
            return False

        # Normal vector from brick center to ball
        nx = dx / dist
        ny = dy / dist

        # Push ball out (with buffer to clear adjacent bricks)
        ball.pos.x = cx + nx * (min_dist + 1)
        ball.pos.y = cy + ny * (min_dist + 1)

        # Reflect velocity along normal
        dot = ball.vel.x * nx + ball.vel.y * ny
        ball.vel.x -= 2 * dot * nx
        ball.vel.y -= 2 * dot * ny
        return True

    def _collide_diamond(self, ball: Ball, brick: dict) -> bool:
        """Diamond (rotated square) collision. Uses Manhattan distance."""
        bx, by = ball.pos.x, ball.pos.y
        rect = cell_rect(brick["col"], brick["row"], "square")
        cx, cy = rect.center
        half = BRICK_SIZE / 2

        dx = bx - cx
        dy = by - cy
        # Manhattan distance defines diamond boundary
        man_dist = abs(dx) / half + abs(dy) / half
        # Account for ball radius
        threshold = 1.0 + BALL_RADIUS / half

        if man_dist >= threshold or man_dist == 0:
            return False

        # Determine which edge was hit based on quadrant
        # Diamond normals are at 45 degrees
        if dx >= 0 and dy <= 0:      # top-right edge
            nx, ny = 1.0, -1.0
        elif dx >= 0 and dy > 0:     # bottom-right edge
            nx, ny = 1.0, 1.0
        elif dx < 0 and dy <= 0:     # top-left edge
            nx, ny = -1.0, -1.0
        else:                         # bottom-left edge
            nx, ny = -1.0, 1.0

        # Normalize
        length = math.hypot(nx, ny)
        nx /= length
        ny /= length

        # Push ball out along normal
        push = (threshold - man_dist) * half
        ball.pos.x += nx * push
        ball.pos.y += ny * push

        # Reflect velocity along normal
        dot = ball.vel.x * nx + ball.vel.y * ny
        ball.vel.x -= 2 * dot * nx
        ball.vel.y -= 2 * dot * ny
        return True

    def _collide_polygon(self, ball: Ball, verts: list, cx: float, cy: float) -> bool:
        """Generic polygon collision using closest point on edge segments."""
        bx, by = ball.pos.x, ball.pos.y
        n = len(verts)

        # Quick reject
        r = max(math.hypot(v[0] - cx, v[1] - cy) for v in verts)
        if abs(bx - cx) > r + BALL_RADIUS + 4 or abs(by - cy) > r + BALL_RADIUS + 4:
            return False

        # Find closest point on boundary
        min_dist_sq = float('inf')
        closest_x, closest_y = cx, cy
        for i in range(n):
            x1, y1 = verts[i]
            x2, y2 = verts[(i + 1) % n]
            ex, ey = x2 - x1, y2 - y1
            seg_len_sq = ex * ex + ey * ey
            if seg_len_sq == 0:
                continue
            t = max(0.0, min(1.0, ((bx - x1) * ex + (by - y1) * ey) / seg_len_sq))
            px = x1 + t * ex
            py = y1 + t * ey
            dsq = (bx - px) ** 2 + (by - py) ** 2
            if dsq < min_dist_sq:
                min_dist_sq = dsq
                closest_x, closest_y = px, py

        dist = math.sqrt(min_dist_sq)
        if dist >= BALL_RADIUS or dist == 0:
            # Check if ball is inside polygon
            # Detect winding: compute signed area
            area = sum((verts[i][0] - cx) * (verts[(i+1)%n][1] - cy)
                       - (verts[(i+1)%n][0] - cx) * (verts[i][1] - cy)
                       for i in range(n))
            sign = 1 if area > 0 else -1  # +1=CCW, -1=CW
            inside = True
            for i in range(n):
                x1, y1 = verts[i]
                x2, y2 = verts[(i + 1) % n]
                cross = (x2 - x1) * (by - y1) - (y2 - y1) * (bx - x1)
                if cross * sign < 0:
                    inside = False
                    break
            if not inside:
                return False
            # Ball is inside polygon — push out from center
            dx, dy = bx - cx, by - cy
            dl = math.hypot(dx, dy)
            if dl == 0:
                dx, dy = 0, -1
            else:
                dx, dy = dx / dl, dy / dl
            ball.pos.x = cx + dx * (r + BALL_RADIUS)
            ball.pos.y = cy + dy * (r + BALL_RADIUS)
            dot = ball.vel.x * dx + ball.vel.y * dy
            ball.vel.x -= 2 * dot * dx
            ball.vel.y -= 2 * dot * dy
            return True

        # Ball overlaps boundary — push out along normal from closest point
        nx = (bx - closest_x) / dist
        ny = (by - closest_y) / dist
        ball.pos.x = closest_x + nx * (BALL_RADIUS + 1)
        ball.pos.y = closest_y + ny * (BALL_RADIUS + 1)
        dot = ball.vel.x * nx + ball.vel.y * ny
        ball.vel.x -= 2 * dot * nx
        ball.vel.y -= 2 * dot * ny
        return True

    def _collide_hexagon(self, ball: Ball, brick: dict) -> bool:
        rect = cell_rect(brick["col"], brick["row"], "square")
        cx, cy = rect.center
        r = BRICK_SIZE / 2
        verts = [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
                  cy + r * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]
        return self._collide_polygon(ball, verts, cx, cy)

    def _collide_trapezoid(self, ball: Ball, brick: dict) -> bool:
        rect = cell_rect(brick["col"], brick["row"], "square")
        cx, cy = rect.center
        hw = BRICK_SIZE / 2  # half width
        hh = BRICK_SIZE / 2  # half height
        tw = hw * 0.6  # top half-width (narrower)
        # Vertices clockwise: top-left, top-right, bottom-right, bottom-left
        verts = [
            (cx - tw, cy - hh),
            (cx + tw, cy - hh),
            (cx + hw, cy + hh),
            (cx - hw, cy + hh),
        ]
        return self._collide_polygon(ball, verts, cx, cy)

    def _tri_verts(self, brick: dict):
        """Return triangle vertices and center for given brick."""
        rect = cell_rect(brick["col"], brick["row"], "square")
        cx, cy = rect.center
        h = BRICK_SIZE / 2
        d = brick.get("tri_dir", "up")
        if d == "up":
            return [(cx, cy - h), (cx + h, cy + h), (cx - h, cy + h)], cx, cy
        elif d == "down":
            return [(cx - h, cy - h), (cx + h, cy - h), (cx, cy + h)], cx, cy
        elif d == "left":
            return [(cx - h, cy), (cx + h, cy - h), (cx + h, cy + h)], cx, cy
        else:  # right
            return [(cx - h, cy - h), (cx - h, cy + h), (cx + h, cy)], cx, cy

    def _collide_triangle(self, ball: Ball, brick: dict) -> bool:
        verts, cx, cy = self._tri_verts(brick)
        return self._collide_polygon(ball, verts, cx, cy)

    def _collide_collectibles(self, ball: Ball):
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []
        for i, col in enumerate(self.collectibles):
            rect = cell_rect(col["col"], col["row"])
            cx = rect.centerx
            cy = rect.centery
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.25:
                to_remove.append(i)
                self.pending_collect += 1
        for i in reversed(to_remove):
            self.collectibles.pop(i)

    def _collide_bombs(self, ball: Ball):
        bx, by = ball.pos.x, ball.pos.y
        triggered = []
        for bomb in self.bombs:
            rect = cell_rect(bomb["col"], bomb["row"])
            cx = rect.centerx
            cy = rect.centery
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.25:
                triggered.append((bomb, cx, cy))
        for bomb, cx, cy in triggered:
            if bomb in self.bombs:
                self.bombs.remove(bomb)
                self._explode(cx, cy)


    def _explode(self, ex: float, ey: float):
        """Deal 50% of brick HP to targets within blast radius. Chains PUs."""
        damage = max(1, self.round // 2)
        blast_px = BOMB_RADIUS_CELLS * CELL_SIZE

        # Damage bricks
        brick_remove = []
        for i, brick in enumerate(self.bricks):
            shape = brick.get("shape", "square")
            rect = cell_rect(brick["col"], brick["row"], shape)
            cx, cy = rect.center
            dist = math.hypot(cx - ex, cy - ey)
            if dist < blast_px:
                brick["hp"] -= damage
                if brick["hp"] <= 0:
                    brick_remove.append(i)
        for i in reversed(brick_remove):
            self.bricks.pop(i)

        # Chain to other bombs in range
        bomb_chain = []
        for bomb in self.bombs:
            rect = cell_rect(bomb["col"], bomb["row"])
            cx, cy = rect.center
            dist = math.hypot(cx - ex, cy - ey)
            if dist < blast_px and dist > 0:  # dist > 0 to skip self
                bomb_chain.append(bomb)
        for bomb in bomb_chain:
            if bomb in self.bombs:
                bx = cell_rect(bomb["col"], bomb["row"]).centerx
                by = cell_rect(bomb["col"], bomb["row"]).centery
                self.bombs.remove(bomb)
                self._explode(bx, by)

        # Chain to lightnings in range
        lg_chain = []
        for lg in self.lightnings:
            rect = cell_rect(lg["col"], lg["row"])
            cx, cy = rect.center
            dist = math.hypot(cx - ex, cy - ey)
            if dist < blast_px:
                lg["hp"] -= damage
                if lg["hp"] <= 0:
                    lg_chain.append(lg)
        for lg in lg_chain:
            if lg in self.lightnings:
                lrect = cell_rect(lg["col"], lg["row"])
                self.lightnings.remove(lg)
                self._lightning_strike(lrect.centerx, lrect.centery)

        # Collect +ball collectibles in range
        col_remove = []
        for col in self.collectibles:
            rect = cell_rect(col["col"], col["row"])
            cx, cy = rect.center
            dist = math.hypot(cx - ex, cy - ey)
            if dist < blast_px:
                col_remove.append(col)
                self.pending_collect += 1
        for col in col_remove:
            if col in self.collectibles:
                self.collectibles.remove(col)

        # Add visual explosion
        self.explosions.append({"x": ex, "y": ey, "timer": 0.4})

    def _collide_cages(self, ball: Ball):
        if ball.cage_immune > 0:
            ball.cage_immune -= 1
            return
        bx, by = ball.pos.x, ball.pos.y
        for cage in self.cages:
            rect = cell_rect(cage["col"], cage["row"])
            cx, cy = rect.center
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.35:
                cage["hp"] -= 1
                if len(cage["captured"]) < cage["max_capture"]:
                    # Capture the ball
                    ball.alive = False
                    if ball in self.balls:
                        self.balls.remove(ball)
                    cage["captured"].append({"x": cx, "y": cy})
                    cage["timer"] = 4.0
                    if len(cage["captured"]) >= cage["max_capture"]:
                        self._release_cage(cage)
                else:
                    # Cage full — release on next hit
                    self._release_cage(cage)

    def _release_cage(self, cage: dict):
        """Release all captured balls in random directions."""
        rect = cell_rect(cage["col"], cage["row"])
        cx, cy = rect.center
        for _ in cage["captured"]:
            angle = random.uniform(-math.pi + 0.15, -0.15)
            vel = pygame.math.Vector2(
                math.cos(angle) * BALL_SPEED,
                math.sin(angle) * BALL_SPEED,
            )
            b = Ball(pygame.math.Vector2(cx, cy), vel)
            b.cage_immune = 10  # immune from cage recapture for 10 frames
            self.balls.append(b)
        cage["captured"].clear()
        cage["timer"] = 0.0

    def _update_cages(self, speed_mult: float = 1.0):
        dt = 1.0 / FPS * speed_mult
        to_remove = []
        for cage in self.cages:
            # Destroy cage at 0 HP — release captured balls first
            if cage["hp"] <= 0:
                if cage["captured"]:
                    self._release_cage(cage)
                to_remove.append(cage)
                continue
            if not cage["captured"]:
                continue
            # Count down timer
            cage["timer"] -= dt
            # Release on timer expiry
            if cage["timer"] <= 0:
                self._release_cage(cage)
        for cage in to_remove:
            if cage in self.cages:
                self.cages.remove(cage)

    def _update_paddles(self, speed_mult: float = 1.0):
        dt = 1.0 / FPS * speed_mult
        for pd in self.paddles:
            pd["angle"] += pd["speed"] * dt

    def _collide_paddles(self, ball: Ball):
        if not ball.alive:
            return
        bx, by = ball.pos.x, ball.pos.y
        for pd in self.paddles:
            rect = cell_rect(pd["col"], pd["row"])
            cx, cy = rect.center
            angle = pd["angle"]
            half = PADDLE_LENGTH / 2

            # Paddle endpoints
            dx = math.cos(angle) * half
            dy = math.sin(angle) * half
            x1, y1 = cx - dx, cy - dy
            x2, y2 = cx + dx, cy + dy

            # Distance from ball to line segment
            # Project ball onto paddle line
            px, py = x2 - x1, y2 - y1
            seg_len_sq = px * px + py * py
            if seg_len_sq == 0:
                continue
            t = ((bx - x1) * px + (by - y1) * py) / seg_len_sq
            t = max(0.0, min(1.0, t))
            closest_x = x1 + t * px
            closest_y = y1 + t * py

            dist = math.hypot(bx - closest_x, by - closest_y)
            hit_dist = BALL_RADIUS + PADDLE_THICKNESS / 2

            if dist < hit_dist and dist > 0:
                # Normal from paddle surface to ball
                nx = (bx - closest_x) / dist
                ny = (by - closest_y) / dist

                # Push ball out
                ball.pos.x = closest_x + nx * hit_dist
                ball.pos.y = closest_y + ny * hit_dist

                # Reflect velocity along normal
                dot = ball.vel.x * nx + ball.vel.y * ny
                ball.vel.x -= 2 * dot * nx
                ball.vel.y -= 2 * dot * ny

                ball.border_hits = 0
                break

    def _collide_fireballs(self, ball: Ball):
        if not ball.alive or ball.fireball:
            return
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []
        for fb in self.fireballs:
            rect = cell_rect(fb["col"], fb["row"])
            cx, cy = rect.center
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.3:
                ball.fireball = True
                ball.fireball_in_bricks = False
                # Redirect downward balls upward
                if ball.vel.y > 0:
                    ball.vel.y = -abs(ball.vel.y)
                fb["charges"] -= 1
                if fb["charges"] <= 0:
                    to_remove.append(fb)
                break
        for fb in to_remove:
            if fb in self.fireballs:
                self.fireballs.remove(fb)

    def _collide_skulls(self, ball: Ball):
        if not ball.alive:
            return
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []
        for sk in self.skulls:
            rect = cell_rect(sk["col"], sk["row"])
            cx, cy = rect.center
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.3:
                to_remove.append(sk)
                self._activate_skull(cx, cy)
        for sk in to_remove:
            if sk in self.skulls:
                self.skulls.remove(sk)

    def _activate_skull(self, sx: float = 0, sy: float = 0):
        """Halve balls, all brick HP, and future difficulty."""
        # Skull wave animation
        self.skull_wave = {
            "x": sx, "y": sy, "radius": 0,
            "max_radius": math.hypot(WIDTH, HEIGHT),
            "speed": 600,
        }
        # Halve future brick HP
        self.hp_level = max(1, self.hp_level // 2)
        # Halve HP of all current bricks
        for brick in self.bricks:
            brick["hp"] = max(1, math.ceil(brick["hp"] * 0.5))
        # Halve total ball count (alive + unfired + already landed)
        dead = sum(1 for b in self.balls if not b.alive)
        alive = sum(1 for b in self.balls if b.alive)
        total = dead + alive + self.balls_to_fire
        new_total = max(1, math.ceil(total * 0.5))
        reduce = total - new_total
        # Remove from unfired first, then from landed
        from_unfired = min(reduce, self.balls_to_fire)
        self.balls_to_fire -= from_unfired
        reduce -= from_unfired
        # Remove landed balls
        if reduce > 0:
            removed = 0
            new_balls = []
            for b in self.balls:
                if not b.alive and removed < reduce:
                    removed += 1
                else:
                    new_balls.append(b)
            self.balls = new_balls
        self.ball_count = new_total
        # Visual feedback — full board flash
        self.skull_flash = 0.5  # seconds

    def _collide_lasers(self, ball: Ball):
        if not ball.alive:
            return
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []
        for ls in self.lasers:
            rect = cell_rect(ls["col"], ls["row"])
            cx, cy = rect.center
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.3:
                ls["hp"] -= 1
                if ls["hp"] <= 0:
                    to_remove.append(ls)
        for ls in to_remove:
            if ls in self.lasers:
                self.lasers.remove(ls)
                rect = cell_rect(ls["col"], ls["row"])
                cx, cy = rect.center
                self._fire_laser(cx, cy, ls["direction"])

    def _fire_laser(self, lx: float, ly: float, direction: str):
        """Fire a laser beam across the screen, damaging everything in its path."""
        damage = max(1, self.round // 10)
        # Visual beam
        self.laser_beams.append({"x": lx, "y": ly, "direction": direction, "timer": 0.5})

        def in_beam(rect):
            if direction == "h":
                return rect.top <= ly <= rect.bottom
            return rect.left <= lx <= rect.right

        # Damage bricks in beam
        hit_bricks = [b for b in self.bricks
                      if in_beam(cell_rect(b["col"], b["row"], b.get("shape", "square")))]
        for b in hit_bricks:
            b["hp"] -= damage
        self.bricks = [b for b in self.bricks if b["hp"] > 0 or b not in hit_bricks]

        # Chain: trigger bombs in beam
        hit_bombs = [b for b in self.bombs if in_beam(cell_rect(b["col"], b["row"]))]
        for bomb in hit_bombs:
            if bomb in self.bombs:
                cx, cy = cell_rect(bomb["col"], bomb["row"]).center
                self.bombs.remove(bomb)
                self._explode(cx, cy)

        # Chain: trigger other lasers in beam
        hit_lasers = [ls for ls in self.lasers if in_beam(cell_rect(ls["col"], ls["row"]))]
        for ls in hit_lasers:
            ls["hp"] -= damage
            if ls["hp"] <= 0 and ls in self.lasers:
                cx, cy = cell_rect(ls["col"], ls["row"]).center
                self.lasers.remove(ls)
                self._fire_laser(cx, cy, ls["direction"])

        # Collect +ball collectibles in beam
        hit_cols = [c for c in self.collectibles if in_beam(cell_rect(c["col"], c["row"]))]
        for col in hit_cols:
            if col in self.collectibles:
                self.collectibles.remove(col)
                self.pending_collect += 1

    def _collide_homings(self, ball: Ball):
        if not ball.alive or ball.homing:
            return
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []
        for hm in self.homings:
            rect = cell_rect(hm["col"], hm["row"])
            cx, cy = rect.center
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.3:
                ball.homing = True
                ball.homing_timer = 10.0
                hm["charges"] -= 1
                if hm["charges"] <= 0:
                    to_remove.append(hm)
                break
        for hm in to_remove:
            if hm in self.homings:
                self.homings.remove(hm)

    def _collide_wall_pus(self, ball: Ball):
        if not ball.alive:
            return
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []
        for wp in self.wall_pus:
            rect = cell_rect(wp["col"], wp["row"])
            cx, cy = rect.center
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.3:
                to_remove.append(wp)
                # Place active wall at this position
                self.walls.append({"col": wp["col"], "row": wp["row"],
                                   "hp": max(1, self.hp_level)})
        for wp in to_remove:
            if wp in self.wall_pus:
                self.wall_pus.remove(wp)

    def _collide_walls(self, ball: Ball):
        """Balls damage active walls like bricks."""
        if not ball.alive:
            return
        bx, by = ball.pos.x, ball.pos.y
        for w in self.walls:
            rect = cell_rect_full(w["col"], w["row"])
            expanded = rect.inflate(BALL_RADIUS * 2, BALL_RADIUS * 2)
            if expanded.collidepoint(bx, by):
                # Reflect ball
                cx, cy = rect.centerx, rect.centery
                dx, dy = bx - cx, by - cy
                half_w = rect.width / 2 + BALL_RADIUS
                half_h = rect.height / 2 + BALL_RADIUS
                ox = half_w - abs(dx)
                oy = half_h - abs(dy)
                if ox <= 0 or oy <= 0:
                    continue
                if ox < oy:
                    if dx > 0:
                        ball.pos.x = rect.right + BALL_RADIUS + 1
                    else:
                        ball.pos.x = rect.left - BALL_RADIUS - 1
                    ball.vel.x = -ball.vel.x
                else:
                    if dy > 0:
                        ball.pos.y = rect.bottom + BALL_RADIUS + 1
                    else:
                        ball.pos.y = rect.top - BALL_RADIUS - 1
                    ball.vel.y = -ball.vel.y
                w["hp"] -= 1
                ball.border_hits = 0
                break

    def _collide_acids(self, ball: Ball):
        if not ball.alive:
            return
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []
        for ac in self.acids:
            rect = cell_rect(ac["col"], ac["row"])
            cx, cy = rect.center
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.3:
                to_remove.append(ac)
                # Activate acid: 10 sec, radius 3 cells
                self.acid_active = True
                self.acid_timer = 1.0
                self.acid_duration = 10.0
                self.acid_center = (cx, cy)
                # Mark bricks within radius
                acid_px = CELL_SIZE * 3
                self.acid_bricks = set()
                for b in self.bricks:
                    shape = b.get("shape", "square")
                    br = cell_rect(b["col"], b["row"], shape)
                    d = math.hypot(br.centerx - cx, br.centery - cy)
                    if d < acid_px:
                        self.acid_bricks.add(id(b))
        for ac in to_remove:
            if ac in self.acids:
                self.acids.remove(ac)

    def _collide_freezes(self, ball: Ball):
        if not ball.alive:
            return
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []
        for fz in self.freezes:
            rect = cell_rect(fz["col"], fz["row"])
            cx, cy = rect.center
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.25:
                to_remove.append(fz)
                self.frozen_rounds += 1
                self.is_frozen_round = True
                # Start expanding ice wave from freeze PU position
                self.freeze_wave = {
                    "x": cx, "y": cy, "radius": 0,
                    "max_radius": math.hypot(WIDTH, HEIGHT),
                    "speed": 800,  # pixels per second
                }
        for fz in to_remove:
            if fz in self.freezes:
                self.freezes.remove(fz)

    def _collide_lightnings(self, ball: Ball):
        if not ball.alive:
            return
        bx, by = ball.pos.x, ball.pos.y
        to_remove = []
        for lg in self.lightnings:
            rect = cell_rect(lg["col"], lg["row"])
            cx, cy = rect.center
            dist = math.hypot(bx - cx, by - cy)
            if dist < BALL_RADIUS + BRICK_SIZE * 0.3:
                lg["hp"] -= 1
                # Each ball hit triggers strikes
                self._lightning_strike(cx, cy)
                if lg["hp"] <= 0:
                    to_remove.append(lg)
        for lg in to_remove:
            if lg in self.lightnings:
                self.lightnings.remove(lg)

    def _lightning_strike(self, lx: float, ly: float):
        """Queue lightning strikes to execute over time."""
        strikes = max(1, self.round // 20)
        self.lightning_queue.append({
            "lx": lx, "ly": ly,
            "strikes": strikes, "damage": 2,
            "delay": 0.0,
        })

    def _process_lightning_queue(self, dt: float):
        """Process one strike at a time with delays between them."""
        if not self.lightning_queue:
            return
        entry = self.lightning_queue[0]
        entry["delay"] -= dt
        if entry["delay"] > 0:
            return

        # Execute one strike
        lx, ly = entry["lx"], entry["ly"]
        damage = entry["damage"]

        # Gather targets
        targets = []
        for b in self.bricks:
            shape = b.get("shape", "square")
            rect = cell_rect(b["col"], b["row"], shape)
            targets.append({"type": "brick", "ref": b, "x": rect.centerx, "y": rect.centery})
        for bomb in self.bombs:
            rect = cell_rect(bomb["col"], bomb["row"])
            targets.append({"type": "bomb", "ref": bomb, "x": rect.centerx, "y": rect.centery})
        for col in self.collectibles:
            rect = cell_rect(col["col"], col["row"])
            targets.append({"type": "ball", "ref": col, "x": rect.centerx, "y": rect.centery})
        for lg in self.lightnings:
            rect = cell_rect(lg["col"], lg["row"])
            targets.append({"type": "lightning", "ref": lg, "x": rect.centerx, "y": rect.centery})

        if targets:
            t = random.choice(targets)
            self.lightning_bolts.append({
                "x1": lx, "y1": ly,
                "x2": t["x"], "y2": t["y"],
                "timer": 0.3,
            })
            # Chain: next bolt starts from this target
            entry["lx"] = t["x"]
            entry["ly"] = t["y"]

            if t["type"] == "brick":
                t["ref"]["hp"] -= damage
                if t["ref"]["hp"] <= 0 and t["ref"] in self.bricks:
                    self.bricks.remove(t["ref"])
            elif t["type"] == "bomb":
                if t["ref"] in self.bombs:
                    bx = cell_rect(t["ref"]["col"], t["ref"]["row"]).centerx
                    by = cell_rect(t["ref"]["col"], t["ref"]["row"]).centery
                    self.bombs.remove(t["ref"])
                    self._explode(bx, by)
            elif t["type"] == "ball":
                self.pending_collect += 1
                if t["ref"] in self.collectibles:
                    self.collectibles.remove(t["ref"])
            elif t["type"] == "lightning":
                t["ref"]["hp"] -= damage
                if t["ref"]["hp"] <= 0 and t["ref"] in self.lightnings:
                    lrect = cell_rect(t["ref"]["col"], t["ref"]["row"])
                    self.lightnings.remove(t["ref"])
                    self._lightning_strike(lrect.centerx, lrect.centery)

        entry["strikes"] -= 1
        if entry["strikes"] <= 0:
            self.lightning_queue.pop(0)
        else:
            entry["delay"] = 0.15  # 150ms between strikes


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw_pu_icon(screen, col, row, color, label, font, label_color=None,
                 radius_factor=0.26):
    """Draw a standard PU icon: colored circle with centered text."""
    rect = cell_rect(col, row)
    cx, cy = rect.center
    radius = int(BRICK_SIZE * radius_factor)
    pygame.draw.circle(screen, color, (cx, cy), radius)
    txt = font.render(label, True, label_color or BG_COLOR)
    screen.blit(txt, txt.get_rect(center=(cx, cy)))
    return cx, cy, radius


def draw_snowflake(screen, cx, cy, size, color=None):
    """Draw a 5-line snowflake centered at (cx, cy)."""
    c = color or TEXT_COLOR
    for i in range(5):
        a = i * math.pi / 5
        dx, dy = math.cos(a) * size, math.sin(a) * size
        pygame.draw.line(screen, c, (cx - dx, cy - dy), (cx + dx, cy + dy), 2)


def draw_game(screen: pygame.Surface, game: Game, font: pygame.font.Font,
              small_font: pygame.font.Font, mouse_held: bool = False):
    screen.fill(BG_COLOR)

    # Animation offset: during advancing, items slide down
    global GRID_TOP
    orig_grid_top = GRID_TOP
    if game.advance_anim > 0 and game.advance_duration > 0:
        progress = game.advance_anim / game.advance_duration  # 1.0 -> 0.0
        GRID_TOP = orig_grid_top - int(CELL_SIZE * progress)

    # --- UI top bar ---
    round_surf = font.render(f"Round: {game.round}", True, TEXT_COLOR)
    hi_surf = font.render(f"Best: {game.highscore}", True, (180, 180, 100))
    balls_surf = font.render(f"Balls: {game.ball_count + game.pending_collect}", True, TEXT_COLOR)
    screen.blit(round_surf, (15, 12))
    screen.blit(hi_surf, hi_surf.get_rect(center=(WIDTH // 2, 13)))
    screen.blit(balls_surf, (WIDTH - balls_surf.get_width() - 15, 12))

    # Efficiency: current round live, or last round's result
    if game.phase in ("fire", "running") and game.round_balls > 0:
        eff = game.round_hits / game.round_balls
        eff_text = f"Eff: {eff:.1f}"
    elif game.last_efficiency > 0:
        eff_text = f"Eff: {game.last_efficiency:.1f}"
    else:
        eff_text = ""
    if eff_text:
        eff_surf = small_font.render(eff_text, True, (160, 160, 180))
        screen.blit(eff_surf, eff_surf.get_rect(center=(WIDTH // 2, 37)))

    # --- Bricks ---
    ice_frame = game.is_frozen_round
    for brick in game.bricks:
        shape = brick.get("shape", "square")
        color = brick_color(brick["hp"])

        if shape == "round":
            rect = cell_rect(brick["col"], brick["row"], "square")
            cx, cy = rect.center
            radius = BRICK_SIZE // 2
            pygame.draw.circle(screen, color, (cx, cy), radius)
            if ice_frame:
                pygame.draw.circle(screen, FREEZE_COLOR, (cx, cy), radius + 2, 2)
            hp_surf = small_font.render(str(brick["hp"]), True, TEXT_COLOR)
            hp_rect = hp_surf.get_rect(center=(cx, cy))
            screen.blit(hp_surf, hp_rect)
        elif shape == "diamond":
            rect = cell_rect(brick["col"], brick["row"], "square")
            cx, cy = rect.center
            half = BRICK_SIZE // 2
            points = [(cx, cy - half), (cx + half, cy), (cx, cy + half), (cx - half, cy)]
            pygame.draw.polygon(screen, color, points)
            if ice_frame:
                pygame.draw.polygon(screen, FREEZE_COLOR, points, 2)
            hp_surf = small_font.render(str(brick["hp"]), True, TEXT_COLOR)
            hp_rect = hp_surf.get_rect(center=(cx, cy))
            screen.blit(hp_surf, hp_rect)
        elif shape == "hexagon":
            rect = cell_rect(brick["col"], brick["row"], "square")
            cx, cy = rect.center
            r = BRICK_SIZE // 2
            points = []
            for i in range(6):
                a = math.pi / 6 + i * math.pi / 3
                points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            pygame.draw.polygon(screen, color, points)
            if ice_frame:
                pygame.draw.polygon(screen, FREEZE_COLOR, points, 2)
            hp_surf = small_font.render(str(brick["hp"]), True, TEXT_COLOR)
            hp_rect = hp_surf.get_rect(center=(cx, cy))
            screen.blit(hp_surf, hp_rect)
        elif shape == "trapezoid":
            rect = cell_rect(brick["col"], brick["row"], "square")
            cx, cy = rect.center
            hw = BRICK_SIZE // 2
            hh = BRICK_SIZE // 2
            tw = int(hw * 0.6)
            points = [(cx - tw, cy - hh), (cx + tw, cy - hh),
                       (cx + hw, cy + hh), (cx - hw, cy + hh)]
            pygame.draw.polygon(screen, color, points)
            if ice_frame:
                pygame.draw.polygon(screen, FREEZE_COLOR, points, 2)
            hp_surf = small_font.render(str(brick["hp"]), True, TEXT_COLOR)
            hp_rect = hp_surf.get_rect(center=(cx, cy))
            screen.blit(hp_surf, hp_rect)
        elif shape == "triangle":
            verts, cx, cy = game._tri_verts(brick)
            points = [(int(x), int(y)) for x, y in verts]
            pygame.draw.polygon(screen, color, points)
            if ice_frame:
                pygame.draw.polygon(screen, FREEZE_COLOR, points, 2)
            hp_surf = small_font.render(str(brick["hp"]), True, TEXT_COLOR)
            hp_rect = hp_surf.get_rect(center=(int(cx), int(cy)))
            screen.blit(hp_surf, hp_rect)
        else:
            rect = cell_rect(brick["col"], brick["row"], shape)
            pygame.draw.rect(screen, color, rect, border_radius=4)
            if ice_frame:
                pygame.draw.rect(screen, FREEZE_COLOR, rect.inflate(4, 4), 2, border_radius=5)
            hp_surf = small_font.render(str(brick["hp"]), True, TEXT_COLOR)
            hp_rect = hp_surf.get_rect(center=rect.center)
            screen.blit(hp_surf, hp_rect)

    # --- Shields (drawn on top of bricks) ---
    for brick in game.bricks:
        shield = brick.get("shield", 0)
        if shield > 0:
            shape = brick.get("shape", "square")
            rect = cell_rect(brick["col"], brick["row"], "square")
            cx, cy = rect.center

            if shape == "round":
                # Half-circle arc at bottom
                r = BRICK_SIZE // 2 + 2
                arc_rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
                pygame.draw.arc(screen, SHIELD_COLOR, arc_rect,
                                math.pi + 0.3, 2 * math.pi - 0.3, 3)
            elif shape == "diamond":
                # V shape at bottom half
                half = BRICK_SIZE // 2 + 2
                pygame.draw.lines(screen, SHIELD_COLOR, False, [
                    (cx - half, cy), (cx, cy + half), (cx + half, cy)
                ], 3)
            elif shape == "triangle":
                # Shield on bottom half of triangle
                h = BRICK_SIZE // 2 + 2
                d = brick.get("tri_dir", "up")
                if d == "up":  # base at bottom — flat line
                    pygame.draw.line(screen, SHIELD_COLOR,
                                     (cx - h, cy + h), (cx + h, cy + h), 3)
                elif d == "down":  # tip at bottom — V halfway up sides
                    pygame.draw.lines(screen, SHIELD_COLOR, False, [
                        (cx - h // 2, cy), (cx, cy + h), (cx + h // 2, cy)
                    ], 3)
                elif d == "left":  # tip at left — bottom slant + half of right
                    pygame.draw.lines(screen, SHIELD_COLOR, False, [
                        (cx + h, cy), (cx - h, cy), (cx + h, cy + h)
                    ], 3)
                else:  # right — tip at right — bottom slant + half of left
                    pygame.draw.lines(screen, SHIELD_COLOR, False, [
                        (cx - h, cy), (cx + h, cy), (cx - h, cy + h)
                    ], 3)
            else:
                # Line at bottom for rectangular shapes
                if shape not in ("round", "diamond", "hexagon"):
                    rect = cell_rect(brick["col"], brick["row"], shape)
                bottom = rect.bottom
                half_w = rect.width // 2
                pygame.draw.line(screen, SHIELD_COLOR,
                                 (rect.centerx - half_w, bottom),
                                 (rect.centerx + half_w, bottom), 3)
                glow_surf = pygame.Surface((rect.width, 6), pygame.SRCALPHA)
                glow_surf.fill((*SHIELD_COLOR, 60))
                screen.blit(glow_surf, (rect.left, bottom - 3))

    # --- Collectibles ---
    for col in game.collectibles:
        rect = cell_rect(col["col"], col["row"])
        cx, cy = rect.center
        radius = int(BRICK_SIZE * 0.22)
        pygame.draw.circle(screen, COLLECTIBLE_COLOR, (cx, cy), radius)
        plus = small_font.render("+", True, BG_COLOR)
        pr = plus.get_rect(center=(cx, cy))
        screen.blit(plus, pr)

    # --- Bombs ---
    for bomb in game.bombs:
        draw_pu_icon(screen, bomb["col"], bomb["row"], BOMB_COLOR, "B", small_font, TEXT_COLOR)

    # --- Cages ---
    for cage in game.cages:
        rect = cell_rect(cage["col"], cage["row"])
        cx, cy = rect.center
        radius = int(BRICK_SIZE * 0.32)
        # Draw cage body
        pygame.draw.circle(screen, CAGE_COLOR, (cx, cy), radius)
        # Draw grid lines to look cage-like
        pygame.draw.circle(screen, CAGE_COLOR, (cx, cy), radius, 2)
        # Show captured count / hp
        captured = len(cage["captured"])
        if captured > 0:
            cap_text = small_font.render(str(captured), True, TEXT_COLOR)
            screen.blit(cap_text, cap_text.get_rect(center=(cx, cy)))
        else:
            c_text = small_font.render("#", True, BG_COLOR)
            screen.blit(c_text, c_text.get_rect(center=(cx, cy)))

    # --- Lasers ---
    for ls in game.lasers:
        rect = cell_rect(ls["col"], ls["row"])
        cx, cy = rect.center
        radius = int(BRICK_SIZE * 0.26)
        color = LASER_H_COLOR if ls["direction"] == "h" else LASER_V_COLOR
        pygame.draw.circle(screen, color, (cx, cy), radius)
        # Draw direction indicator
        if ls["direction"] == "h":
            pygame.draw.line(screen, TEXT_COLOR, (cx - radius + 3, cy), (cx + radius - 3, cy), 2)
        else:
            pygame.draw.line(screen, TEXT_COLOR, (cx, cy - radius + 3), (cx, cy + radius - 3), 2)
        hp_text = small_font.render(str(ls["hp"]), True, BG_COLOR)
        screen.blit(hp_text, hp_text.get_rect(center=(cx, cy)))

    # --- Laser beams ---
    for beam in game.laser_beams:
        alpha = max(0, min(255, int(255 * (beam["timer"] / 0.5))))
        beam_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        if beam["direction"] == "h":
            color = (*LASER_H_COLOR, alpha)
            pygame.draw.line(beam_surf, color, (0, int(beam["y"])), (WIDTH, int(beam["y"])), 4)
            glow = (*LASER_H_COLOR[:2], min(255, LASER_H_COLOR[2] + 100), alpha // 3)
            pygame.draw.line(beam_surf, glow, (0, int(beam["y"])), (WIDTH, int(beam["y"])), 12)
        else:
            color = (*LASER_V_COLOR, alpha)
            pygame.draw.line(beam_surf, color, (int(beam["x"]), TOP_UI_HEIGHT), (int(beam["x"]), GRID_BOTTOM), 4)
            glow = (*LASER_V_COLOR[:2], min(255, LASER_V_COLOR[2] + 100), alpha // 3)
            pygame.draw.line(beam_surf, glow, (int(beam["x"]), TOP_UI_HEIGHT), (int(beam["x"]), GRID_BOTTOM), 12)
        screen.blit(beam_surf, (0, 0))

    # --- Wall PUs ---
    for wp in game.wall_pus:
        draw_pu_icon(screen, wp["col"], wp["row"], WALL_COLOR, "=", small_font)

    # --- Active walls (energy barrier) ---
    for w in game.walls:
        if w["hp"] > 0:
            rect = cell_rect_full(w["col"], w["row"])
            cx, cy = rect.centerx, rect.centery
            left, right = rect.left, rect.right
            # Glow above and below
            glow_surf = pygame.Surface((rect.width, 12), pygame.SRCALPHA)
            glow_surf.fill((*WALL_COLOR, 30))
            screen.blit(glow_surf, (left, cy - 6))
            # Main barrier line
            pygame.draw.line(screen, WALL_COLOR, (left, cy), (right, cy), 3)
            # HP text
            hp_surf = small_font.render(str(w["hp"]), True, TEXT_COLOR)
            screen.blit(hp_surf, hp_surf.get_rect(center=(cx, cy - 10)))

    # --- Acids ---
    for ac in game.acids:
        draw_pu_icon(screen, ac["col"], ac["row"], ACID_COLOR, "A", small_font)

    # --- Acid overlay on affected bricks ---
    if game.acid_active:
        for brick in game.bricks:
            if id(brick) in game.acid_bricks:
                shape = brick.get("shape", "square")
                if shape in ("round", "diamond", "hexagon", "triangle"):
                    rect = cell_rect(brick["col"], brick["row"], "square")
                else:
                    rect = cell_rect(brick["col"], brick["row"], shape)
                acid_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
                acid_surf.fill((*ACID_COLOR, 50))
                screen.blit(acid_surf, rect.topleft)

    # --- Homings ---
    for hm in game.homings:
        draw_pu_icon(screen, hm["col"], hm["row"], HOMING_COLOR, "H", small_font)

    # --- Freezes ---
    for fz in game.freezes:
        rect = cell_rect(fz["col"], fz["row"])
        cx, cy = rect.center
        r = int(BRICK_SIZE * 0.26)
        pygame.draw.circle(screen, FREEZE_COLOR, (cx, cy), r)
        pygame.draw.circle(screen, TEXT_COLOR, (cx, cy), r, 2)
        draw_snowflake(screen, cx, cy, r - 2)

    # --- Skulls ---
    for sk in game.skulls:
        draw_pu_icon(screen, sk["col"], sk["row"], SKULL_COLOR, "X", small_font, TEXT_COLOR, 0.28)

    # --- Fireball PUs ---
    for fb in game.fireballs:
        cx, cy, r = draw_pu_icon(screen, fb["col"], fb["row"], FIREBALL_COLOR, "", small_font)
        pygame.draw.circle(screen, FIREBALL_GLOW, (cx, cy), r - 3)
        f_text = small_font.render("F", True, BG_COLOR)
        screen.blit(f_text, f_text.get_rect(center=(cx, cy)))

    # --- Paddles ---
    for pd in game.paddles:
        rect = cell_rect(pd["col"], pd["row"])
        cx, cy = rect.center
        angle = pd["angle"]
        half = PADDLE_LENGTH / 2
        dx = math.cos(angle) * half
        dy = math.sin(angle) * half
        x1, y1 = cx - dx, cy - dy
        x2, y2 = cx + dx, cy + dy
        pygame.draw.line(screen, PADDLE_COLOR, (int(x1), int(y1)), (int(x2), int(y2)), PADDLE_THICKNESS + 2)

    # --- Lightnings ---
    for lg in game.lightnings:
        rect = cell_rect(lg["col"], lg["row"])
        cx, cy = rect.center
        radius = int(BRICK_SIZE * 0.26)
        pygame.draw.circle(screen, LIGHTNING_COLOR, (cx, cy), radius)
        # Draw a small lightning bolt symbol
        sz = radius * 0.6
        points = [
            (cx - sz * 0.3, cy - sz), (cx + sz * 0.2, cy - sz * 0.1),
            (cx - sz * 0.1, cy - sz * 0.1), (cx + sz * 0.3, cy + sz),
            (cx - sz * 0.2, cy + sz * 0.1), (cx + sz * 0.1, cy + sz * 0.1),
        ]
        pygame.draw.polygon(screen, TEXT_COLOR, points)
        # Show HP on the icon
        hp_text = small_font.render(str(lg["hp"]), True, BG_COLOR)
        screen.blit(hp_text, hp_text.get_rect(center=(cx, cy)))

    # --- Lightning bolts (visual effect) ---
    for bolt in game.lightning_bolts:
        alpha = max(0, min(255, int(255 * (bolt["timer"] / 0.3))))
        x1, y1 = int(bolt["x1"]), int(bolt["y1"])
        x2, y2 = int(bolt["x2"]), int(bolt["y2"])
        # Jagged line
        segments = 5
        points = [(x1, y1)]
        for s in range(1, segments):
            t = s / segments
            mx = x1 + (x2 - x1) * t + random.randint(-8, 8)
            my = y1 + (y2 - y1) * t + random.randint(-8, 8)
            points.append((mx, my))
        points.append((x2, y2))
        color = (100, 200, 255, alpha)
        bolt_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.lines(bolt_surf, color, False, points, 2)
        screen.blit(bolt_surf, (0, 0))

    # --- Explosions ---
    for exp in game.explosions:
        alpha = max(0, min(255, int(255 * (exp["timer"] / 0.4))))
        blast_px = int(BOMB_RADIUS_CELLS * CELL_SIZE)
        exp_surf = pygame.Surface((blast_px * 2, blast_px * 2), pygame.SRCALPHA)
        pygame.draw.circle(exp_surf, (255, 150, 50, alpha), (blast_px, blast_px), blast_px)
        pygame.draw.circle(exp_surf, (255, 255, 100, alpha // 2), (blast_px, blast_px), blast_px // 2)
        screen.blit(exp_surf, (int(exp["x"]) - blast_px, int(exp["y"]) - blast_px))

    # --- Balls (only draw alive ones) ---
    for ball in game.balls:
        if ball.alive:
            if ball.fireball:
                # Glow effect
                glow_surf = pygame.Surface((BALL_RADIUS * 6, BALL_RADIUS * 6), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (255, 100, 0, 80),
                                   (BALL_RADIUS * 3, BALL_RADIUS * 3), BALL_RADIUS * 3)
                screen.blit(glow_surf, (int(ball.pos.x) - BALL_RADIUS * 3,
                                        int(ball.pos.y) - BALL_RADIUS * 3))
                pygame.draw.circle(screen, FIREBALL_COLOR, (int(ball.pos.x), int(ball.pos.y)),
                                   BALL_RADIUS)
                pygame.draw.circle(screen, FIREBALL_GLOW, (int(ball.pos.x), int(ball.pos.y)),
                                   BALL_RADIUS - 2)
            elif ball.homing:
                pygame.draw.circle(screen, HOMING_COLOR, (int(ball.pos.x), int(ball.pos.y)),
                                   BALL_RADIUS)
            else:
                pygame.draw.circle(screen, TEXT_COLOR, (int(ball.pos.x), int(ball.pos.y)),
                                   BALL_RADIUS)

    # --- Landed balls indicator (only show first ball's exit point) ---

    # --- Top border ---
    pygame.draw.line(screen, (80, 80, 100), (0, TOP_UI_HEIGHT), (WIDTH, TOP_UI_HEIGHT), 2)

    # --- Danger flash: bricks on last row pulse red for 3 sec ---
    danger_bricks = [b for b in game.bricks
                     if b["row"] + (1 if b.get("shape") == "tall" else 0) >= MAX_ROWS - 1]
    if danger_bricks:
        if not hasattr(game, '_danger_timer'):
            game._danger_timer = 3.0
        if game._danger_timer > 0:
            pulse = (math.sin(pygame.time.get_ticks() / 150) + 1) / 2
            alpha = int(80 + 160 * pulse)
            for b in danger_bricks:
                shape = b.get("shape", "square")
                rect = cell_rect(b["col"], b["row"], shape)
                flash_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
                flash_surf.fill((255, 40, 40, alpha))
                screen.blit(flash_surf, rect.topleft)
    else:
        game._danger_timer = 3.0  # reset when no danger

    # --- Aim line ---
    launch_y = HEIGHT - BOTTOM_AREA_HEIGHT
    if game.phase == "aim" or (game.phase == "fire" and mouse_held):
        draw_aim_line(screen, game.launch_x, launch_y, game.aim_angle, pygame.mouse.get_pos())

    # --- Launch point indicator ---
    if game.phase in ("aim", "fire", "running"):
        pygame.draw.circle(screen, TEXT_COLOR, (int(game.launch_x), launch_y), 4)

    # --- Unfired balls counter at bottom right (fades after last ball) ---
    if game.phase in ("fire", "running"):
        if game.balls_to_fire > 0:
            game._fire_counter_fade = 2.0
        elif hasattr(game, '_fire_counter_fade') and game._fire_counter_fade > 0:
            pass  # fade timer ticking in main loop
        if hasattr(game, '_fire_counter_fade') and game._fire_counter_fade > 0:
            alpha = min(255, int(255 * (game._fire_counter_fade / 2.0)))
            bl_surf = small_font.render("0" if game.balls_to_fire <= 0 else str(game.balls_to_fire),
                                        True, (160, 160, 180))
            bl_surf.set_alpha(alpha)
            screen.blit(bl_surf, (WIDTH - bl_surf.get_width() - 10, HEIGHT - 25))

    # --- First ball exit marker (shows next launch point during running) ---
    if game.phase in ("fire", "running") and game.first_landed_x is not None:
        mx = int(game.first_landed_x)
        my = launch_y
        # Draw a small triangle pointing up
        pygame.draw.polygon(screen, (255, 200, 60), [
            (mx, my - 10), (mx - 6, my), (mx + 6, my)
        ])

    # --- Freeze wave ---
    if game.freeze_wave:
        fw = game.freeze_wave
        r = int(fw["radius"])
        if r > 0:
            wave_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            alpha = max(0, min(150, int(150 * (1 - fw["radius"] / fw["max_radius"]))))
            pygame.draw.circle(wave_surf, (*FREEZE_COLOR, alpha), (int(fw["x"]), int(fw["y"])), r, 4)
            # Inner glow
            inner_alpha = max(0, alpha // 3)
            pygame.draw.circle(wave_surf, (*FREEZE_COLOR, inner_alpha), (int(fw["x"]), int(fw["y"])), r)
            screen.blit(wave_surf, (0, 0))

    # --- Skull wave ---
    if game.skull_wave:
        sw = game.skull_wave
        r = int(sw["radius"])
        if r > 0:
            wave_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            alpha = max(0, min(180, int(180 * (1 - sw["radius"] / sw["max_radius"]))))
            pygame.draw.circle(wave_surf, (*SKULL_COLOR, alpha), (int(sw["x"]), int(sw["y"])), r, 5)
            inner_alpha = max(0, alpha // 3)
            pygame.draw.circle(wave_surf, (*SKULL_COLOR, inner_alpha), (int(sw["x"]), int(sw["y"])), r)
            screen.blit(wave_surf, (0, 0))

    # --- Unlock text ---
    if game.unlock_timer > 0:
        unlock_font = pygame.font.SysFont("Arial", 28, bold=True)
        alpha = min(255, int(255 * min(1.0, game.unlock_timer / 0.5)))
        unlock_surf = unlock_font.render(game.unlock_text, True, (100, 255, 100))
        unlock_bg = pygame.Surface(unlock_surf.get_size(), pygame.SRCALPHA)
        unlock_bg.blit(unlock_surf, (0, 0))
        unlock_bg.set_alpha(alpha)
        screen.blit(unlock_bg, unlock_bg.get_rect(center=(WIDTH // 2, HEIGHT // 3)))

    # --- Bonus text ---
    if game.bonus_text_timer > 0:
        bonus_font = pygame.font.SysFont("Arial", 36, bold=True)
        alpha = min(255, int(255 * (game.bonus_text_timer / 0.5)))
        bonus_surf = bonus_font.render("BONUS +1", True, (255, 200, 60))
        bonus_bg = pygame.Surface(bonus_surf.get_size(), pygame.SRCALPHA)
        bonus_bg.fill((0, 0, 0, 0))
        bonus_bg.blit(bonus_surf, (0, 0))
        bonus_bg.set_alpha(alpha)
        screen.blit(bonus_bg, bonus_bg.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

    # --- Game over overlay ---
    if game.phase == "gameover":
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill(GAMEOVER_OVERLAY)
        screen.blit(overlay, (0, 0))

        go_font = pygame.font.SysFont("Arial", 48, bold=True)
        go_surf = go_font.render("GAME OVER", True, (255, 80, 80))
        screen.blit(go_surf, go_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 40)))

        info = font.render(f"Round {game.round}", True, TEXT_COLOR)
        screen.blit(info, info.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 20)))

        hi = font.render(f"Best: {game.highscore}", True, (255, 200, 60))
        screen.blit(hi, hi.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 55)))

        hint = small_font.render("Click to restart", True, (180, 180, 180))
        screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 90)))

    # Restore GRID_TOP after animation
    GRID_TOP = orig_grid_top


def draw_menu(screen: pygame.Surface):
    """Draw the startup menu."""
    screen.fill(BG_COLOR)

    title_font = pygame.font.SysFont("Arial", 52, bold=True)
    btn_font = pygame.font.SysFont("Arial", 28, bold=True)
    desc_font = pygame.font.SysFont("Arial", 16)
    hs_font = pygame.font.SysFont("Arial", 15)

    # Title
    title = title_font.render("BRICKS", True, TEXT_COLOR)
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 150)))

    # Simple button
    simple_rect = pygame.Rect(WIDTH // 2 - 140, 260, 280, 60)
    pygame.draw.rect(screen, (100, 100, 120), simple_rect, border_radius=10)
    sim_text = btn_font.render("Simple", True, TEXT_COLOR)
    screen.blit(sim_text, sim_text.get_rect(center=simple_rect.center))
    sim_desc = desc_font.render("Squares, +ball, skull only", True, (180, 180, 180))
    screen.blit(sim_desc, sim_desc.get_rect(center=(WIDTH // 2, 335)))
    sim_hs = load_highscore("simple")
    if sim_hs > 0:
        hs_text = hs_font.render(f"Best: {sim_hs}", True, (255, 200, 60))
        screen.blit(hs_text, hs_text.get_rect(center=(WIDTH // 2, 352)))

    # Classic button
    classic_rect = pygame.Rect(WIDTH // 2 - 140, 380, 280, 60)
    pygame.draw.rect(screen, (76, 175, 80), classic_rect, border_radius=10)
    cls_text = btn_font.render("Classic", True, TEXT_COLOR)
    screen.blit(cls_text, cls_text.get_rect(center=classic_rect.center))
    cls_desc = desc_font.render("Squares with powerups", True, (180, 180, 180))
    screen.blit(cls_desc, cls_desc.get_rect(center=(WIDTH // 2, 455)))
    cls_hs = load_highscore("classic")
    if cls_hs > 0:
        hs_text = hs_font.render(f"Best: {cls_hs}", True, (255, 200, 60))
        screen.blit(hs_text, hs_text.get_rect(center=(WIDTH // 2, 472)))

    # Advanced button
    adv_rect = pygame.Rect(WIDTH // 2 - 140, 500, 280, 60)
    pygame.draw.rect(screen, (156, 39, 176), adv_rect, border_radius=10)
    adv_text = btn_font.render("Advanced", True, TEXT_COLOR)
    screen.blit(adv_text, adv_text.get_rect(center=adv_rect.center))
    adv_desc = desc_font.render("Multiple shapes with powerups", True, (180, 180, 180))
    screen.blit(adv_desc, adv_desc.get_rect(center=(WIDTH // 2, 575)))
    adv_hs = load_highscore("advanced")
    if adv_hs > 0:
        hs_text = hs_font.render(f"Best: {adv_hs}", True, (255, 200, 60))
        screen.blit(hs_text, hs_text.get_rect(center=(WIDTH // 2, 592)))

    # Help button
    help_rect = pygame.Rect(WIDTH // 2 - 60, 630, 120, 40)
    pygame.draw.rect(screen, (80, 80, 100), help_rect, border_radius=8)
    help_text = btn_font.render("Help", True, TEXT_COLOR)
    screen.blit(help_text, help_text.get_rect(center=help_rect.center))

    return simple_rect, classic_rect, adv_rect, help_rect


HELP_PAGES = 3


def draw_help(screen: pygame.Surface, page: int = 0):
    """Draw the help screen with pagination."""
    screen.fill(BG_COLOR)

    title_font = pygame.font.SysFont("Arial", 36, bold=True)
    label_font = pygame.font.SysFont("Arial", 18, bold=True)
    desc_font = pygame.font.SysFont("Arial", 14)
    small_font = pygame.font.SysFont("Arial", 14, bold=True)

    icon_x = 40
    text_x = 70
    r = 14
    spacing = 55

    def draw_pu(cy, draw_icon, color, name, desc_text):
        draw_icon(icon_x, cy + 12, r)
        name_surf = label_font.render(name, True, color)
        screen.blit(name_surf, (text_x, cy))
        d_surf = desc_font.render(desc_text, True, (180, 180, 180))
        screen.blit(d_surf, (text_x, cy + 22))

    if page == 0:
        title = title_font.render("Powerups", True, TEXT_COLOR)
        screen.blit(title, title.get_rect(center=(WIDTH // 2, 35)))
        y = 70

        def icon_ball(cx, cy, radius):
            pygame.draw.circle(screen, COLLECTIBLE_COLOR, (cx, cy), radius)
            sym = small_font.render("+", True, BG_COLOR)
            screen.blit(sym, sym.get_rect(center=(cx, cy)))
        draw_pu(y, icon_ball, COLLECTIBLE_COLOR, "Extra Ball",
                "Collect to gain +1 ball next round")
        y += spacing

        # Ordered by unlock level
        def icon_bomb(cx, cy, radius):
            pygame.draw.circle(screen, BOMB_COLOR, (cx, cy), radius)
            sym = small_font.render("B", True, TEXT_COLOR)
            screen.blit(sym, sym.get_rect(center=(cx, cy)))
        draw_pu(y, icon_bomb, BOMB_COLOR, f"Bomb (lvl {UNLOCK['bombs']})",
                "Hit to detonate. 50% HP damage in radius. Chains PUs")
        y += spacing

        def icon_lightning(cx, cy, radius):
            pygame.draw.circle(screen, LIGHTNING_COLOR, (cx, cy), radius)
            sz = radius * 0.6
            points = [
                (cx - sz * 0.3, cy - sz), (cx + sz * 0.2, cy - sz * 0.1),
                (cx - sz * 0.1, cy - sz * 0.1), (cx + sz * 0.3, cy + sz),
                (cx - sz * 0.2, cy + sz * 0.1), (cx + sz * 0.1, cy + sz * 0.1),
            ]
            pygame.draw.polygon(screen, TEXT_COLOR, points)
        draw_pu(y, icon_lightning, LIGHTNING_COLOR, f"Lightning (lvl {UNLOCK['lightning']})",
                "Each ball hit triggers strikes on random targets")
        y += spacing

        def icon_cage(cx, cy, radius):
            pygame.draw.circle(screen, CAGE_COLOR, (cx, cy), radius)
            pygame.draw.circle(screen, CAGE_COLOR, (cx, cy), radius, 2)
            sym = small_font.render("#", True, BG_COLOR)
            screen.blit(sym, sym.get_rect(center=(cx, cy)))
        draw_pu(y, icon_cage, CAGE_COLOR, f"Cage (lvl {UNLOCK['cage']})",
                "Captures balls. Releases after 4s, when full, or 0 HP")
        y += spacing

        def icon_fireball(cx, cy, radius):
            pygame.draw.circle(screen, FIREBALL_COLOR, (cx, cy), radius)
            pygame.draw.circle(screen, FIREBALL_GLOW, (cx, cy), radius - 3)
            sym = small_font.render("F", True, BG_COLOR)
            screen.blit(sym, sym.get_rect(center=(cx, cy)))
        draw_pu(y, icon_fireball, FIREBALL_COLOR, f"Fireball (lvl {UNLOCK['fireball']})",
                "Ball passes through bricks. Redirects upward")
        y += spacing

        def icon_paddle(cx, cy, radius):
            pygame.draw.line(screen, PADDLE_COLOR,
                             (cx - radius, cy), (cx + radius, cy), PADDLE_THICKNESS + 2)
        draw_pu(y, icon_paddle, PADDLE_COLOR, f"Paddle (lvl {UNLOCK['paddle']})",
                "Rotating paddle. Bounces balls. Lasts 1 round")
        y += spacing

    elif page == 1:
        title = title_font.render("Powerups (2)", True, TEXT_COLOR)
        screen.blit(title, title.get_rect(center=(WIDTH // 2, 35)))
        y = 70

        def icon_freeze(cx, cy, radius):
            pygame.draw.circle(screen, FREEZE_COLOR, (cx, cy), radius)
            pygame.draw.circle(screen, TEXT_COLOR, (cx, cy), radius, 2)
            draw_snowflake(screen, cx, cy, radius - 2)
        draw_pu(y, icon_freeze, FREEZE_COLOR, f"Freeze (lvl {UNLOCK['freeze']})",
                "No advance, no new bricks, no +ball. Pure extra shot")
        y += spacing

        def icon_laser_h(cx, cy, radius):
            pygame.draw.circle(screen, LASER_H_COLOR, (cx, cy), radius)
            pygame.draw.line(screen, TEXT_COLOR, (cx - radius + 3, cy), (cx + radius - 3, cy), 2)
        draw_pu(y, icon_laser_h, LASER_H_COLOR, f"Laser H (lvl {UNLOCK['laser']})",
                "Beam cuts across row. Chains PUs")
        y += spacing

        def icon_laser_v(cx, cy, radius):
            pygame.draw.circle(screen, LASER_V_COLOR, (cx, cy), radius)
            pygame.draw.line(screen, TEXT_COLOR, (cx, cy - radius + 3), (cx, cy + radius - 3), 2)
        draw_pu(y, icon_laser_v, LASER_V_COLOR, f"Laser V (lvl {UNLOCK['laser']})",
                "Beam cuts down column. Chains PUs")
        y += spacing

        def icon_homing(cx, cy, radius):
            pygame.draw.circle(screen, HOMING_COLOR, (cx, cy), radius)
            sym = small_font.render("H", True, BG_COLOR)
            screen.blit(sym, sym.get_rect(center=(cx, cy)))
        draw_pu(y, icon_homing, HOMING_COLOR, f"Homing (lvl {UNLOCK['homing']})",
                "Ball steers toward nearest brick (10s)")
        y += spacing

        def icon_skull(cx, cy, radius):
            pygame.draw.circle(screen, SKULL_COLOR, (cx, cy), radius)
            sym = small_font.render("X", True, TEXT_COLOR)
            screen.blit(sym, sym.get_rect(center=(cx, cy)))
        draw_pu(y, icon_skull, SKULL_COLOR, f"Skull (lvl {UNLOCK['skull']})",
                "Halves balls, brick HP, and future difficulty")
        y += spacing

        def icon_acid(cx, cy, radius):
            pygame.draw.circle(screen, ACID_COLOR, (cx, cy), radius)
            sym = small_font.render("A", True, BG_COLOR)
            screen.blit(sym, sym.get_rect(center=(cx, cy)))
        draw_pu(y, icon_acid, ACID_COLOR, f"Acid (lvl {UNLOCK['acid']})",
                "Nearby bricks lose 1 HP/sec for 10s (radius 3)")
        y += spacing

        def icon_wall(cx, cy, radius):
            pygame.draw.circle(screen, WALL_COLOR, (cx, cy), radius)
            sym = small_font.render("=", True, BG_COLOR)
            screen.blit(sym, sym.get_rect(center=(cx, cy)))
        draw_pu(y, icon_wall, WALL_COLOR, f"Wall (lvl {UNLOCK['wall']})",
                "Blocks bricks in column. HP = level. Balls damage it")
        y += spacing

    elif page == 2:
        title = title_font.render("Controls", True, TEXT_COLOR)
        screen.blit(title, title.get_rect(center=(WIDTH // 2, 35)))
        y = 80
        line_h = 30
        controls = [
            ("Aim & Fire", "Click to aim, release to fire"),
            ("Redirect", "Hold mouse during fire to change direction"),
            ("Fast Forward", "Hold Space for 4x speed"),
            ("Gravity Pull", "After 10 wall bounces, ball curves downward"),
            ("Board Clear", "Destroy all bricks = BONUS +1 ball"),
            ("PU Chance", "Higher efficiency = more powerup spawns (max +20%)"),
            ("Brick Merge", "15% chance new brick merges with one below"),
        ]
        for name, desc in controls:
            name_surf = label_font.render(name, True, TEXT_COLOR)
            screen.blit(name_surf, (30, y))
            desc_surf = desc_font.render(desc, True, (160, 160, 180))
            screen.blit(desc_surf, (30, y + 22))
            y += line_h + 25

    # Page indicator and navigation
    page_text = desc_font.render(f"Page {page + 1}/{HELP_PAGES}", True, (140, 140, 160))
    screen.blit(page_text, page_text.get_rect(center=(WIDTH // 2, HEIGHT - 55)))

    nav = desc_font.render("Click left/right side to change page, center to go back",
                           True, (120, 120, 140))
    screen.blit(nav, nav.get_rect(center=(WIDTH // 2, HEIGHT - 30)))


def draw_aim_line(screen: pygame.Surface, lx: float, ly: float, angle: float,
                  mouse_pos: tuple[int, int]):
    """Draw a dotted line from launch point to mouse position, with crosshair at mouse."""
    mx, my = mouse_pos
    min_y = TOP_UI_HEIGHT + CELL_SIZE * 3
    # Clamp crosshair position
    cx, cy = mx, max(my, min_y)
    dist_to_crosshair = math.hypot(cx - lx, cy - ly)
    dx = math.cos(angle)
    dy = math.sin(angle)
    dot_spacing = 14
    max_dots = max(1, int(dist_to_crosshair / dot_spacing))
    for i in range(1, max_dots + 1):
        x = lx + dx * dot_spacing * i
        y = ly + dy * dot_spacing * i
        if y < min_y or x < 0 or x > WIDTH:
            break
        pygame.draw.circle(screen, AIM_DOT_COLOR, (int(x), int(y)), 2)
    size = 10
    pygame.draw.line(screen, AIM_DOT_COLOR, (cx - size, cy), (cx + size, cy), 2)
    pygame.draw.line(screen, AIM_DOT_COLOR, (cx, cy - size), (cx, cy + size), 2)
    pygame.draw.circle(screen, AIM_DOT_COLOR, (cx, cy), size, 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Bricks")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("Arial", 22, bold=True)
    small_font = pygame.font.SysFont("Arial", 16, bold=True)

    game = Game()
    menu_rects = (None, None, None, None)  # simple, classic, adv, help

    mouse_held = False

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_held = True
                mx, my = event.pos
                if game.phase == "menu":
                    simple_rect, classic_rect, adv_rect, help_rect = menu_rects
                    if simple_rect and simple_rect.collidepoint(mx, my):
                        game.mode = "simple"
                        game.reset()
                        game.start_round()
                    elif classic_rect and classic_rect.collidepoint(mx, my):
                        game.mode = "classic"
                        game.reset()
                        game.start_round()
                    elif adv_rect and adv_rect.collidepoint(mx, my):
                        game.mode = "advanced"
                        game.reset()
                        game.start_round()
                    elif help_rect and help_rect.collidepoint(mx, my):
                        game.phase = "help"
                        game._help_page = 0
                elif game.phase == "help":
                    if mx < WIDTH // 3:
                        game._help_page = max(0, game._help_page - 1)
                    elif mx > WIDTH * 2 // 3:
                        game._help_page = min(HELP_PAGES - 1, game._help_page + 1)
                    else:
                        game.phase = "menu"
                elif game.phase == "aim":
                    game.begin_fire()
                elif game.phase == "gameover":
                    game.reset()

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                mouse_held = False

        mouse_pos = pygame.mouse.get_pos()

        # --- Speed multiplier ---
        keys = pygame.key.get_pressed()
        speed_mult = 1.0
        # Manual fast-forward with Space
        if keys[pygame.K_SPACE] and game.phase in ("fire", "running"):
            speed_mult = 4.0
            # Every 10 sec at high speed, add 1 gravity pull to all alive balls
            if not hasattr(game, '_speed_gravity_timer'):
                game._speed_gravity_timer = 10.0
            game._speed_gravity_timer -= dt * speed_mult
            if game._speed_gravity_timer <= 0:
                game._speed_gravity_timer = 10.0
                for b in game.balls:
                    if b.alive:
                        _apply_gravity(b)
        else:
            game._speed_gravity_timer = 10.0

        # --- Phase updates ---
        if game.phase == "menu":
            menu_rects = draw_menu(screen)
            pygame.display.flip()
            continue
        elif game.phase == "help":
            draw_help(screen, getattr(game, '_help_page', 0))
            pygame.display.flip()
            continue
        elif game.phase == "advancing":
            game.advance_anim -= dt
            if game.advance_anim <= 0:
                game.advance_anim = 0
                game.phase = "aim"
        elif game.phase == "aim":
            game.update_aim(mouse_pos)
        elif game.phase == "fire":
            # If mouse is held, redirect aim in real-time
            if mouse_held:
                game.update_aim_live(mouse_pos)
            game.update_fire(dt)
            game.update_running(speed_mult)
        elif game.phase == "running":
            game.update_running(speed_mult)

        # Update explosion and lightning bolt timers
        game.explosions = [e for e in game.explosions if e["timer"] > 0]
        for e in game.explosions:
            e["timer"] -= dt
        game.lightning_bolts = [b for b in game.lightning_bolts if b["timer"] > 0]
        for b in game.lightning_bolts:
            b["timer"] -= dt
        if game.bonus_text_timer > 0:
            game.bonus_text_timer -= dt
        if game.unlock_timer > 0:
            game.unlock_timer -= dt
        if hasattr(game, '_danger_timer') and game._danger_timer > 0:
            game._danger_timer -= dt
        if game.freeze_wave:
            game.freeze_wave["radius"] += game.freeze_wave["speed"] * dt
            if game.freeze_wave["radius"] >= game.freeze_wave["max_radius"]:
                game.freeze_wave = None
        game.laser_beams = [b for b in game.laser_beams if b["timer"] > 0]
        for b in game.laser_beams:
            b["timer"] -= dt
        if game.skull_wave:
            game.skull_wave["radius"] += game.skull_wave["speed"] * dt
            if game.skull_wave["radius"] >= game.skull_wave["max_radius"]:
                game.skull_wave = None
        if hasattr(game, '_fire_counter_fade') and game._fire_counter_fade > 0 and game.balls_to_fire <= 0:
            game._fire_counter_fade -= dt

        # Hide cursor when crosshair is shown
        show_crosshair = game.phase == "aim" or (game.phase == "fire" and mouse_held)
        pygame.mouse.set_visible(not show_crosshair)

        draw_game(screen, game, font, small_font, mouse_held)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
