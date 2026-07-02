"""BricksRT game logic — no rendering, no display dependency."""

import json
import math
import os
import random
from dataclasses import dataclass

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

PROJECTILE_RADIUS = 5
PROJECTILE_SPEED = 600  # px per second
GUN_COOLDOWN = 0.12  # seconds between shots
GUN_RELOAD_DELAY = 1.0  # seconds before returned ammo is available
STARTING_GUN_AMMO = 1
AMMO_PER_PICKUP = 1

ADVANCE_SPEED_BASE = 6.0   # px/sec at start
ADVANCE_SPEED_MAX = 25.0   # cap

BOMB_RADIUS_CELLS = 1.5

ACID_RADIUS_CELLS = 1.5
ACID_DURATION = 5.0   # seconds
ACID_TICK = 1.0       # seconds between ticks

FREEZE_DURATION = 5.0  # seconds
REVERSE_DURATION = 3.0  # seconds

FIREBALL_CHARGES = 5    # shots as fireball per pickup
HOMING_CHARGES = 5      # shots as homing per pickup

LIGHTNING_STRIKES = 6      # bricks hit per lightning trigger
LIGHTNING_BOLT_TTL = 0.35  # seconds a bolt stays visible

SKULL_START = 600.0     # seconds of game time before skulls appear
SKULL_INTERVAL = 300.0  # seconds between skull spawns
SKULL_ROWS = 4          # skulls spawn only in the bottom N usable rows

MERGE_CHANCE = 0.25  # chance a spawning square fuses with the one below

MORTAR_TYPES = ["bomb", "mine", "acid", "wall"]
MORTAR_COOLDOWN = 0.6  # seconds between mortar shots

# Unlock thresholds (wave number)
UNLOCK = {
    "mines": 3, "wall": 3, "bombs": 5, "fireball": 7, "acid": 8,
    "freeze": 10, "reverse": 10, "homing": 11,
    "round": 15, "diamond": 15,
    "lightning": 20,
    "hexagon": 30, "trapezoid": 30, "wide": 30,
    "triangle": 50, "shields": 60, "merging": 70,
}


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def cell_rect(col: int, row: int, shape: str = "square", y_offset: float = 0) -> pygame.Rect:
    """Pixel Rect for a brick (visual, with gaps)."""
    x = col * CELL_SIZE + BRICK_GAP
    y = GRID_TOP + row * CELL_SIZE + BRICK_GAP + y_offset
    if shape == "wide":
        return pygame.Rect(x, y, CELL_SIZE * 2 - BRICK_GAP * 2, BRICK_SIZE)
    if shape == "tall":
        return pygame.Rect(x, y, BRICK_SIZE, CELL_SIZE * 2 - BRICK_GAP * 2)
    return pygame.Rect(x, y, BRICK_SIZE, BRICK_SIZE)


def cell_rect_full(col: int, row: int, shape: str = "square", y_offset: float = 0) -> pygame.Rect:
    """Full cell Rect (no gaps) for collision."""
    x = col * CELL_SIZE
    y = GRID_TOP + row * CELL_SIZE + y_offset
    if shape == "wide":
        return pygame.Rect(x, y, CELL_SIZE * 2, CELL_SIZE)
    if shape == "tall":
        return pygame.Rect(x, y, CELL_SIZE, CELL_SIZE * 2)
    return pygame.Rect(x, y, CELL_SIZE, CELL_SIZE)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

@dataclass
class Brick:
    col: int
    row: int
    hp: int
    shape: str = "square"
    tri_dir: str = "up"
    shield: int = 0
    held: float = 0.0    # px held back by a wall/stack this frame
    acid_t: float = 0.0  # seconds of acid tint remaining

    def cells(self) -> list[tuple[int, int]]:
        """Grid cells occupied by this brick."""
        out = [(self.col, self.row)]
        if self.shape == "wide":
            out.append((self.col + 1, self.row))
        if self.shape == "tall":
            out.append((self.col, self.row + 1))
        return out

    def cols(self) -> list[int]:
        out = [self.col]
        if self.shape == "wide":
            out.append(self.col + 1)
        return out

    @property
    def extra_height(self) -> int:
        return CELL_SIZE if self.shape == "tall" else 0


class Projectile:
    def __init__(self, pos: pygame.math.Vector2, vel: pygame.math.Vector2):
        self.pos = pygame.math.Vector2(pos)
        self.vel = pygame.math.Vector2(vel)
        self.alive = True
        self.exited_bottom = False
        self.border_hits = 0
        self.fireball = False
        self.homing = False
        self.homing_timer = 0.0

    def update(self, dt: float):
        if not self.alive:
            return
        self.pos += self.vel * dt

        # Wall bounces
        if self.pos.x - PROJECTILE_RADIUS < 0:
            self.pos.x = PROJECTILE_RADIUS
            self.vel.x = abs(self.vel.x)
            self.border_hits += 1
        elif self.pos.x + PROJECTILE_RADIUS > WIDTH:
            self.pos.x = WIDTH - PROJECTILE_RADIUS
            self.vel.x = -abs(self.vel.x)
            self.border_hits += 1

        # Ceiling bounce
        if self.pos.y - PROJECTILE_RADIUS < GRID_TOP:
            self.pos.y = GRID_TOP + PROJECTILE_RADIUS
            self.vel.y = abs(self.vel.y)
            self.border_hits += 1

        # Floor: exit and return ammo
        if self.pos.y + PROJECTILE_RADIUS >= GRID_BOTTOM:
            self.alive = False
            self.exited_bottom = True


def _apply_gravity(proj: Projectile, dt: float):
    """Nudge projectile toward straight down (prevents infinite bouncing)."""
    current = math.atan2(proj.vel.y, proj.vel.x)
    target = math.pi / 2
    diff = target - current
    while diff > math.pi:
        diff -= 2 * math.pi
    while diff < -math.pi:
        diff += 2 * math.pi
    max_pull = math.radians(6) * dt
    pull = max(-max_pull, min(max_pull, diff))
    new_angle = current + pull
    speed = proj.vel.length()
    proj.vel.x = math.cos(new_angle) * speed
    proj.vel.y = math.sin(new_angle) * speed


def _jagged_path(points: list[tuple[float, float]],
                 steps: int = 5, spread: float = 8.0) -> list[tuple[float, float]]:
    """Subdivide a polyline with random perpendicular offsets (lightning look)."""
    out: list[tuple[float, float]] = [points[0]]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1:
            out.append((x2, y2))
            continue
        nx, ny = -dy / length, dx / length  # perpendicular unit
        for i in range(1, steps):
            t = i / steps
            off = random.uniform(-spread, spread)
            out.append((x1 + dx * t + nx * off, y1 + dy * t + ny * off))
        out.append((x2, y2))
    return out


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class Game:
    def __init__(self):
        self.highscore = load_highscore("realtime")
        self.reset()

    def reset(self):
        self.phase = "menu"  # menu | playing | paused | gameover
        self.wave = 0
        self.game_time = 0.0
        self.highscore = load_highscore("realtime")
        self.new_best = False

        # Bricks
        self.bricks: list[Brick] = []
        self.brick_offset = 0.0  # sub-cell scroll offset in pixels

        # Gun
        self.gun_x = WIDTH / 2  # gun position, drifts toward exit points
        self.gun_ammo = STARTING_GUN_AMMO
        self.gun_cooldown = 0.0
        self.gun_reloading = 0  # ammo pending reload
        self.gun_reload_timer = 0.0
        self.ammo_debt = 0  # skull penalty: eats returning shots
        self.projectiles: list[Projectile] = []

        # Mortar ammo — count per type, player selects with scroll / 1-4
        self.mortar_ammo: dict[str, int] = {t: 0 for t in MORTAR_TYPES}
        self.mortar_sel = 0  # index into MORTAR_TYPES
        self.mortar_cooldown = 0.0

        # Gun ammo modifiers
        self.fireball_charges = 0  # next N shots are fireballs
        self.homing_charges = 0    # next N shots are homing

        # Field pickups (advance with bricks, ball hit to collect):
        # {col, row, type} — type: ammo | bomb | mine | acid | wall |
        # fireball | homing
        self.pickups: list[dict] = []

        # Placed items from mortar fire (stationary)
        self.placed_mines: list[dict] = []  # {x, y} — explode when brick touches
        self.placed_acids: list[dict] = []  # {x, y, timer, tick} — area DoT
        self.placed_walls: list[dict] = []  # {y, hp} — horizontal barrier
        self.wall_weight = 0  # total HP resting on walls (for HUD)

        # Stationary AoE PUs (pixel coords, ball or brick contact to trigger)
        self.placed_freezes: list[dict] = []   # {x, y}
        self.placed_reverses: list[dict] = []  # {x, y}
        self.placed_lightnings: list[dict] = []  # {x, y}
        self.placed_skulls: list[dict] = []      # {x, y}
        self.skull_timer = 0.0  # counts down to next skull spawn

        # Aim
        self.aim_angle: float = -math.pi / 2
        self.crosshair: tuple[int, int] = (WIDTH // 2, HEIGHT // 2)

        # Visual effects
        self.explosions: list[dict] = []
        # Mortar shells in flight: {sx, sy, tx, ty, type, t, duration}
        self.mortar_shells: list[dict] = []
        self.freeze_timer = 0.0  # seconds remaining of freeze
        self.freeze_wave: dict | None = None  # {x, y, radius, max_radius, speed}
        self.reverse_timer = 0.0  # seconds remaining of reverse
        self.reverse_wave: dict | None = None  # {x, y, height, max_height, speed}
        self.skull_wave: dict | None = None  # {x, y, radius, max_radius, speed}
        self.lightning_bolts: list[dict] = []  # {points, timer}

        # Advance speed
        self.advance_speed = ADVANCE_SPEED_BASE

    def start(self):
        self.reset()
        self.phase = "playing"
        self.gun_cooldown = 0.5  # aim delay before first shot
        self.spawn_wave()

    def save_if_record(self):
        """Persist the highscore if the current run beats it."""
        if self.wave > self.highscore:
            self.highscore = self.wave
            self.new_best = True
            save_highscore("realtime", self.wave)

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    def update(self, dt: float):
        if self.phase != "playing":
            return

        self.game_time += dt

        # Freeze countdown
        if self.freeze_timer > 0:
            self.freeze_timer -= dt

        # Reverse countdown
        if self.reverse_timer > 0:
            self.reverse_timer -= dt

        # Freeze wave animation
        if self.freeze_wave:
            self.freeze_wave["radius"] += self.freeze_wave["speed"] * dt
            if self.freeze_wave["radius"] >= self.freeze_wave["max_radius"]:
                self.freeze_wave = None

        # Reverse wave animation (vertical line radiates up)
        if self.reverse_wave:
            self.reverse_wave["height"] += self.reverse_wave["speed"] * dt
            if self.reverse_wave["height"] >= self.reverse_wave["max_height"]:
                self.reverse_wave = None

        # Skull wave animation
        if self.skull_wave:
            self.skull_wave["radius"] += self.skull_wave["speed"] * dt
            if self.skull_wave["radius"] >= self.skull_wave["max_radius"]:
                self.skull_wave = None

        # Skulls spawn at intervals late in the game
        if self.game_time >= SKULL_START:
            self.skull_timer -= dt
            if self.skull_timer <= 0:
                self.skull_timer = SKULL_INTERVAL
                # Bottom rows only: shootable early, or a natural emergency
                # brake when bricks push far enough down to touch it
                free = [cell for cell in self._free_cells()
                        if cell[1] >= MAX_ROWS - SKULL_ROWS]
                if free:
                    c, r = random.choice(free)
                    rect = cell_rect(c, r, "square", self.brick_offset)
                    self.placed_skulls.append({
                        "x": float(rect.centerx), "y": float(rect.centery),
                    })

        # Gradually increase advance speed
        minutes = self.game_time / 60.0
        self.advance_speed = min(ADVANCE_SPEED_MAX,
                                 ADVANCE_SPEED_BASE + minutes * 2.0)

        # Advance bricks smoothly (skip if frozen)
        if self.freeze_timer <= 0:
            if self.reverse_timer > 0:
                # Reverse: bricks move upward
                self.brick_offset -= self.advance_speed * dt
                while self.brick_offset < 0:
                    self.brick_offset += CELL_SIZE
                    self._retreat_rows()
            else:
                self.brick_offset += self.advance_speed * dt
                while self.brick_offset >= CELL_SIZE:
                    self.brick_offset -= CELL_SIZE
                    self._advance_rows()
                    if self.phase != "playing":
                        return

        # Pin bricks at walls (smooth per-brick blocking)
        self._update_wall_blocking()

        # Game over check (smooth — mid-cell)
        if self._check_game_over():
            return

        # Weapon cooldowns
        if self.gun_cooldown > 0:
            self.gun_cooldown -= dt
        if self.mortar_cooldown > 0:
            self.mortar_cooldown -= dt

        # Update projectiles
        for p in self.projectiles:
            if not p.alive:
                continue
            p.update(dt)
            # Homing steering toward nearest brick
            if p.homing and p.alive and self.bricks:
                p.homing_timer -= dt
                if p.homing_timer <= 0:
                    p.homing = False
                else:
                    self._steer_homing(p, dt)
            if p.border_hits >= 10:
                _apply_gravity(p, dt)
            if p.alive:
                self._collide_bricks(p)
            if p.alive:
                self._collide_pickups(p)
            if p.alive:
                self._collide_walls(p)
            if p.alive:
                for placed, trigger in self._placed_aoe():
                    self._collide_placed_aoe(p, placed, trigger)

        # Return ammo for projectiles that exited bottom (into reload queue).
        # Skull debt eats returning shots instead of refunding them.
        for p in self.projectiles:
            if not p.alive and p.exited_bottom:
                if self.ammo_debt > 0:
                    self.ammo_debt -= 1
                else:
                    self.gun_reloading += 1
                    if self.gun_reload_timer <= 0:
                        self.gun_reload_timer = GUN_RELOAD_DELAY
                # Nudge gun toward exit point (10% of distance)
                self.gun_x += (p.pos.x - self.gun_x) * 0.1
                self.gun_x = max(PROJECTILE_RADIUS,
                                 min(WIDTH - PROJECTILE_RADIUS, self.gun_x))
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Reload timer: pending ammo becomes available after delay
        if self.gun_reloading > 0 and self.gun_reload_timer > 0:
            self.gun_reload_timer -= dt
            if self.gun_reload_timer <= 0:
                self.gun_ammo += self.gun_reloading
                self.gun_reloading = 0

        # Mines: explode when any brick overlaps them
        self._check_mines()

        # AoE pickups also trigger on brick contact
        for placed, trigger in self._placed_aoe():
            self._check_placed_aoe_brick(placed, trigger)

        # Acid zones: tick damage on nearby bricks
        self._update_acids(dt)

        # Mark bricks touched by acid, decay timer when outside
        self._update_acid_tint(dt)

        # Walls: grace countdown, then break when weight >= max_weight
        self.wall_weight = sum(b.hp for b in self.bricks
                               if b.held > 0) if self.placed_walls else 0
        dead_walls: list[dict] = []
        for w in self.placed_walls:
            if w.get("grace", 0) > 0:
                w["grace"] -= dt
                continue
            w["ttl"] -= dt
            if w["ttl"] <= 0 or self.wall_weight >= w["max_weight"]:
                dead_walls.append(w)
        if dead_walls:
            self.placed_walls = [w for w in self.placed_walls
                                 if w not in dead_walls]
            for b in self.bricks:
                b.held = 0.0

        # Update mortar shells in flight
        landed = [s for s in self.mortar_shells if s["t"] + dt / s["duration"] >= 1.0]
        for shell in self.mortar_shells:
            shell["t"] += dt / shell["duration"]
        self.mortar_shells = [s for s in self.mortar_shells if s not in landed]
        for shell in landed:
            self._land_mortar(shell)

        # Decay visual effects
        self.explosions = [e for e in self.explosions if e["timer"] > 0]
        for e in self.explosions:
            e["timer"] -= dt
        self.lightning_bolts = [b for b in self.lightning_bolts
                                if b["timer"] > 0]
        for b in self.lightning_bolts:
            b["timer"] -= dt

    def _steer_homing(self, p: Projectile, dt: float):
        best_dist = float('inf')
        best_tx, best_ty = p.pos.x, p.pos.y - 100
        for brick in self.bricks:
            rect = cell_rect(brick.col, brick.row, brick.shape,
                             self._brick_off(brick))
            cx, cy = rect.center
            d = math.hypot(cx - p.pos.x, cy - p.pos.y)
            if d < best_dist:
                best_dist = d
                best_tx, best_ty = cx, cy
        target_angle = math.atan2(best_ty - p.pos.y, best_tx - p.pos.x)
        current_angle = math.atan2(p.vel.y, p.vel.x)
        diff = target_angle - current_angle
        while diff > math.pi:
            diff -= 2 * math.pi
        while diff < -math.pi:
            diff += 2 * math.pi
        max_steer = math.radians(120) * dt
        steer = max(-max_steer, min(max_steer, diff))
        new_angle = current_angle + steer
        speed = p.vel.length()
        p.vel.x = math.cos(new_angle) * speed
        p.vel.y = math.sin(new_angle) * speed

    def _brick_off(self, brick: Brick) -> float:
        """Effective y offset for a brick (accounts for wall hold-back)."""
        return self.brick_offset - brick.held

    def _update_wall_blocking(self):
        """Pin bricks at walls, and stack bricks on top of stopped bricks."""
        # Reset all held values — recalculate from scratch each frame
        for brick in self.bricks:
            brick.held = 0.0

        # First pass: pin bricks directly at walls
        for brick in self.bricks:
            bottom = (GRID_TOP + (brick.row + 1) * CELL_SIZE
                      + brick.extra_height + self.brick_offset)
            for w in self.placed_walls:
                if bottom > w["y"]:
                    brick.held = bottom - w["y"]
                    break

        # Second pass: process bottom-to-top so bricks stack on stopped bricks.
        # Sort by effective bottom position (highest row = furthest down = first).
        sorted_bricks = sorted(self.bricks,
                               key=lambda b: -(b.row * CELL_SIZE
                                               + self._brick_off(b)))
        # Build occupied map: for each column, track the topmost blocked pixel
        # (i.e. the top edge of the highest stopped brick per column)
        col_barrier: dict[int, float] = {}  # col -> min top pixel of stopped bricks

        for brick in sorted_bricks:
            eff_offset = self.brick_offset - brick.held
            top = GRID_TOP + brick.row * CELL_SIZE + eff_offset
            bottom = top + CELL_SIZE + brick.extra_height
            cols = brick.cols()

            # Check if this brick is blocked (has held > 0)
            if brick.held > 0:
                for c in cols:
                    if c not in col_barrier or top < col_barrier[c]:
                        col_barrier[c] = top
            else:
                # Check if any column has a barrier below this brick
                for c in cols:
                    if c in col_barrier and bottom > col_barrier[c]:
                        brick.held += bottom - col_barrier[c]
                        # Recalculate top with new held
                        eff_offset = self.brick_offset - brick.held
                        top = GRID_TOP + brick.row * CELL_SIZE + eff_offset
                        for c2 in cols:
                            if c2 not in col_barrier or top < col_barrier[c2]:
                                col_barrier[c2] = top
                        break

    def _check_game_over(self) -> bool:
        for b in self.bricks:
            pixel_bottom = (GRID_TOP + (b.row + 1) * CELL_SIZE
                            + b.extra_height + self._brick_off(b))
            if pixel_bottom >= GRID_BOTTOM:
                self.phase = "gameover"
                self.save_if_record()
                return True
        return False

    def _advance_rows(self):
        """All items shift down one grid row. Spawn new wave at top."""
        # Build set of cells occupied by held bricks (they don't move)
        held_cells = set()
        for b in self.bricks:
            if b.held > 0:
                held_cells.update(b.cells())

        # Process bottom-to-top so lower bricks block upper ones
        for b in sorted(self.bricks, key=lambda x: -x.row):
            if b.held >= CELL_SIZE:
                b.held -= CELL_SIZE
                continue
            # Check if target cells are free
            new_row = b.row + 1
            target_cells = [(c, r + 1) for c, r in b.cells()]
            if any(cell in held_cells for cell in target_cells):
                # This brick can't advance — mark as held for 1 cell
                b.held += CELL_SIZE
                # Add this brick's cells to held set so bricks above stop too
                held_cells.update(b.cells())
            else:
                b.row = new_row
        for pu in self.pickups:
            pu["row"] += 1

        # Remove items scrolled past bottom
        self.bricks = [b for b in self.bricks if b.row <= MAX_ROWS]
        self.pickups = [p for p in self.pickups if p["row"] <= MAX_ROWS]

        # Check game over after advancing
        if self._check_game_over():
            return

        self.spawn_wave()

    def _retreat_rows(self):
        """All items shift up one grid row. Remove bricks pushed off top."""
        for b in self.bricks:
            b.row -= 1
        for pu in self.pickups:
            pu["row"] -= 1

        # Remove items pushed past top
        self.bricks = [b for b in self.bricks if b.row >= -1]
        self.pickups = [p for p in self.pickups if p["row"] >= -1]

    # ------------------------------------------------------------------
    # Wave spawning
    # ------------------------------------------------------------------

    def _distribute_blocked_hp(self, blocked_hp: dict[int, int]):
        """Distribute HP from blocked columns across connected held containers."""
        # Build held cell grid: (col, row) -> brick
        held_cells: dict[tuple[int, int], Brick] = {}
        for b in self.bricks:
            if b.held > 0:
                for cell in b.cells():
                    held_cells[cell] = b

        if not held_cells:
            return

        # Union-Find to group connected held cells
        parent: dict[tuple, tuple] = {}

        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for cell in held_cells:
            parent[cell] = cell

        # Connect adjacent held cells (up/down/left/right)
        for (c, r) in held_cells:
            for dc, dr in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nb = (c + dc, r + dr)
                if nb in held_cells:
                    union((c, r), nb)

        # Group cells by container
        containers: dict[tuple, list[tuple]] = {}
        for cell in held_cells:
            root = find(cell)
            containers.setdefault(root, []).append(cell)

        # Pool blocked HP per container, then distribute
        container_hp: dict[tuple, int] = {}
        for col, hp in blocked_hp.items():
            target = None
            for r in range(MAX_ROWS):
                if (col, r) in held_cells:
                    target = (col, r)
                    break
            if target is None:
                continue
            root = find(target)
            container_hp[root] = container_hp.get(root, 0) + hp

        for root, hp in container_hp.items():
            cells = containers[root]
            total = len(cells)
            hp_each = hp // total
            hp_rem = hp % total
            for i, cell in enumerate(cells):
                held_cells[cell].hp += hp_each + (1 if i < hp_rem else 0)

    def _free_cells(self) -> list[tuple[int, int]]:
        """Return grid cells not occupied. Excludes first and last row."""
        occupied = set()
        for b in self.bricks:
            occupied.update(b.cells())
        for pu in self.pickups:
            occupied.add((pu["col"], pu["row"]))
        # Convert pixel-based placed items to grid cells
        off = self.brick_offset
        for p in (self.placed_freezes + self.placed_reverses
                  + self.placed_lightnings + self.placed_skulls):
            col = int(p["x"] // CELL_SIZE)
            row = int((p["y"] - GRID_TOP - off) // CELL_SIZE)
            occupied.add((col, row))
        return [(c, r) for r in range(1, MAX_ROWS - 1)
                for c in range(COLS)
                if (c, r) not in occupied]

    def spawn_wave(self):
        self.wave += 1

        # Build map of occupied rows per column
        rows_by_col: dict[int, set[int]] = {}
        for b in self.bricks:
            for cb in b.cols():
                rows_by_col.setdefault(cb, set()).add(b.row)

        # A column is full if every row from 0 down to the lowest held
        # brick in that column is occupied.
        held_floor: dict[int, int] = {}  # col -> lowest held row
        for b in self.bricks:
            if b.held > 0:
                for cb in b.cols():
                    if cb not in held_floor or b.row > held_floor[cb]:
                        held_floor[cb] = b.row
        full_cols = set()
        for c, floor in held_floor.items():
            if c in rows_by_col:
                if all(r in rows_by_col[c] for r in range(floor + 1)):
                    full_cols.add(c)

        # Distribute HP to full columns using same spawn chance
        if full_cols:
            # Same logic as brick spawning: pick 3-6 random columns
            all_cols = list(range(COLS))
            random.shuffle(all_cols)
            spawn_count = random.randint(3, 6)
            spawn_candidates = all_cols[:spawn_count]
            blocked_hp_pre: dict[int, int] = {}
            for c in spawn_candidates:
                if c in full_cols:
                    blocked_hp_pre[c] = max(1, self.wave)
            if blocked_hp_pre:
                self._distribute_blocked_hp(blocked_hp_pre)

        # Columns occupied at row 0 can't receive new bricks
        row0_occupied = set()
        for b in self.bricks:
            if b.row == 0:
                row0_occupied.update(b.cols())
        available_cols = [c for c in range(COLS) if c not in row0_occupied]
        random.shuffle(available_cols)
        count = min(random.randint(4, 6), len(available_cols))
        brick_cols = available_cols[:count]
        remaining = [c for c in available_cols if c not in brick_cols]

        # Available shapes based on wave
        shapes = ["square"]
        weights = [30]
        if self.wave >= UNLOCK["round"]:
            shapes += ["round", "diamond"]
            weights += [18, 13]
        if self.wave >= UNLOCK["hexagon"]:
            shapes += ["hexagon", "trapezoid"]
            weights += [13, 14]
        if self.wave >= UNLOCK["triangle"]:
            shapes.append("triangle")
            weights.append(18)

        occupied = set()
        for c in brick_cols:
            if c in occupied:
                continue
            hp = max(1, self.wave)

            shape = random.choices(shapes, weights=weights)[0]

            # Wide brick: needs adjacent column free
            if (self.wave >= UNLOCK["wide"] and shape == "square"
                    and random.random() < 0.12
                    and c + 1 < COLS and c + 1 not in occupied
                    and c + 1 not in brick_cols
                    and c + 1 not in full_cols
                    and c + 1 not in row0_occupied):
                shape = "wide"
                occupied.add(c + 1)
                if c + 1 in remaining:
                    remaining.remove(c + 1)

            occupied.add(c)
            if shape == "wide":
                hp *= 2
            tri_dir = (random.choice(["up", "down", "left", "right"])
                       if shape == "triangle" else "up")
            shield = 0
            if self.wave >= UNLOCK["shields"] and random.random() < 0.15:
                shield = max(2, self.wave // 5)

            # Merging: a spawning square fuses with a square directly
            # below into one tall brick with combined HP
            if (shape == "square" and self.wave >= UNLOCK["merging"]
                    and random.random() < MERGE_CHANCE):
                below = next((b for b in self.bricks
                              if b.col == c and b.row == 1
                              and b.shape == "square"), None)
                if below is not None:
                    self.bricks.remove(below)
                    self.bricks.append(Brick(
                        col=c, row=0, hp=hp + below.hp, shape="tall",
                        shield=max(shield, below.shield)))
                    continue

            self.bricks.append(Brick(col=c, row=0, hp=hp, shape=shape,
                                     tri_dir=tri_dir, shield=shield))

        # Spawn ammo pickup (row 0 only, not during reverse, skip every 5th wave)
        if remaining and self.reverse_timer <= 0 and self.wave % 5 != 0:
            cc = random.choice(remaining)
            self.pickups.append({"col": cc, "row": 0, "type": "ammo"})

        # Helper: spawn grid-based PU on a free cell (not first or last row)
        def _spawn_grid(unlock_key, chance, ptype):
            if self.wave >= UNLOCK[unlock_key] and random.random() < chance:
                free = self._free_cells()
                if free:
                    c, r = random.choice(free)
                    self.pickups.append({"col": c, "row": r, "type": ptype})

        # Helper: spawn pixel-based PU on a free cell
        def _spawn_pixel(unlock_key, chance, target_list):
            if self.wave >= UNLOCK[unlock_key] and random.random() < chance:
                free = self._free_cells()
                if free:
                    c, r = random.choice(free)
                    rect = cell_rect(c, r, "square", self.brick_offset)
                    target_list.append({
                        "x": float(rect.centerx), "y": float(rect.centery),
                    })

        # Mortar PUs (grid-based, advance with bricks, ball hit to collect)
        _spawn_grid("mines", 0.30, "mine")
        _spawn_grid("bombs", 0.25, "bomb")
        _spawn_grid("acid", 0.20, "acid")
        _spawn_grid("wall", 0.15, "wall")

        # Gun PUs (grid-based, advance with bricks, ball hit to activate)
        _spawn_grid("fireball", 0.15, "fireball")
        _spawn_grid("homing", 0.12, "homing")

        # AoE PUs (pixel-based, stationary, ball hit to activate)
        _spawn_pixel("freeze", 0.12, self.placed_freezes)
        _spawn_pixel("reverse", 0.10, self.placed_reverses)
        _spawn_pixel("lightning", 0.10, self.placed_lightnings)

    # ------------------------------------------------------------------
    # Aim & fire
    # ------------------------------------------------------------------

    def update_aim(self, mouse_pos: tuple[int, int]):
        mx, my = mouse_pos
        self.crosshair = (mx, my)
        launch_x = self.gun_x
        launch_y = GRID_BOTTOM
        dx = mx - launch_x
        dy = my - launch_y
        if dy >= -5:
            dy = -5
        angle = math.atan2(dy, dx)
        angle = max(angle, -math.pi + 0.15)
        angle = min(angle, -0.15)
        self.aim_angle = angle

    def fire_gun(self) -> bool:
        if self.gun_ammo <= 0 or self.gun_cooldown > 0:
            return False
        self.gun_ammo -= 1
        self.gun_cooldown = GUN_COOLDOWN
        launch_x = self.gun_x
        launch_y = GRID_BOTTOM - PROJECTILE_RADIUS
        vel = pygame.math.Vector2(
            math.cos(self.aim_angle) * PROJECTILE_SPEED,
            math.sin(self.aim_angle) * PROJECTILE_SPEED,
        )
        p = Projectile(pygame.math.Vector2(launch_x, launch_y), vel)
        if self.fireball_charges > 0:
            p.fireball = True
            self.fireball_charges -= 1
        elif self.homing_charges > 0:
            p.homing = True
            p.homing_timer = 10.0  # 10 sec homing per projectile
            self.homing_charges -= 1
        self.projectiles.append(p)
        return True

    def cycle_mortar(self, step: int):
        """Cycle mortar type selection (scroll wheel)."""
        self.mortar_sel = (self.mortar_sel + step) % len(MORTAR_TYPES)

    def select_mortar(self, index: int):
        """Select mortar type directly (number keys)."""
        if 0 <= index < len(MORTAR_TYPES):
            self.mortar_sel = index

    def fire_mortar(self) -> bool:
        """Launch a mortar shell of the selected type toward the crosshair."""
        if self.mortar_cooldown > 0:
            return False
        mtype = MORTAR_TYPES[self.mortar_sel]
        if self.mortar_ammo[mtype] <= 0:
            # Fall back to the first type with ammo
            for t in MORTAR_TYPES:
                if self.mortar_ammo[t] > 0:
                    mtype = t
                    break
            else:
                return False
        self.mortar_ammo[mtype] -= 1
        self.mortar_cooldown = MORTAR_COOLDOWN
        mx, my = self.crosshair
        my = max(GRID_TOP, min(GRID_BOTTOM, my))
        # Launch from gun position
        sx, sy = self.gun_x, float(GRID_BOTTOM)
        dist = math.hypot(mx - sx, my - sy)
        duration = max(0.2, min(0.6, dist / 600))
        self.mortar_shells.append({
            "sx": sx, "sy": sy,       # start
            "tx": float(mx), "ty": float(my),  # target
            "type": mtype,
            "t": 0.0,                 # progress 0..1
            "duration": duration,
        })
        return True

    def _land_mortar(self, shell: dict):
        """Apply mortar effect when shell reaches target."""
        mx, my = shell["tx"], shell["ty"]
        mtype = shell["type"]
        if mtype == "bomb":
            self._explode(mx, my)
        elif mtype == "mine":
            self.placed_mines.append({"x": mx, "y": my})
        elif mtype == "acid":
            self.placed_acids.append({
                "x": mx, "y": my,
                "timer": ACID_DURATION, "tick": 0.0,
            })
        elif mtype == "wall":
            self.placed_walls.append({
                "y": my, "max_weight": max(1, self.wave) * 15,
                "grace": 2.0, "ttl": 12.0,
            })

    # ------------------------------------------------------------------
    # Brick collisions
    # ------------------------------------------------------------------

    def _collide_bricks(self, proj: Projectile):
        bx, by = proj.pos.x, proj.pos.y
        to_remove: list[int] = []

        if proj.fireball:
            # Fireball: pass through all bricks, 1 damage each, no bounce
            for i, brick in enumerate(self.bricks):
                off = self._brick_off(brick)
                rect = cell_rect_full(brick.col, brick.row, brick.shape, off)
                expanded = rect.inflate(PROJECTILE_RADIUS * 2,
                                        PROJECTILE_RADIUS * 2)
                if expanded.collidepoint(bx, by):
                    brick.hp -= 1
                    proj.border_hits = 0
                    if brick.hp <= 0:
                        to_remove.append(i)
        else:
            # Normal/homing: bounce off first brick hit
            for i, brick in enumerate(self.bricks):
                off = self._brick_off(brick)
                shape = brick.shape
                pre_vel_y = proj.vel.y
                pre_pos_y = proj.pos.y
                pre_pos_x = proj.pos.x

                if shape == "round":
                    hit = self._collide_round(proj, brick, off)
                elif shape == "diamond":
                    hit = self._collide_diamond(proj, brick, off)
                elif shape == "hexagon":
                    hit = self._collide_hexagon(proj, brick, off)
                elif shape == "trapezoid":
                    hit = self._collide_trapezoid(proj, brick, off)
                elif shape == "triangle":
                    hit = self._collide_triangle(proj, brick, off)
                else:
                    hit = self._collide_rect(proj, brick, off)

                if hit:
                    if brick.shield > 0:
                        rect_c = cell_rect_full(brick.col, brick.row,
                                                shape, off)
                        if shape in ("round", "diamond", "triangle"):
                            from_below = (pre_vel_y < 0
                                          and pre_pos_y > rect_c.centery)
                        else:
                            from_below = (pre_vel_y < 0
                                          and pre_pos_y > rect_c.centery
                                          and rect_c.left <= pre_pos_x <= rect_c.right)
                        if from_below:
                            brick.shield -= 1
                        else:
                            brick.hp -= 1
                    else:
                        brick.hp -= 1

                    proj.border_hits = 0
                    if brick.hp <= 0:
                        to_remove.append(i)
                    break

        for i in reversed(to_remove):
            self.bricks.pop(i)

    def _collide_rect(self, proj: Projectile, brick: Brick,
                      y_offset: float = 0) -> bool:
        bx, by = proj.pos.x, proj.pos.y
        rect = cell_rect_full(brick.col, brick.row, brick.shape, y_offset)
        expanded = rect.inflate(PROJECTILE_RADIUS * 2, PROJECTILE_RADIUS * 2)
        if not expanded.collidepoint(bx, by):
            return False

        cx, cy = rect.centerx, rect.centery
        dx, dy = bx - cx, by - cy
        half_w = rect.width / 2 + PROJECTILE_RADIUS
        half_h = rect.height / 2 + PROJECTILE_RADIUS
        ox = half_w - abs(dx)
        oy = half_h - abs(dy)
        if ox <= 0 or oy <= 0:
            return False

        buf = 1
        if ox < oy:
            if dx > 0:
                proj.pos.x = rect.right + PROJECTILE_RADIUS + buf
            else:
                proj.pos.x = rect.left - PROJECTILE_RADIUS - buf
            proj.vel.x = -proj.vel.x
        else:
            if dy > 0:
                proj.pos.y = rect.bottom + PROJECTILE_RADIUS + buf
            else:
                proj.pos.y = rect.top - PROJECTILE_RADIUS - buf
            proj.vel.y = -proj.vel.y
        return True

    def _collide_round(self, proj: Projectile, brick: Brick,
                       y_offset: float = 0) -> bool:
        bx, by = proj.pos.x, proj.pos.y
        rect = cell_rect(brick.col, brick.row, "square", y_offset)
        cx, cy = rect.center
        brick_radius = BRICK_SIZE / 2
        dx, dy = bx - cx, by - cy
        dist = math.hypot(dx, dy)
        min_dist = brick_radius + PROJECTILE_RADIUS
        if dist >= min_dist or dist == 0:
            return False
        nx, ny = dx / dist, dy / dist
        proj.pos.x = cx + nx * (min_dist + 1)
        proj.pos.y = cy + ny * (min_dist + 1)
        dot = proj.vel.x * nx + proj.vel.y * ny
        proj.vel.x -= 2 * dot * nx
        proj.vel.y -= 2 * dot * ny
        return True

    def _collide_diamond(self, proj: Projectile, brick: Brick,
                         y_offset: float = 0) -> bool:
        bx, by = proj.pos.x, proj.pos.y
        rect = cell_rect(brick.col, brick.row, "square", y_offset)
        cx, cy = rect.center
        half = BRICK_SIZE / 2
        dx, dy = bx - cx, by - cy
        man_dist = abs(dx) / half + abs(dy) / half
        threshold = 1.0 + PROJECTILE_RADIUS / half
        if man_dist >= threshold or man_dist == 0:
            return False
        if dx >= 0 and dy <= 0:
            nx, ny = 1.0, -1.0
        elif dx >= 0 and dy > 0:
            nx, ny = 1.0, 1.0
        elif dx < 0 and dy <= 0:
            nx, ny = -1.0, -1.0
        else:
            nx, ny = -1.0, 1.0
        length = math.hypot(nx, ny)
        nx /= length
        ny /= length
        push = (threshold - man_dist) * half
        proj.pos.x += nx * push
        proj.pos.y += ny * push
        dot = proj.vel.x * nx + proj.vel.y * ny
        proj.vel.x -= 2 * dot * nx
        proj.vel.y -= 2 * dot * ny
        return True

    def _collide_polygon(self, proj: Projectile, verts: list,
                         cx: float, cy: float) -> bool:
        bx, by = proj.pos.x, proj.pos.y
        n = len(verts)
        r = max(math.hypot(v[0] - cx, v[1] - cy) for v in verts)
        if (abs(bx - cx) > r + PROJECTILE_RADIUS + 4
                or abs(by - cy) > r + PROJECTILE_RADIUS + 4):
            return False

        min_dist_sq = float('inf')
        closest_x, closest_y = cx, cy
        for i in range(n):
            x1, y1 = verts[i]
            x2, y2 = verts[(i + 1) % n]
            ex, ey = x2 - x1, y2 - y1
            seg_len_sq = ex * ex + ey * ey
            if seg_len_sq == 0:
                continue
            t = max(0.0, min(1.0,
                             ((bx - x1) * ex + (by - y1) * ey) / seg_len_sq))
            px, py = x1 + t * ex, y1 + t * ey
            dsq = (bx - px) ** 2 + (by - py) ** 2
            if dsq < min_dist_sq:
                min_dist_sq = dsq
                closest_x, closest_y = px, py

        dist = math.sqrt(min_dist_sq)
        if dist >= PROJECTILE_RADIUS or dist == 0:
            # Check if ball is inside polygon
            area = sum(
                (verts[i][0] - cx) * (verts[(i + 1) % n][1] - cy)
                - (verts[(i + 1) % n][0] - cx) * (verts[i][1] - cy)
                for i in range(n))
            sign = 1 if area > 0 else -1
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
            dx, dy = bx - cx, by - cy
            dl = math.hypot(dx, dy)
            if dl == 0:
                dx, dy = 0, -1
            else:
                dx, dy = dx / dl, dy / dl
            proj.pos.x = cx + dx * (r + PROJECTILE_RADIUS)
            proj.pos.y = cy + dy * (r + PROJECTILE_RADIUS)
            dot = proj.vel.x * dx + proj.vel.y * dy
            proj.vel.x -= 2 * dot * dx
            proj.vel.y -= 2 * dot * dy
            return True

        nx = (bx - closest_x) / dist
        ny = (by - closest_y) / dist
        proj.pos.x = closest_x + nx * (PROJECTILE_RADIUS + 1)
        proj.pos.y = closest_y + ny * (PROJECTILE_RADIUS + 1)
        dot = proj.vel.x * nx + proj.vel.y * ny
        proj.vel.x -= 2 * dot * nx
        proj.vel.y -= 2 * dot * ny
        return True

    def _collide_hexagon(self, proj: Projectile, brick: Brick,
                         y_offset: float = 0) -> bool:
        rect = cell_rect(brick.col, brick.row, "square", y_offset)
        cx, cy = rect.center
        r = BRICK_SIZE / 2
        verts = [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
                  cy + r * math.sin(math.pi / 6 + i * math.pi / 3))
                 for i in range(6)]
        return self._collide_polygon(proj, verts, cx, cy)

    def _collide_trapezoid(self, proj: Projectile, brick: Brick,
                           y_offset: float = 0) -> bool:
        rect = cell_rect(brick.col, brick.row, "square", y_offset)
        cx, cy = rect.center
        hw, hh = BRICK_SIZE / 2, BRICK_SIZE / 2
        tw = hw * 0.6
        verts = [(cx - tw, cy - hh), (cx + tw, cy - hh),
                 (cx + hw, cy + hh), (cx - hw, cy + hh)]
        return self._collide_polygon(proj, verts, cx, cy)

    def tri_verts(self, brick: Brick, y_offset: float = 0):
        rect = cell_rect(brick.col, brick.row, "square", y_offset)
        cx, cy = rect.center
        h = BRICK_SIZE / 2
        d = brick.tri_dir
        if d == "up":
            return [(cx, cy - h), (cx + h, cy + h), (cx - h, cy + h)], cx, cy
        elif d == "down":
            return [(cx - h, cy - h), (cx + h, cy - h), (cx, cy + h)], cx, cy
        elif d == "left":
            return [(cx - h, cy), (cx + h, cy - h), (cx + h, cy + h)], cx, cy
        else:
            return [(cx - h, cy - h), (cx - h, cy + h), (cx + h, cy)], cx, cy

    def _collide_triangle(self, proj: Projectile, brick: Brick,
                          y_offset: float = 0) -> bool:
        verts, cx, cy = self.tri_verts(brick, y_offset)
        return self._collide_polygon(proj, verts, cx, cy)

    # ------------------------------------------------------------------
    # Pickup / placed-item collisions
    # ------------------------------------------------------------------

    def _collect_pickup(self, ptype: str):
        """Apply the effect of a collected field pickup."""
        if ptype == "ammo":
            self.gun_ammo += AMMO_PER_PICKUP
        elif ptype == "fireball":
            self.fireball_charges += FIREBALL_CHARGES
        elif ptype == "homing":
            self.homing_charges += HOMING_CHARGES
        else:  # bomb / mine / acid / wall — collected as mortar ammo
            self.mortar_ammo[ptype] += 1

    def _collide_pickups(self, proj: Projectile):
        bx, by = proj.pos.x, proj.pos.y
        off = self.brick_offset
        hit: list[dict] = []
        for pu in self.pickups:
            rect = cell_rect(pu["col"], pu["row"], "square", off)
            cx, cy = rect.center
            if math.hypot(bx - cx, by - cy) < PROJECTILE_RADIUS + BRICK_SIZE * 0.25:
                hit.append(pu)
                self._collect_pickup(pu["type"])
        if hit:
            self.pickups = [p for p in self.pickups if p not in hit]

    def _collide_walls(self, proj: Projectile):
        """Normal projectiles bounce off walls. Fireballs pass through."""
        if not proj.alive or proj.fireball:
            return
        py = proj.pos.y
        for w in self.placed_walls:
            wy = w["y"]
            if abs(py - wy) < PROJECTILE_RADIUS + 2:
                if proj.vel.y > 0:
                    proj.pos.y = wy - PROJECTILE_RADIUS - 1
                else:
                    proj.pos.y = wy + PROJECTILE_RADIUS + 1
                proj.vel.y = -proj.vel.y
                proj.border_hits = 0
                # Each bounce chips the wall: its weight capacity drops by 1,
                # so bouncing your own shots off a wall shortens its life.
                w["max_weight"] = max(0, w["max_weight"] - 1)
                break

    def _placed_aoe(self) -> list[tuple[list[dict], object]]:
        """(placed list, trigger fn) pairs for all stationary AoE pickups."""
        return [
            (self.placed_freezes, self._trigger_freeze),
            (self.placed_reverses, self._trigger_reverse),
            (self.placed_lightnings, self._trigger_lightning),
            (self.placed_skulls, self._trigger_skull),
        ]

    def _trigger_freeze(self, x: float, y: float):
        self.freeze_timer = FREEZE_DURATION
        self.freeze_wave = {
            "x": x, "y": y, "radius": 0,
            "max_radius": math.hypot(WIDTH, HEIGHT),
            "speed": 800,
        }

    def _trigger_reverse(self, x: float, y: float):
        self.reverse_timer = REVERSE_DURATION
        self.reverse_wave = {
            "x": x, "y": y,
            "height": 0, "max_height": GRID_BOTTOM - GRID_TOP,
            "speed": 600,
        }

    def _trigger_lightning(self, x: float, y: float):
        """Chain strikes from the trigger point through random bricks."""
        if not self.bricks:
            return
        targets = random.sample(self.bricks,
                                min(LIGHTNING_STRIKES, len(self.bricks)))
        damage = max(1, self.wave)
        points = [(x, y)]
        for b in targets:
            rect = cell_rect(b.col, b.row, b.shape, self._brick_off(b))
            points.append(rect.center)
            b.hp -= damage
        self.bricks = [b for b in self.bricks if b.hp > 0]
        self.lightning_bolts.append({
            "points": _jagged_path(points),
            "timer": LIGHTNING_BOLT_TTL,
        })

    def _trigger_skull(self, x: float, y: float):
        """Halve everything: brick HP and shields, but also gun ammo.

        Ammo halving applies to the TOTAL pool (available + reloading +
        in-flight) so dumping the magazine before the trigger doesn't
        dodge it. What can't be taken immediately becomes debt that eats
        shots as they return off the bottom.
        """
        for b in self.bricks:
            b.hp = max(1, b.hp // 2)
            b.shield //= 2
        in_flight = sum(1 for p in self.projectiles if p.alive)
        total = self.gun_ammo + self.gun_reloading + in_flight
        destroy = total - max(1, total // 2) if total > 1 else 0
        take = min(destroy, self.gun_ammo)
        self.gun_ammo -= take
        destroy -= take
        take = min(destroy, self.gun_reloading)
        self.gun_reloading -= take
        destroy -= take
        self.ammo_debt += destroy
        self.skull_wave = {
            "x": x, "y": y, "radius": 0,
            "max_radius": math.hypot(WIDTH, HEIGHT),
            "speed": 800,
        }

    def _collide_placed_aoe(self, proj: Projectile, placed: list[dict],
                            trigger):
        """Projectile hitting a placed AoE pickup activates it."""
        bx, by = proj.pos.x, proj.pos.y
        for item in list(placed):
            if math.hypot(bx - item["x"], by - item["y"]) < PROJECTILE_RADIUS + 10:
                placed.remove(item)
                trigger(item["x"], item["y"])

    def _check_placed_aoe_brick(self, placed: list[dict], trigger):
        """Placed freeze/reverse activates when any brick touches it."""
        for item in list(placed):
            for brick in self.bricks:
                brect = cell_rect_full(brick.col, brick.row, brick.shape,
                                       self._brick_off(brick))
                cx = max(brect.left, min(item["x"], brect.right))
                cy = max(brect.top, min(item["y"], brect.bottom))
                if math.hypot(cx - item["x"], cy - item["y"]) < 10:
                    placed.remove(item)
                    trigger(item["x"], item["y"])
                    break

    def _check_mines(self):
        """Placed mines (stationary) explode when any brick touches their edge."""
        mine_radius = 10  # matches visual radius
        for mine in list(self.placed_mines):
            mx, my = mine["x"], mine["y"]
            for brick in self.bricks:
                brect = cell_rect_full(brick.col, brick.row, brick.shape,
                                       self._brick_off(brick))
                # Closest point on brick rect to mine center
                cx = max(brect.left, min(mx, brect.right))
                cy = max(brect.top, min(my, brect.bottom))
                if math.hypot(cx - mx, cy - my) < mine_radius:
                    self.placed_mines.remove(mine)
                    self._explode(mx, my)
                    break

    def _explode(self, ex: float, ey: float):
        """Area damage around explosion point. Chains to other bombs."""
        damage = max(1, self.wave // 2)
        blast_px = BOMB_RADIUS_CELLS * CELL_SIZE
        off = self.brick_offset

        # Damage bricks
        to_remove: list[int] = []
        for i, brick in enumerate(self.bricks):
            rect = cell_rect(brick.col, brick.row, brick.shape,
                             self._brick_off(brick))
            cx, cy = rect.center
            if math.hypot(cx - ex, cy - ey) < blast_px:
                brick.hp -= damage
                if brick.hp <= 0:
                    to_remove.append(i)
        for i in reversed(to_remove):
            self.bricks.pop(i)

        # Chain to bomb pickups, collect ammo pickups caught in the blast
        chain: list[dict] = []
        collected: list[dict] = []
        for pu in self.pickups:
            rect = cell_rect(pu["col"], pu["row"], "square", off)
            cx, cy = rect.center
            d = math.hypot(cx - ex, cy - ey)
            if pu["type"] == "bomb" and 0 < d < blast_px:
                chain.append(pu)
            elif pu["type"] == "ammo" and d < blast_px:
                collected.append(pu)
                self.gun_ammo += AMMO_PER_PICKUP
        if collected:
            self.pickups = [p for p in self.pickups if p not in collected]
        for pu in chain:
            if pu in self.pickups:
                rect = cell_rect(pu["col"], pu["row"], "square", off)
                self.pickups.remove(pu)
                self._explode(rect.centerx, rect.centery)

        # Chain to placed mines in range
        for mine in list(self.placed_mines):
            d = math.hypot(mine["x"] - ex, mine["y"] - ey)
            if 0 < d < blast_px and mine in self.placed_mines:
                self.placed_mines.remove(mine)
                self._explode(mine["x"], mine["y"])

        self.explosions.append({"x": ex, "y": ey, "timer": 0.4})

    def _update_acids(self, dt: float):
        """Tick placed acid zones: damage bricks within radius each second."""
        acid_px = ACID_RADIUS_CELLS * CELL_SIZE
        for acid in self.placed_acids:
            acid["timer"] -= dt
            if acid["timer"] <= 0:
                continue
            acid["tick"] -= dt
            if acid["tick"] <= 0:
                acid["tick"] = ACID_TICK
                damage = max(1, self.wave // 10)
                to_remove: list[int] = []
                for i, brick in enumerate(self.bricks):
                    rect = cell_rect(brick.col, brick.row, brick.shape,
                                     self._brick_off(brick))
                    # Closest point on brick edge to acid center
                    cx = max(rect.left, min(acid["x"], rect.right))
                    cy = max(rect.top, min(acid["y"], rect.bottom))
                    if math.hypot(cx - acid["x"], cy - acid["y"]) < acid_px:
                        brick.hp -= damage
                        if brick.hp <= 0:
                            to_remove.append(i)
                for i in reversed(to_remove):
                    self.bricks.pop(i)
        self.placed_acids = [a for a in self.placed_acids if a["timer"] > 0]

    def _update_acid_tint(self, dt: float):
        """Mark bricks inside acid zones. Keep tint 2s after leaving."""
        acid_px = ACID_RADIUS_CELLS * CELL_SIZE
        for brick in self.bricks:
            brect = cell_rect(brick.col, brick.row, brick.shape,
                              self._brick_off(brick))
            in_acid = False
            for acid in self.placed_acids:
                cx = max(brect.left, min(acid["x"], brect.right))
                cy = max(brect.top, min(acid["y"], brect.bottom))
                if math.hypot(cx - acid["x"], cy - acid["y"]) < acid_px:
                    in_acid = True
                    break
            if in_acid:
                brick.acid_t = 2.0
            elif brick.acid_t > 0:
                brick.acid_t = max(0.0, brick.acid_t - dt)
