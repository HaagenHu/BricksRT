"""BricksRT — Real-time brick breaker with continuous advancement."""

import json
import math
import os
import random
import colorsys
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
PROJECTILE_SPEED = 10  # px per frame
GUN_COOLDOWN = 0.12  # seconds between shots
GUN_RELOAD_DELAY = 1.0  # seconds before returned ammo is available
STARTING_GUN_AMMO = 1
AMMO_PER_PICKUP = 1

ADVANCE_SPEED_BASE = 6.0   # px/sec at start
ADVANCE_SPEED_MAX = 25.0   # cap

BOMB_RADIUS_CELLS = 1.5
MINE_COLOR = (255, 50, 50)

# Unlock thresholds (wave number)
ACID_RADIUS_CELLS = 1.5
ACID_DURATION = 5.0   # seconds
ACID_TICK = 1.0       # seconds between ticks

FREEZE_DURATION = 5.0  # seconds
FREEZE_COLOR = (150, 230, 255)

REVERSE_DURATION = 3.0  # seconds
REVERSE_COLOR = (255, 80, 80)

FIREBALL_CHARGES = 5    # shots as fireball per pickup
HOMING_CHARGES = 5      # shots as homing per pickup
FIREBALL_COLOR = (255, 100, 0)
HOMING_COLOR = (0, 255, 150)

UNLOCK = {
    "mines": 3, "wall": 3, "bombs": 5, "fireball": 7, "acid": 8,
    "freeze": 10, "reverse": 10, "homing": 11,
    "round": 15, "diamond": 15,
    "hexagon": 30, "trapezoid": 30, "wide": 30,
    "triangle": 50, "shields": 60, "merging": 70,
}

# Colors
BG_COLOR = (20, 20, 30)
TEXT_COLOR = (255, 255, 255)
CROSSHAIR_COLOR = (200, 200, 200)
COLLECTIBLE_COLOR = (100, 255, 130)
BOMB_COLOR = (255, 80, 50)
AMMO_COLOR = (220, 200, 100)
SHIELD_COLOR = (0, 220, 255)
MORTAR_BOMB_COLOR = (255, 80, 50)
MORTAR_ACID_COLOR = (120, 255, 0)
MORTAR_WALL_COLOR = (255, 160, 40)
GAMEOVER_OVERLAY = (0, 0, 0, 180)
HUD_BG = (30, 30, 45)


def brick_color(hp: int) -> tuple[int, int, int]:
    """Map HP to rainbow gradient. Low HP = green, high HP = red/violet."""
    t = min(1.0, math.log(1 + hp) / math.log(1 + 100))
    hue = 0.33 - t * 0.5
    if hue < 0:
        hue += 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.95)
    return (int(r * 255), int(g * 255), int(b * 255))


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
# Projectile
# ---------------------------------------------------------------------------

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

    def update(self):
        if not self.alive:
            return
        self.pos += self.vel

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


def _apply_gravity(proj: Projectile):
    """Nudge projectile toward straight down (prevents infinite bouncing)."""
    current = math.atan2(proj.vel.y, proj.vel.x)
    target = math.pi / 2
    diff = target - current
    while diff > math.pi:
        diff -= 2 * math.pi
    while diff < -math.pi:
        diff += 2 * math.pi
    pull = max(-math.radians(0.1), min(math.radians(0.1), diff))
    new_angle = current + pull
    speed = proj.vel.length()
    proj.vel.x = math.cos(new_angle) * speed
    proj.vel.y = math.sin(new_angle) * speed


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

        # Bricks
        self.bricks: list[dict] = []
        self.brick_offset = 0.0  # sub-cell scroll offset in pixels

        # Gun
        self.gun_x = WIDTH / 2  # gun position, drifts toward exit points
        self.gun_ammo = STARTING_GUN_AMMO
        self.gun_cooldown = 0.0
        self.gun_reloading = 0  # ammo pending reload
        self.gun_reload_timer = 0.0
        self.projectiles: list[Projectile] = []

        # Mortar ammo — list of type strings in pickup order
        self.mortar_ammo: list[str] = []

        # Gun ammo modifiers
        self.fireball_charges = 0  # next N shots are fireballs
        self.homing_charges = 0    # next N shots are homing

        # Field items (advance with bricks, on row 0)
        self.collectibles: list[dict] = []  # {col, row} — gives gun ammo

        # Stationary PU pickups on field (pixel coords, any free cell, ball hit to collect)
        self.bombs: list[dict] = []         # {col, row} — bomb PU, collect as mortar
        self.mines: list[dict] = []         # {col, row} — mine PU, collect as mortar
        self.acid_pus: list[dict] = []      # {col, row} — acid PU, collect as mortar
        self.wall_pus: list[dict] = []      # {col, row} — wall PU, collect as mortar
        self.fireballs: list[dict] = []     # {col, row} — fireball PU, gives charges
        self.homings: list[dict] = []       # {col, row} — homing PU, gives duration

        # Placed items from mortar fire (stationary)
        self.placed_mines: list[dict] = []  # {x, y} — explode when brick touches
        self.placed_acids: list[dict] = []  # {x, y, timer, tick} — area DoT
        self.placed_walls: list[dict] = []  # {y, hp} — horizontal barrier

        # Stationary AoE/gun PUs (pixel coords, ball hit to trigger/collect)
        self.placed_freezes: list[dict] = []   # {x, y}
        self.placed_reverses: list[dict] = []  # {x, y}

        # Aim
        self.aim_angle: float = -math.pi / 2
        self.crosshair: tuple[int, int] = (WIDTH // 2, HEIGHT // 2)

        # Visual effects
        self.explosions: list[dict] = []
        # Mortar shells in flight: {x, y, tx, ty, type, t, duration}
        self.mortar_shells: list[dict] = []
        self.freeze_timer = 0.0  # seconds remaining of freeze
        self.freeze_wave: dict | None = None  # {x, y, radius, max_radius, speed}
        self.reverse_timer = 0.0  # seconds remaining of reverse
        self.reverse_wave: dict | None = None  # {x, y, height, max_height, speed}

        # Advance speed
        self.advance_speed = ADVANCE_SPEED_BASE

    def start(self):
        self.reset()
        self.phase = "playing"
        self.gun_cooldown = 0.5  # aim delay before first shot
        self.spawn_wave()

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

        # Gun cooldown
        if self.gun_cooldown > 0:
            self.gun_cooldown -= dt

        # Update projectiles
        for p in self.projectiles:
            if not p.alive:
                continue
            p.update()
            # Homing steering toward nearest brick
            if p.homing and p.alive and self.bricks:
                p.homing_timer -= 1.0 / FPS
                if p.homing_timer <= 0:
                    p.homing = False
                else:
                    best_dist = float('inf')
                    best_tx, best_ty = p.pos.x, p.pos.y - 100
                    for brick in self.bricks:
                        off = self._brick_off(brick)
                        shape = brick.get("shape", "square")
                        rect = cell_rect(brick["col"], brick["row"], shape, off)
                        cx, cy = rect.center
                        d = math.hypot(cx - p.pos.x, cy - p.pos.y)
                        if d < best_dist:
                            best_dist = d
                            best_tx, best_ty = cx, cy
                    target_angle = math.atan2(best_ty - p.pos.y,
                                              best_tx - p.pos.x)
                    current_angle = math.atan2(p.vel.y, p.vel.x)
                    diff = target_angle - current_angle
                    while diff > math.pi:
                        diff -= 2 * math.pi
                    while diff < -math.pi:
                        diff += 2 * math.pi
                    max_steer = math.radians(2)
                    steer = max(-max_steer, min(max_steer, diff))
                    new_angle = current_angle + steer
                    speed = p.vel.length()
                    p.vel.x = math.cos(new_angle) * speed
                    p.vel.y = math.sin(new_angle) * speed
            if p.border_hits >= 10:
                _apply_gravity(p)
            if p.alive:
                self._collide_bricks(p)
            if p.alive:
                self._collide_collectibles(p)
            if p.alive:
                self._collide_bombs(p)
            if p.alive:
                self._collide_mines(p)
            if p.alive:
                self._collide_acid_pus(p)
            if p.alive:
                self._collide_wall_pus(p)
            if p.alive:
                self._collide_walls(p)
            if p.alive:
                self._collide_fireballs_pu(p)
            if p.alive:
                self._collide_homings_pu(p)
            if p.alive:
                self._collide_placed_freezes(p)
            if p.alive:
                self._collide_placed_reverses(p)

        # Return ammo for projectiles that exited bottom (into reload queue)
        for p in self.projectiles:
            if not p.alive and p.exited_bottom:
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

        # Freeze/reverse: also trigger on brick contact
        self._check_placed_freezes_brick()
        self._check_placed_reverses_brick()

        # Acid zones: tick damage on nearby bricks
        self._update_acids(dt)

        # Mark bricks touched by acid, decay timer when outside
        self._update_acid_tint(dt)

        # Walls: grace countdown, then break when weight >= max_weight
        self._wall_weight = sum(b["hp"] for b in self.bricks
                                if b.get("held", 0) > 0) if self.placed_walls else 0
        dead_walls: list[dict] = []
        for w in self.placed_walls:
            if w.get("grace", 0) > 0:
                w["grace"] -= dt
                continue
            w["ttl"] -= dt
            if w["ttl"] <= 0 or self._wall_weight >= w["max_weight"]:
                dead_walls.append(w)
        if dead_walls:
            for w in dead_walls:
                self.placed_walls.remove(w)
            for b in self.bricks:
                if "held" in b:
                    del b["held"]

        # Update mortar shells in flight
        landed: list[dict] = []
        for shell in self.mortar_shells:
            shell["t"] += dt / shell["duration"]
            if shell["t"] >= 1.0:
                landed.append(shell)
        for shell in landed:
            self.mortar_shells.remove(shell)
            self._land_mortar(shell)

        # Decay visual effects
        self.explosions = [e for e in self.explosions if e["timer"] > 0]
        for e in self.explosions:
            e["timer"] -= dt

    def _brick_off(self, brick: dict) -> float:
        """Effective y offset for a brick (accounts for wall hold-back)."""
        return self.brick_offset - brick.get("held", 0.0)

    def _update_wall_blocking(self):
        """Pin bricks at walls, and stack bricks on top of stopped bricks."""
        # Reset all held values — recalculate from scratch each frame
        for brick in self.bricks:
            if "held" in brick:
                del brick["held"]

        # First pass: pin bricks directly at walls
        for brick in self.bricks:
            shape = brick.get("shape", "square")
            extra = CELL_SIZE if shape == "tall" else 0
            bottom = (GRID_TOP + (brick["row"] + 1) * CELL_SIZE
                      + extra + self.brick_offset)
            for w in self.placed_walls:
                if bottom > w["y"]:
                    overshoot = bottom - w["y"]
                    brick["held"] = overshoot
                    break

        # Second pass: process bottom-to-top so bricks stack on stopped bricks.
        # Sort by effective bottom position (highest row = furthest down = first).
        sorted_bricks = sorted(self.bricks,
                               key=lambda b: -(b["row"] * CELL_SIZE
                                               + self._brick_off(b)))
        # Build occupied map: for each column, track the topmost blocked pixel
        # (i.e. the top edge of the highest stopped brick per column)
        col_barrier: dict[int, float] = {}  # col -> min top pixel of stopped bricks

        for brick in sorted_bricks:
            shape = brick.get("shape", "square")
            extra = CELL_SIZE if shape == "tall" else 0
            held = brick.get("held", 0.0)
            eff_offset = self.brick_offset - held
            top = GRID_TOP + brick["row"] * CELL_SIZE + eff_offset
            bottom = top + CELL_SIZE + extra

            cols = [brick["col"]]
            if shape == "wide":
                cols.append(brick["col"] + 1)

            # Check if this brick is blocked (has held > 0)
            if held > 0:
                for c in cols:
                    if c not in col_barrier or top < col_barrier[c]:
                        col_barrier[c] = top
            else:
                # Check if any column has a barrier below this brick
                for c in cols:
                    if c in col_barrier and bottom > col_barrier[c]:
                        overshoot = bottom - col_barrier[c]
                        brick["held"] = brick.get("held", 0.0) + overshoot
                        # Recalculate top with new held
                        eff_offset = self.brick_offset - brick["held"]
                        top = GRID_TOP + brick["row"] * CELL_SIZE + eff_offset
                        for c2 in cols:
                            if c2 not in col_barrier or top < col_barrier[c2]:
                                col_barrier[c2] = top
                        break

    def _check_game_over(self) -> bool:
        for b in self.bricks:
            shape = b.get("shape", "square")
            extra = CELL_SIZE if shape == "tall" else 0
            pixel_bottom = (GRID_TOP + (b["row"] + 1) * CELL_SIZE
                            + extra + self._brick_off(b))
            if pixel_bottom >= GRID_BOTTOM:
                self.phase = "gameover"
                if self.wave > self.highscore:
                    self.highscore = self.wave
                    save_highscore("realtime", self.wave)
                return True
        return False

    def _advance_rows(self):
        """All items shift down one grid row. Spawn new wave at top."""
        # Build set of cells occupied by held bricks (they don't move)
        held_cells = set()
        for b in self.bricks:
            if b.get("held", 0) > 0:
                held_cells.add((b["col"], b["row"]))
                if b.get("shape") == "wide":
                    held_cells.add((b["col"] + 1, b["row"]))
                if b.get("shape") == "tall":
                    held_cells.add((b["col"], b["row"] + 1))

        # Process bottom-to-top so lower bricks block upper ones
        for b in sorted(self.bricks, key=lambda x: -x["row"]):
            held = b.get("held", 0.0)
            if held >= CELL_SIZE:
                b["held"] = held - CELL_SIZE
                continue
            # Check if target cells are free
            shape = b.get("shape", "square")
            new_row = b["row"] + 1
            target_cells = [(b["col"], new_row)]
            if shape == "wide":
                target_cells.append((b["col"] + 1, new_row))
            if shape == "tall":
                target_cells.append((b["col"], new_row + 1))
            blocked = any(cell in held_cells for cell in target_cells)
            if blocked:
                # This brick can't advance — mark as held for 1 cell
                b["held"] = b.get("held", 0.0) + CELL_SIZE
                # Add this brick's cells to held set so bricks above stop too
                held_cells.add((b["col"], b["row"]))
                if shape == "wide":
                    held_cells.add((b["col"] + 1, b["row"]))
                if shape == "tall":
                    held_cells.add((b["col"], b["row"] + 1))
            else:
                b["row"] = new_row
        for c in self.collectibles:
            c["row"] += 1
        for b in self.bombs:
            b["row"] += 1
        for m in self.mines:
            m["row"] += 1
        for a in self.acid_pus:
            a["row"] += 1
        for w in self.wall_pus:
            w["row"] += 1
        for f in self.fireballs:
            f["row"] += 1
        for h in self.homings:
            h["row"] += 1

        # Remove items scrolled past bottom
        self.bricks = [b for b in self.bricks if b["row"] <= MAX_ROWS]
        self.collectibles = [c for c in self.collectibles if c["row"] <= MAX_ROWS]
        self.bombs = [b for b in self.bombs if b["row"] <= MAX_ROWS]
        self.mines = [m for m in self.mines if m["row"] <= MAX_ROWS]
        self.acid_pus = [a for a in self.acid_pus if a["row"] <= MAX_ROWS]
        self.wall_pus = [w for w in self.wall_pus if w["row"] <= MAX_ROWS]
        self.fireballs = [f for f in self.fireballs if f["row"] <= MAX_ROWS]
        self.homings = [h for h in self.homings if h["row"] <= MAX_ROWS]

        # Check game over after advancing
        if self._check_game_over():
            return

        self.spawn_wave()

    def _retreat_rows(self):
        """All items shift up one grid row. Remove bricks pushed off top."""
        for b in self.bricks:
            b["row"] -= 1
        for c in self.collectibles:
            c["row"] -= 1
        for b in self.bombs:
            b["row"] -= 1
        for m in self.mines:
            m["row"] -= 1
        for a in self.acid_pus:
            a["row"] -= 1
        for w in self.wall_pus:
            w["row"] -= 1
        for f in self.fireballs:
            f["row"] -= 1
        for h in self.homings:
            h["row"] -= 1

        # Remove items pushed past top
        self.bricks = [b for b in self.bricks if b["row"] >= -1]
        self.collectibles = [c for c in self.collectibles if c["row"] >= -1]
        self.bombs = [b for b in self.bombs if b["row"] >= -1]
        self.mines = [m for m in self.mines if m["row"] >= -1]
        self.acid_pus = [a for a in self.acid_pus if a["row"] >= -1]
        self.wall_pus = [w for w in self.wall_pus if w["row"] >= -1]
        self.fireballs = [f for f in self.fireballs if f["row"] >= -1]
        self.homings = [h for h in self.homings if h["row"] >= -1]

    # ------------------------------------------------------------------
    # Wave spawning
    # ------------------------------------------------------------------

    def _distribute_blocked_hp(self, blocked_hp: dict[int, int]):
        """Distribute HP from blocked columns across connected held containers."""
        # Build held cell grid: (col, row) -> brick
        held_cells: dict[tuple[int, int], dict] = {}
        for b in self.bricks:
            if b.get("held", 0) > 0:
                cells = [(b["col"], b["row"])]
                if b.get("shape") == "wide":
                    cells.append((b["col"] + 1, b["row"]))
                if b.get("shape") == "tall":
                    cells.append((b["col"], b["row"] + 1))
                for cell in cells:
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
                held_cells[cell]["hp"] += hp_each + (1 if i < hp_rem else 0)

    def _free_cells(self) -> list[tuple[int, int]]:
        """Return grid cells not occupied. Excludes first and last row."""
        occupied = set()
        for b in self.bricks:
            occupied.add((b["col"], b["row"]))
            if b.get("shape") == "wide":
                occupied.add((b["col"] + 1, b["row"]))
        for items in (self.collectibles, self.bombs, self.mines,
                      self.acid_pus, self.wall_pus,
                      self.fireballs, self.homings):
            for item in items:
                occupied.add((item["col"], item["row"]))
        # Convert pixel-based placed items to grid cells
        off = self.brick_offset
        for p in self.placed_freezes + self.placed_reverses:
            col = int(p["x"] // CELL_SIZE)
            row = int((p["y"] - GRID_TOP - off) // CELL_SIZE)
            occupied.add((col, row))
        return [(c, r) for r in range(1, MAX_ROWS - 1)
                for c in range(COLS)
                if (c, r) not in occupied]

    def spawn_wave(self):
        self.wave += 1

        # Build map of bricks per column, detect full columns
        bricks_by_col: dict[int, list[dict]] = {}
        rows_by_col: dict[int, set[int]] = {}
        for b in self.bricks:
            cols_b = [b["col"]]
            if b.get("shape") == "wide":
                cols_b.append(b["col"] + 1)
            for cb in cols_b:
                bricks_by_col.setdefault(cb, []).append(b)
                rows_by_col.setdefault(cb, set()).add(b["row"])
        # Find lowest wall row per column (approximate from pixel y)
        wall_row_limit = MAX_ROWS  # default: no wall
        if self.placed_walls:
            # Use the highest wall (lowest y) to determine the blocked row
            min_wy = min(w["y"] for w in self.placed_walls)
            wall_row_limit = max(0, int((min_wy - GRID_TOP) // CELL_SIZE))
        # A column is full if every row from 0 down to the lowest held
        # brick (or wall) in that column is occupied.
        # Find the lowest occupied row per column (the "floor")
        held_floor: dict[int, int] = {}  # col -> lowest held row
        for b in self.bricks:
            if b.get("held", 0) > 0:
                cols_b = [b["col"]]
                if b.get("shape") == "wide":
                    cols_b.append(b["col"] + 1)
                for cb in cols_b:
                    r = b["row"]
                    if cb not in held_floor or r > held_floor[cb]:
                        held_floor[cb] = r
        full_cols = set()
        for c in held_floor:
            floor = held_floor[c]
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
            if b["row"] == 0:
                row0_occupied.add(b["col"])
                if b.get("shape") == "wide":
                    row0_occupied.add(b["col"] + 1)
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
                    and c + 1 not in full_cols):
                shape = "wide"
                occupied.add(c + 1)
                if c + 1 in remaining:
                    remaining.remove(c + 1)

            occupied.add(c)
            if shape == "wide":
                hp *= 2
            brick = {"col": c, "row": 0, "hp": hp, "shape": shape}
            if shape == "triangle":
                brick["tri_dir"] = random.choice(["up", "down", "left", "right"])
            if self.wave >= UNLOCK["shields"] and random.random() < 0.15:
                brick["shield"] = max(2, self.wave // 5)
            self.bricks.append(brick)

        # Spawn ammo collectible (row 0 only, not during reverse, skip every 5th wave)
        if remaining and self.reverse_timer <= 0 and self.wave % 5 != 0:
            cc = random.choice(remaining)
            self.collectibles.append({"col": cc, "row": 0})

        # Helper: spawn grid-based PU on a free cell (not first or last row)
        def _spawn_grid(unlock_key, chance, target_list):
            if self.wave >= UNLOCK[unlock_key] and random.random() < chance:
                free = self._free_cells()
                if free:
                    c, r = random.choice(free)
                    target_list.append({"col": c, "row": r})

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
        _spawn_grid("mines", 0.30, self.mines)
        _spawn_grid("bombs", 0.25, self.bombs)
        _spawn_grid("acid", 0.20, self.acid_pus)
        _spawn_grid("wall", 0.15, self.wall_pus)

        # Gun PUs (grid-based, advance with bricks, ball hit to activate)
        _spawn_grid("fireball", 0.15, self.fireballs)
        _spawn_grid("homing", 0.12, self.homings)

        # AoE PUs (pixel-based, stationary, ball hit to activate)
        _spawn_pixel("freeze", 0.12, self.placed_freezes)
        _spawn_pixel("reverse", 0.10, self.placed_reverses)

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

    def fire_mortar(self) -> bool:
        """Launch a mortar shell toward the crosshair position."""
        if not self.mortar_ammo:
            return False
        mtype = self.mortar_ammo.pop(0)
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
                shape = brick.get("shape", "square")
                rect = cell_rect_full(brick["col"], brick["row"], shape, off)
                expanded = rect.inflate(PROJECTILE_RADIUS * 2,
                                        PROJECTILE_RADIUS * 2)
                if expanded.collidepoint(bx, by):
                    brick["hp"] -= 1
                    proj.border_hits = 0
                    if brick["hp"] <= 0:
                        to_remove.append(i)
        else:
            # Normal/homing: bounce off first brick hit
            for i, brick in enumerate(self.bricks):
                off = self._brick_off(brick)
                shape = brick.get("shape", "square")
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
                    shield = brick.get("shield", 0)
                    if shield > 0:
                        rect_c = cell_rect_full(brick["col"], brick["row"],
                                                shape, off)
                        if shape in ("round", "diamond", "triangle"):
                            from_below = (pre_vel_y < 0
                                          and pre_pos_y > rect_c.centery)
                        else:
                            from_below = (pre_vel_y < 0
                                          and pre_pos_y > rect_c.centery
                                          and rect_c.left <= pre_pos_x <= rect_c.right)
                        if from_below:
                            brick["shield"] -= 1
                            if brick["shield"] <= 0:
                                del brick["shield"]
                        else:
                            brick["hp"] -= 1
                    else:
                        brick["hp"] -= 1

                    proj.border_hits = 0
                    if brick["hp"] <= 0:
                        to_remove.append(i)
                    break

        for i in reversed(to_remove):
            self.bricks.pop(i)

    def _collide_rect(self, proj: Projectile, brick: dict,
                      y_offset: float = 0) -> bool:
        bx, by = proj.pos.x, proj.pos.y
        shape = brick.get("shape", "square")
        rect = cell_rect_full(brick["col"], brick["row"], shape, y_offset)
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

    def _collide_round(self, proj: Projectile, brick: dict,
                       y_offset: float = 0) -> bool:
        bx, by = proj.pos.x, proj.pos.y
        rect = cell_rect(brick["col"], brick["row"], "square", y_offset)
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

    def _collide_diamond(self, proj: Projectile, brick: dict,
                         y_offset: float = 0) -> bool:
        bx, by = proj.pos.x, proj.pos.y
        rect = cell_rect(brick["col"], brick["row"], "square", y_offset)
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

    def _collide_hexagon(self, proj: Projectile, brick: dict,
                         y_offset: float = 0) -> bool:
        rect = cell_rect(brick["col"], brick["row"], "square", y_offset)
        cx, cy = rect.center
        r = BRICK_SIZE / 2
        verts = [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
                  cy + r * math.sin(math.pi / 6 + i * math.pi / 3))
                 for i in range(6)]
        return self._collide_polygon(proj, verts, cx, cy)

    def _collide_trapezoid(self, proj: Projectile, brick: dict,
                           y_offset: float = 0) -> bool:
        rect = cell_rect(brick["col"], brick["row"], "square", y_offset)
        cx, cy = rect.center
        hw, hh = BRICK_SIZE / 2, BRICK_SIZE / 2
        tw = hw * 0.6
        verts = [(cx - tw, cy - hh), (cx + tw, cy - hh),
                 (cx + hw, cy + hh), (cx - hw, cy + hh)]
        return self._collide_polygon(proj, verts, cx, cy)

    def _tri_verts(self, brick: dict, y_offset: float = 0):
        rect = cell_rect(brick["col"], brick["row"], "square", y_offset)
        cx, cy = rect.center
        h = BRICK_SIZE / 2
        d = brick.get("tri_dir", "up")
        if d == "up":
            return [(cx, cy - h), (cx + h, cy + h), (cx - h, cy + h)], cx, cy
        elif d == "down":
            return [(cx - h, cy - h), (cx + h, cy - h), (cx, cy + h)], cx, cy
        elif d == "left":
            return [(cx - h, cy), (cx + h, cy - h), (cx + h, cy + h)], cx, cy
        else:
            return [(cx - h, cy - h), (cx - h, cy + h), (cx + h, cy)], cx, cy

    def _collide_triangle(self, proj: Projectile, brick: dict,
                          y_offset: float = 0) -> bool:
        verts, cx, cy = self._tri_verts(brick, y_offset)
        return self._collide_polygon(proj, verts, cx, cy)

    # ------------------------------------------------------------------
    # Collectible / bomb collisions
    # ------------------------------------------------------------------

    def _collide_collectibles(self, proj: Projectile):
        bx, by = proj.pos.x, proj.pos.y
        off = self.brick_offset
        to_remove: list[int] = []
        for i, col in enumerate(self.collectibles):
            rect = cell_rect(col["col"], col["row"], "square", off)
            cx, cy = rect.center
            if math.hypot(bx - cx, by - cy) < PROJECTILE_RADIUS + BRICK_SIZE * 0.25:
                to_remove.append(i)
                self.gun_ammo += AMMO_PER_PICKUP
        for i in reversed(to_remove):
            self.collectibles.pop(i)

    def _collide_bombs(self, proj: Projectile):
        """Bomb pickups are collected as mortar ammo, not detonated."""
        bx, by = proj.pos.x, proj.pos.y
        off = self.brick_offset
        to_remove: list[dict] = []
        for bomb in self.bombs:
            rect = cell_rect(bomb["col"], bomb["row"], "square", off)
            cx, cy = rect.center
            if math.hypot(bx - cx, by - cy) < PROJECTILE_RADIUS + BRICK_SIZE * 0.25:
                to_remove.append(bomb)
                self.mortar_ammo.append("bomb")
        for bomb in to_remove:
            if bomb in self.bombs:
                self.bombs.remove(bomb)

    def _collide_mines(self, proj: Projectile):
        """Mine pickups on field are collected as mortar ammo when shot."""
        bx, by = proj.pos.x, proj.pos.y
        off = self.brick_offset
        to_remove: list[dict] = []
        for mine in self.mines:
            rect = cell_rect(mine["col"], mine["row"], "square", off)
            cx, cy = rect.center
            if math.hypot(bx - cx, by - cy) < PROJECTILE_RADIUS + BRICK_SIZE * 0.25:
                to_remove.append(mine)
                self.mortar_ammo.append("mine")
        for mine in to_remove:
            if mine in self.mines:
                self.mines.remove(mine)

    def _collide_acid_pus(self, proj: Projectile):
        """Acid pickups on field are collected as mortar ammo when shot."""
        bx, by = proj.pos.x, proj.pos.y
        off = self.brick_offset
        to_remove: list[dict] = []
        for acid in self.acid_pus:
            rect = cell_rect(acid["col"], acid["row"], "square", off)
            cx, cy = rect.center
            if math.hypot(bx - cx, by - cy) < PROJECTILE_RADIUS + BRICK_SIZE * 0.25:
                to_remove.append(acid)
                self.mortar_ammo.append("acid")
        for acid in to_remove:
            if acid in self.acid_pus:
                self.acid_pus.remove(acid)

    def _collide_wall_pus(self, proj: Projectile):
        """Wall pickups on field are collected as mortar ammo when shot."""
        bx, by = proj.pos.x, proj.pos.y
        off = self.brick_offset
        to_remove: list[dict] = []
        for wall in self.wall_pus:
            rect = cell_rect(wall["col"], wall["row"], "square", off)
            cx, cy = rect.center
            if math.hypot(bx - cx, by - cy) < PROJECTILE_RADIUS + BRICK_SIZE * 0.25:
                to_remove.append(wall)
                self.mortar_ammo.append("wall")
        for wall in to_remove:
            if wall in self.wall_pus:
                self.wall_pus.remove(wall)

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
                w["max_weight"] = max(0, w["max_weight"] - 1)
                break

    def _collide_fireballs_pu(self, proj: Projectile):
        """Fireball PU: gives fireball charges to gun."""
        bx, by = proj.pos.x, proj.pos.y
        off = self.brick_offset
        to_remove: list[dict] = []
        for fb in self.fireballs:
            rect = cell_rect(fb["col"], fb["row"], "square", off)
            cx, cy = rect.center
            if math.hypot(bx - cx, by - cy) < PROJECTILE_RADIUS + BRICK_SIZE * 0.25:
                to_remove.append(fb)
                self.fireball_charges += FIREBALL_CHARGES
        for fb in to_remove:
            if fb in self.fireballs:
                self.fireballs.remove(fb)

    def _collide_homings_pu(self, proj: Projectile):
        """Homing PU: gives homing duration to gun."""
        bx, by = proj.pos.x, proj.pos.y
        off = self.brick_offset
        to_remove: list[dict] = []
        for hm in self.homings:
            rect = cell_rect(hm["col"], hm["row"], "square", off)
            cx, cy = rect.center
            if math.hypot(bx - cx, by - cy) < PROJECTILE_RADIUS + BRICK_SIZE * 0.25:
                to_remove.append(hm)
                self.homing_charges += HOMING_CHARGES
        for hm in to_remove:
            if hm in self.homings:
                self.homings.remove(hm)

    def _collide_placed_freezes(self, proj: Projectile):
        """Projectile hitting a freeze activates it."""
        bx, by = proj.pos.x, proj.pos.y
        to_remove: list[dict] = []
        for fz in self.placed_freezes:
            if math.hypot(bx - fz["x"], by - fz["y"]) < PROJECTILE_RADIUS + 10:
                to_remove.append(fz)
                self.freeze_timer = FREEZE_DURATION
                self.freeze_wave = {
                    "x": fz["x"], "y": fz["y"], "radius": 0,
                    "max_radius": math.hypot(WIDTH, HEIGHT),
                    "speed": 800,
                }
        for fz in to_remove:
            if fz in self.placed_freezes:
                self.placed_freezes.remove(fz)

    def _collide_placed_reverses(self, proj: Projectile):
        """Projectile hitting a reverse activates it."""
        bx, by = proj.pos.x, proj.pos.y
        to_remove: list[dict] = []
        for rv in self.placed_reverses:
            if math.hypot(bx - rv["x"], by - rv["y"]) < PROJECTILE_RADIUS + 10:
                to_remove.append(rv)
                self.reverse_timer = REVERSE_DURATION
                self.reverse_wave = {
                    "x": rv["x"], "y": rv["y"],
                    "height": 0, "max_height": GRID_BOTTOM - GRID_TOP,
                    "speed": 600,
                }
        for rv in to_remove:
            if rv in self.placed_reverses:
                self.placed_reverses.remove(rv)

    def _check_placed_freezes_brick(self):
        """Freeze activates when any brick touches it."""
        triggered: list[dict] = []
        for fz in self.placed_freezes:
            for brick in self.bricks:
                shape = brick.get("shape", "square")
                brect = cell_rect_full(brick["col"], brick["row"], shape,
                                       self._brick_off(brick))
                cx = max(brect.left, min(fz["x"], brect.right))
                cy = max(brect.top, min(fz["y"], brect.bottom))
                if math.hypot(cx - fz["x"], cy - fz["y"]) < 10:
                    triggered.append(fz)
                    break
        for fz in triggered:
            if fz in self.placed_freezes:
                self.placed_freezes.remove(fz)
                self.freeze_timer = FREEZE_DURATION
                self.freeze_wave = {
                    "x": fz["x"], "y": fz["y"], "radius": 0,
                    "max_radius": math.hypot(WIDTH, HEIGHT),
                    "speed": 800,
                }

    def _check_placed_reverses_brick(self):
        """Reverse activates when any brick touches it."""
        triggered: list[dict] = []
        for rv in self.placed_reverses:
            for brick in self.bricks:
                shape = brick.get("shape", "square")
                brect = cell_rect_full(brick["col"], brick["row"], shape,
                                       self._brick_off(brick))
                cx = max(brect.left, min(rv["x"], brect.right))
                cy = max(brect.top, min(rv["y"], brect.bottom))
                if math.hypot(cx - rv["x"], cy - rv["y"]) < 10:
                    triggered.append(rv)
                    break
        for rv in triggered:
            if rv in self.placed_reverses:
                self.placed_reverses.remove(rv)
                self.reverse_timer = REVERSE_DURATION
                self.reverse_wave = {
                    "x": rv["x"], "y": rv["y"],
                    "height": 0, "max_height": GRID_BOTTOM - GRID_TOP,
                    "speed": 600,
                }

    def _check_mines(self):
        """Placed mines (stationary) explode when any brick touches their edge."""
        mine_radius = 10  # matches visual radius
        triggered: list[dict] = []
        for mine in self.placed_mines:
            mx, my = mine["x"], mine["y"]
            for brick in self.bricks:
                shape = brick.get("shape", "square")
                brect = cell_rect_full(brick["col"], brick["row"], shape,
                                       self._brick_off(brick))
                # Closest point on brick rect to mine center
                cx = max(brect.left, min(mx, brect.right))
                cy = max(brect.top, min(my, brect.bottom))
                if math.hypot(cx - mx, cy - my) < mine_radius:
                    triggered.append(mine)
                    break
        for mine in triggered:
            if mine in self.placed_mines:
                self.placed_mines.remove(mine)
                self._explode(mine["x"], mine["y"])

    def _explode(self, ex: float, ey: float):
        """Area damage around explosion point. Chains to other bombs."""
        damage = max(1, self.wave // 2)
        blast_px = BOMB_RADIUS_CELLS * CELL_SIZE
        off = self.brick_offset

        # Damage bricks
        to_remove: list[int] = []
        for i, brick in enumerate(self.bricks):
            shape = brick.get("shape", "square")
            rect = cell_rect(brick["col"], brick["row"], shape,
                             self._brick_off(brick))
            cx, cy = rect.center
            if math.hypot(cx - ex, cy - ey) < blast_px:
                brick["hp"] -= damage
                if brick["hp"] <= 0:
                    to_remove.append(i)
        for i in reversed(to_remove):
            self.bricks.pop(i)

        # Chain to other bombs
        chain: list[dict] = []
        for bomb in self.bombs:
            rect = cell_rect(bomb["col"], bomb["row"], "square", off)
            cx, cy = rect.center
            d = math.hypot(cx - ex, cy - ey)
            if 0 < d < blast_px:
                chain.append(bomb)
        for bomb in chain:
            if bomb in self.bombs:
                rect = cell_rect(bomb["col"], bomb["row"], "square", off)
                self.bombs.remove(bomb)
                self._explode(rect.centerx, rect.centery)

        # Chain to placed mines in range
        mine_chain: list[dict] = []
        for mine in self.placed_mines:
            d = math.hypot(mine["x"] - ex, mine["y"] - ey)
            if 0 < d < blast_px:
                mine_chain.append(mine)
        for mine in mine_chain:
            if mine in self.placed_mines:
                self.placed_mines.remove(mine)
                self._explode(mine["x"], mine["y"])

        # Collect nearby collectibles
        col_hit: list[dict] = []
        for col in self.collectibles:
            rect = cell_rect(col["col"], col["row"], "square", off)
            cx, cy = rect.center
            if math.hypot(cx - ex, cy - ey) < blast_px:
                col_hit.append(col)
                self.gun_ammo += AMMO_PER_PICKUP
        for col in col_hit:
            if col in self.collectibles:
                self.collectibles.remove(col)

        self.explosions.append({"x": ex, "y": ey, "timer": 0.4})

    def _update_acids(self, dt: float):
        """Tick placed acid zones: damage bricks within radius each second."""
        acid_px = ACID_RADIUS_CELLS * CELL_SIZE
        expired: list[dict] = []
        for acid in self.placed_acids:
            acid["timer"] -= dt
            if acid["timer"] <= 0:
                expired.append(acid)
                continue
            acid["tick"] -= dt
            if acid["tick"] <= 0:
                acid["tick"] = ACID_TICK
                damage = max(1, self.wave // 10)
                to_remove: list[int] = []
                for i, brick in enumerate(self.bricks):
                    shape = brick.get("shape", "square")
                    rect = cell_rect(brick["col"], brick["row"], shape,
                                     self._brick_off(brick))
                    # Closest point on brick edge to acid center
                    cx = max(rect.left, min(acid["x"], rect.right))
                    cy = max(rect.top, min(acid["y"], rect.bottom))
                    if math.hypot(cx - acid["x"], cy - acid["y"]) < acid_px:
                        brick["hp"] -= damage
                        if brick["hp"] <= 0:
                            to_remove.append(i)
                for i in reversed(to_remove):
                    self.bricks.pop(i)
        for acid in expired:
            self.placed_acids.remove(acid)

    def _update_acid_tint(self, dt: float):
        """Mark bricks inside acid zones. Keep tint 2s after leaving."""
        acid_px = ACID_RADIUS_CELLS * CELL_SIZE
        for brick in self.bricks:
            boff = self._brick_off(brick)
            shape = brick.get("shape", "square")
            brect = cell_rect(brick["col"], brick["row"], shape, boff)
            in_acid = False
            for acid in self.placed_acids:
                cx = max(brect.left, min(acid["x"], brect.right))
                cy = max(brect.top, min(acid["y"], brect.bottom))
                if math.hypot(cx - acid["x"], cy - acid["y"]) < acid_px:
                    in_acid = True
                    break
            if in_acid:
                brick["acid_t"] = 2.0
            elif "acid_t" in brick:
                brick["acid_t"] -= dt
                if brick["acid_t"] <= 0:
                    del brick["acid_t"]



# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw_brick(screen: pygame.Surface, brick: dict,
               font: pygame.font.Font, y_offset: float = 0,
               danger: bool = False, time: float = 0.0,
               frozen: bool = False, in_acid: bool = False,
               reversing: bool = False):
    shape = brick.get("shape", "square")
    color = brick_color(brick["hp"])
    rect = cell_rect(brick["col"], brick["row"], shape, y_offset)

    # Skip if fully outside game area
    if rect.bottom < GRID_TOP or rect.top > GRID_BOTTOM:
        return

    # Frozen/reverse: frame drawn after shape
    draw_ice_frame = frozen
    draw_reverse_frame = reversing and not frozen

    # Acid tint: shift toward green with pulse
    if in_acid:
        pulse = 0.5 + 0.5 * math.sin(time * 6)
        mix = 0.3 + 0.2 * pulse
        r = int(color[0] * (1 - mix) + 120 * mix)
        g = int(color[1] * (1 - mix) + 255 * mix)
        b = int(color[2] * (1 - mix))
        color = (min(255, r), min(255, g), min(255, b))

    # Danger flash: pulse between normal color and red
    if danger and not frozen:
        pulse = 0.5 + 0.5 * math.sin(time * 10)
        r = min(255, int(color[0] + (255 - color[0]) * pulse))
        g = int(color[1] * (1 - pulse * 0.7))
        b = int(color[2] * (1 - pulse * 0.7))
        color = (r, g, b)

    frame_color = (FREEZE_COLOR if draw_ice_frame
                   else REVERSE_COLOR if draw_reverse_frame else None)

    if shape == "round":
        pygame.draw.circle(screen, color, rect.center, BRICK_SIZE // 2)
        if frame_color:
            pygame.draw.circle(screen, frame_color, rect.center,
                               BRICK_SIZE // 2 + 2, 2)
    elif shape == "diamond":
        cx, cy = rect.center
        h = BRICK_SIZE // 2
        pts = [(cx, cy - h), (cx + h, cy), (cx, cy + h), (cx - h, cy)]
        pygame.draw.polygon(screen, color, pts)
        if frame_color:
            pygame.draw.polygon(screen, frame_color, pts, 2)
    elif shape == "hexagon":
        cx, cy = rect.center
        r = BRICK_SIZE / 2
        pts = [(int(cx + r * math.cos(math.pi / 6 + i * math.pi / 3)),
                int(cy + r * math.sin(math.pi / 6 + i * math.pi / 3)))
               for i in range(6)]
        pygame.draw.polygon(screen, color, pts)
        if frame_color:
            pygame.draw.polygon(screen, frame_color, pts, 2)
    elif shape == "trapezoid":
        cx, cy = rect.center
        hw, hh = BRICK_SIZE // 2, BRICK_SIZE // 2
        tw = int(hw * 0.6)
        pts = [(cx - tw, cy - hh), (cx + tw, cy - hh),
               (cx + hw, cy + hh), (cx - hw, cy + hh)]
        pygame.draw.polygon(screen, color, pts)
        if frame_color:
            pygame.draw.polygon(screen, frame_color, pts, 2)
    elif shape == "triangle":
        cx, cy = rect.center
        h = BRICK_SIZE // 2
        d = brick.get("tri_dir", "up")
        if d == "up":
            pts = [(cx, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
        elif d == "down":
            pts = [(cx - h, cy - h), (cx + h, cy - h), (cx, cy + h)]
        elif d == "left":
            pts = [(cx - h, cy), (cx + h, cy - h), (cx + h, cy + h)]
        else:
            pts = [(cx - h, cy - h), (cx - h, cy + h), (cx + h, cy)]
        pygame.draw.polygon(screen, color, pts)
        if frame_color:
            pygame.draw.polygon(screen, frame_color, pts, 2)
    else:  # square, wide, tall
        pygame.draw.rect(screen, color, rect, border_radius=4)
        if frame_color:
            pygame.draw.rect(screen, frame_color, rect.inflate(4, 4),
                             2, border_radius=5)

    # Shield (shape-aware)
    if brick.get("shield", 0) > 0:
        cx, cy = rect.center
        if shape == "round":
            r = BRICK_SIZE // 2 + 2
            arc_rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
            pygame.draw.arc(screen, SHIELD_COLOR, arc_rect,
                            math.pi + 0.3, 2 * math.pi - 0.3, 3)
        elif shape == "diamond":
            half = BRICK_SIZE // 2 + 2
            pygame.draw.lines(screen, SHIELD_COLOR, False, [
                (cx - half, cy), (cx, cy + half), (cx + half, cy)], 3)
        elif shape == "triangle":
            h = BRICK_SIZE // 2 + 2
            d = brick.get("tri_dir", "up")
            if d == "up":
                pygame.draw.line(screen, SHIELD_COLOR,
                                 (cx - h, cy + h), (cx + h, cy + h), 3)
            elif d == "down":
                pygame.draw.lines(screen, SHIELD_COLOR, False, [
                    (cx - h // 2, cy), (cx, cy + h), (cx + h // 2, cy)], 3)
            elif d == "left":
                pygame.draw.lines(screen, SHIELD_COLOR, False, [
                    (cx + h, cy), (cx - h, cy), (cx + h, cy + h)], 3)
            else:
                pygame.draw.lines(screen, SHIELD_COLOR, False, [
                    (cx - h, cy), (cx + h, cy), (cx - h, cy + h)], 3)
        elif shape == "hexagon":
            r = BRICK_SIZE / 2 + 2
            pts = [(int(cx + r * math.cos(math.pi / 6 + i * math.pi / 3)),
                    int(cy + r * math.sin(math.pi / 6 + i * math.pi / 3)))
                   for i in range(3, 6)]
            pygame.draw.lines(screen, SHIELD_COLOR, False, pts, 3)
        elif shape == "trapezoid":
            hw = BRICK_SIZE // 2 + 2
            hh = BRICK_SIZE // 2 + 2
            pygame.draw.line(screen, SHIELD_COLOR,
                             (cx - hw, cy + hh), (cx + hw, cy + hh), 3)
        else:
            pygame.draw.line(screen, SHIELD_COLOR,
                             (rect.left, rect.bottom),
                             (rect.right, rect.bottom), 3)
            glow_surf = pygame.Surface((rect.width, 6), pygame.SRCALPHA)
            glow_surf.fill((*SHIELD_COLOR, 60))
            screen.blit(glow_surf, (rect.left, rect.bottom - 3))

    # HP text
    txt = font.render(str(brick["hp"]), True, TEXT_COLOR)
    screen.blit(txt, txt.get_rect(center=rect.center))


def draw_game(screen: pygame.Surface, game: Game,
              font: pygame.font.Font, small_font: pygame.font.Font):
    screen.fill(BG_COLOR)
    off = game.brick_offset

    # --- Clip region for game area ---
    clip = pygame.Rect(0, GRID_TOP, WIDTH, GRID_BOTTOM - GRID_TOP)
    screen.set_clip(clip)

    # Bricks (per-brick offset for wall blocking)
    danger_y = GRID_BOTTOM - CELL_SIZE
    for brick in game.bricks:
        boff = game._brick_off(brick)
        shape = brick.get("shape", "square")
        extra = CELL_SIZE if shape == "tall" else 0
        bottom = GRID_TOP + (brick["row"] + 1) * CELL_SIZE + extra + boff
        danger = bottom >= danger_y
        is_frozen = game.freeze_timer > 0
        is_reversing = game.reverse_timer > 0
        in_acid = brick.get("acid_t", 0) > 0
        draw_brick(screen, brick, small_font, boff, danger, game.game_time,
                   is_frozen, in_acid, is_reversing)

    # Collectibles
    for col in game.collectibles:
        rect = cell_rect(col["col"], col["row"], "square", off)
        cx, cy = rect.center
        radius = int(BRICK_SIZE * 0.2)
        pygame.draw.circle(screen, COLLECTIBLE_COLOR, (cx, cy), radius)
        txt = small_font.render("+", True, BG_COLOR)
        screen.blit(txt, txt.get_rect(center=(cx, cy)))

    # Bombs (pickup — collect as mortar ammo)
    for bomb in game.bombs:
        rect = cell_rect(bomb["col"], bomb["row"], "square", off)
        cx, cy = rect.center
        radius = int(BRICK_SIZE * 0.22)
        pygame.draw.circle(screen, BOMB_COLOR, (cx, cy), radius)
        txt = small_font.render("B", True, BG_COLOR)
        screen.blit(txt, txt.get_rect(center=(cx, cy)))

    # Mine pickups (on field, advancing)
    for mine in game.mines:
        rect = cell_rect(mine["col"], mine["row"], "square", off)
        cx, cy = rect.center
        radius = int(BRICK_SIZE * 0.22)
        pygame.draw.circle(screen, MINE_COLOR, (cx, cy), radius)
        pygame.draw.circle(screen, (255, 200, 200), (cx, cy), radius, 2)
        txt = small_font.render("M", True, BG_COLOR)
        screen.blit(txt, txt.get_rect(center=(cx, cy)))

    # Acid pickups (on field, advancing)
    for acid in game.acid_pus:
        rect = cell_rect(acid["col"], acid["row"], "square", off)
        cx, cy = rect.center
        radius = int(BRICK_SIZE * 0.22)
        pygame.draw.circle(screen, MORTAR_ACID_COLOR, (cx, cy), radius)
        txt = small_font.render("A", True, BG_COLOR)
        screen.blit(txt, txt.get_rect(center=(cx, cy)))

    # Wall pickups (on field, advancing)
    for wall in game.wall_pus:
        rect = cell_rect(wall["col"], wall["row"], "square", off)
        cx, cy = rect.center
        radius = int(BRICK_SIZE * 0.22)
        pygame.draw.circle(screen, MORTAR_WALL_COLOR, (cx, cy), radius)
        txt = small_font.render("W", True, BG_COLOR)
        screen.blit(txt, txt.get_rect(center=(cx, cy)))

    # Placed mines (stationary, waiting for brick contact)
    for mine in game.placed_mines:
        mx, my = int(mine["x"]), int(mine["y"])
        pygame.draw.circle(screen, MINE_COLOR, (mx, my), 10)
        pygame.draw.circle(screen, (255, 100, 100), (mx, my), 10, 2)
        pygame.draw.line(screen, (255, 200, 200),
                         (mx - 4, my - 4), (mx + 4, my + 4), 2)
        pygame.draw.line(screen, (255, 200, 200),
                         (mx - 4, my + 4), (mx + 4, my - 4), 2)

    # Placed acid zones (stationary, green pulsing circle)
    for acid in game.placed_acids:
        ax, ay = int(acid["x"]), int(acid["y"])
        acid_r = int(ACID_RADIUS_CELLS * CELL_SIZE)
        pulse = 0.5 + 0.5 * math.sin(acid["timer"] * 3)
        alpha = int(40 + 30 * pulse)
        surf = pygame.Surface((acid_r * 2, acid_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (120, 255, 0, alpha),
                           (acid_r, acid_r), acid_r)
        screen.blit(surf, (ax - acid_r, ay - acid_r))
        pygame.draw.circle(screen, MORTAR_ACID_COLOR, (ax, ay), acid_r, 1)

    # Placed walls (horizontal barrier line)
    for wall in game.placed_walls:
        wy = int(wall["y"])
        weight = getattr(game, '_wall_weight', 0)
        ratio = weight / wall["max_weight"] if wall["max_weight"] > 0 else 0
        # Color shifts from orange to red as weight increases
        r_val = min(255, int(160 + 95 * ratio))
        g_val = max(0, int(160 * (1 - ratio)))
        pygame.draw.line(screen, (r_val, g_val, 0), (0, wy), (WIDTH, wy), 3)
        # Weight indicator
        ttl = wall.get("ttl", 0)
        wt_txt = small_font.render(f"{weight}/{wall['max_weight']}  {ttl:.0f}s",
                                   True, MORTAR_WALL_COLOR)
        screen.blit(wt_txt, (4, wy + 4))

    # Fireball PUs (grid-based, advancing)
    for fb in game.fireballs:
        rect = cell_rect(fb["col"], fb["row"], "square", off)
        cx, cy = rect.center
        pygame.draw.circle(screen, FIREBALL_COLOR, (cx, cy), int(BRICK_SIZE * 0.22))
        pygame.draw.circle(screen, (255, 200, 50), (cx, cy), int(BRICK_SIZE * 0.14))
        txt = small_font.render("F", True, BG_COLOR)
        screen.blit(txt, txt.get_rect(center=(cx, cy)))

    # Homing PUs (grid-based, advancing)
    for hm in game.homings:
        rect = cell_rect(hm["col"], hm["row"], "square", off)
        cx, cy = rect.center
        pygame.draw.circle(screen, HOMING_COLOR, (cx, cy), int(BRICK_SIZE * 0.22))
        txt = small_font.render("H", True, BG_COLOR)
        screen.blit(txt, txt.get_rect(center=(cx, cy)))

    # Placed freezes (stationary snowflake icon)
    for fz in game.placed_freezes:
        fx, fy = int(fz["x"]), int(fz["y"])
        # Snowflake: 3 crossing lines
        size = 10
        for i in range(3):
            angle = i * math.pi / 3
            dx = int(size * math.cos(angle))
            dy = int(size * math.sin(angle))
            pygame.draw.line(screen, FREEZE_COLOR,
                             (fx - dx, fy - dy), (fx + dx, fy + dy), 2)

    # Placed reverses (stationary, red arrow-up icon)
    for rv in game.placed_reverses:
        rx, ry = int(rv["x"]), int(rv["y"])
        # Up arrow
        pygame.draw.line(screen, REVERSE_COLOR, (rx, ry + 8), (rx, ry - 8), 2)
        pygame.draw.line(screen, REVERSE_COLOR, (rx - 5, ry - 3), (rx, ry - 8), 2)
        pygame.draw.line(screen, REVERSE_COLOR, (rx + 5, ry - 3), (rx, ry - 8), 2)

    # Reverse wave visual (horizontal line radiates upward from bottom)
    if game.reverse_wave:
        rw = game.reverse_wave
        h = int(rw["height"])
        if h > 0:
            alpha = max(0, min(200, int(200 * (1 - rw["height"] / rw["max_height"]))))
            line_y = GRID_BOTTOM - h
            surf = pygame.Surface((WIDTH, 4), pygame.SRCALPHA)
            surf.fill((*REVERSE_COLOR, alpha))
            screen.blit(surf, (0, line_y))

    # Freeze wave visual
    if game.freeze_wave:
        fw = game.freeze_wave
        r = int(fw["radius"])
        if r > 0:
            alpha = max(0, min(180, int(180 * (1 - fw["radius"] / fw["max_radius"]))))
            surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*FREEZE_COLOR, alpha), (r, r), r, 3)
            screen.blit(surf, (int(fw["x"]) - r, int(fw["y"]) - r))

    # Projectiles
    for p in game.projectiles:
        if p.alive:
            if p.fireball:
                pcolor = FIREBALL_COLOR
            elif p.homing:
                pcolor = HOMING_COLOR
            else:
                pcolor = TEXT_COLOR
            pygame.draw.circle(screen, pcolor,
                               (int(p.pos.x), int(p.pos.y)),
                               PROJECTILE_RADIUS)

    # Mortar shells in flight
    for shell in game.mortar_shells:
        t = shell["t"]
        sx, sy = shell["sx"], shell["sy"]
        tx, ty = shell["tx"], shell["ty"]
        # Parabolic arc: lerp x/y with upward arc
        x = sx + (tx - sx) * t
        arc_height = min(150, math.hypot(tx - sx, ty - sy) * 0.4)
        y = sy + (ty - sy) * t - arc_height * math.sin(t * math.pi)
        # Color by type
        mtype = shell["type"]
        if mtype == "bomb":
            sc = MORTAR_BOMB_COLOR
        elif mtype == "mine":
            sc = MINE_COLOR
        elif mtype == "acid":
            sc = MORTAR_ACID_COLOR
        elif mtype == "wall":
            sc = MORTAR_WALL_COLOR
        else:
            sc = TEXT_COLOR
        pygame.draw.circle(screen, sc, (int(x), int(y)), 6)
        # Trail
        if t > 0.05:
            t2 = t - 0.05
            x2 = sx + (tx - sx) * t2
            y2 = sy + (ty - sy) * t2 - arc_height * math.sin(t2 * math.pi)
            pygame.draw.line(screen, (*sc[:3],), (int(x2), int(y2)),
                             (int(x), int(y)), 2)

    # Explosions
    for e in game.explosions:
        alpha = max(0, min(255, int(255 * e["timer"] / 0.4)))
        radius = int(BOMB_RADIUS_CELLS * CELL_SIZE
                     * (1 - e["timer"] / 0.4) + 10)
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (255, 150, 50, alpha),
                           (radius, radius), radius)
        screen.blit(surf, (int(e["x"]) - radius, int(e["y"]) - radius))

    screen.set_clip(None)

    # --- Gun position + aim line ---
    gx = int(game.gun_x)
    gy = GRID_BOTTOM
    pygame.draw.circle(screen, AMMO_COLOR, (gx, gy), 8)
    if game.phase in ("playing", "paused"):
        aim_len = 40
        ax = gx + math.cos(game.aim_angle) * aim_len
        ay = gy + math.sin(game.aim_angle) * aim_len
        pygame.draw.line(screen, AMMO_COLOR, (gx, gy), (int(ax), int(ay)), 2)

    # --- Crosshair ---
    if game.phase == "playing":
        mx, my = game.crosshair
        size = 12
        pygame.draw.line(screen, CROSSHAIR_COLOR,
                         (mx - size, my), (mx + size, my), 2)
        pygame.draw.line(screen, CROSSHAIR_COLOR,
                         (mx, my - size), (mx, my + size), 2)
        pygame.draw.circle(screen, CROSSHAIR_COLOR, (mx, my), size, 1)

    # --- HUD: Top bar ---
    pygame.draw.rect(screen, HUD_BG, (0, 0, WIDTH, TOP_UI_HEIGHT))
    wave_txt = font.render(f"Wave: {game.wave}", True, TEXT_COLOR)
    screen.blit(wave_txt, (10, 14))
    best_txt = font.render(f"Best: {game.highscore}", True, TEXT_COLOR)
    screen.blit(best_txt, (WIDTH - best_txt.get_width() - 10, 14))

    # Freeze/reverse timer on top bar (centered)
    if game.reverse_timer > 0:
        rt_txt = small_font.render(f"REVERSE {game.reverse_timer:.1f}s",
                                   True, REVERSE_COLOR)
        screen.blit(rt_txt, rt_txt.get_rect(center=(WIDTH // 2, TOP_UI_HEIGHT // 2)))
    elif game.freeze_timer > 0:
        ft_txt = small_font.render(f"FROZEN {game.freeze_timer:.1f}s",
                                   True, FREEZE_COLOR)
        screen.blit(ft_txt, ft_txt.get_rect(center=(WIDTH // 2, TOP_UI_HEIGHT // 2)))

    # --- HUD: Bottom bar ---
    pygame.draw.rect(screen, HUD_BG,
                     (0, GRID_BOTTOM, WIDTH, BOTTOM_AREA_HEIGHT))

    available = game.gun_ammo
    in_flight = len(game.projectiles)
    bullet_cy = GRID_BOTTOM + BOTTOM_AREA_HEIGHT // 2

    # Gun ammo — 5 bullet icons entering from left + count
    for i in range(5):
        bx = 12 + i * 16
        filled = i < available
        color = AMMO_COLOR if filled else (50, 50, 65)
        # Bullet shape: small rounded rect
        pygame.draw.rect(screen, color,
                         (bx - 3, bullet_cy - 10, 8, 20), border_radius=3)
        # Tip highlight
        if filled:
            pygame.draw.rect(screen, (255, 230, 150),
                             (bx - 2, bullet_cy - 10, 6, 5), border_radius=2)

    # Ammo count + modifier indicator
    ammo_label = f"x{available}"
    if game.fireball_charges > 0:
        ammo_label += f"  F:{game.fireball_charges}"
    if game.homing_charges > 0:
        ammo_label += f"  H:{game.homing_charges}"
    count_color = (FIREBALL_COLOR if game.fireball_charges > 0
                   else HOMING_COLOR if game.homing_charges > 0
                   else AMMO_COLOR)
    count_txt = font.render(ammo_label, True, count_color)
    screen.blit(count_txt, (12 + 5 * 16 + 6, bullet_cy - 12))

    # In-flight / reloading indicator
    sub_parts: list[str] = []
    if in_flight > 0:
        sub_parts.append(f"{in_flight} flying")
    if game.gun_reloading > 0:
        sub_parts.append(f"{game.gun_reloading} reload")
    if sub_parts:
        fly_txt = small_font.render("  ".join(sub_parts), True, (130, 130, 160))
        screen.blit(fly_txt, (12 + 5 * 16 + 6, bullet_cy + 6))

    # Mortar ammo — next-to-fire under gun (center), fills right
    mortar_start_x = WIDTH // 2
    for i, mtype in enumerate(game.mortar_ammo):
        mx = mortar_start_x + i * 24
        if mx + 11 > WIDTH - 4:
            break  # don't overflow off screen
        if mtype == "bomb":
            color, label = MORTAR_BOMB_COLOR, "B"
        elif mtype == "mine":
            color, label = MINE_COLOR, "M"
        elif mtype == "acid":
            color, label = MORTAR_ACID_COLOR, "A"
        elif mtype == "wall":
            color, label = MORTAR_WALL_COLOR, "W"
        else:
            continue
        pygame.draw.circle(screen, color, (mx, bullet_cy), 11)
        t = small_font.render(label, True, BG_COLOR)
        screen.blit(t, t.get_rect(center=(mx, bullet_cy)))

    # --- Pause overlay ---
    if game.phase == "paused":
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))
        txt = font.render("PAUSED", True, TEXT_COLOR)
        screen.blit(txt, txt.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
        hint = small_font.render("Space to resume  |  Esc for menu",
                                 True, (180, 180, 180))
        screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 30)))

    # --- Game over overlay ---
    if game.phase == "gameover":
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill(GAMEOVER_OVERLAY)
        screen.blit(overlay, (0, 0))
        go_txt = font.render("GAME OVER", True, TEXT_COLOR)
        screen.blit(go_txt,
                    go_txt.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30)))
        w_txt = font.render(f"Wave {game.wave}", True, TEXT_COLOR)
        screen.blit(w_txt,
                    w_txt.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 10)))
        if game.wave >= game.highscore and game.wave > 0:
            new_txt = font.render("NEW BEST!", True, AMMO_COLOR)
            screen.blit(new_txt,
                        new_txt.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 40)))
        hint = small_font.render("Click to continue", True, (180, 180, 180))
        screen.blit(hint,
                    hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 70)))


def draw_menu(screen: pygame.Surface, font: pygame.font.Font,
              small_font: pygame.font.Font) -> pygame.Rect:
    screen.fill(BG_COLOR)

    title = font.render("BRICKS RT", True, TEXT_COLOR)
    screen.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 3 - 40)))
    sub = small_font.render("Real-time brick breaker", True, (150, 150, 180))
    screen.blit(sub, sub.get_rect(center=(WIDTH // 2, HEIGHT // 3)))

    # Play button
    play_rect = pygame.Rect(WIDTH // 2 - 80, HEIGHT // 2 - 20, 160, 50)
    pygame.draw.rect(screen, (60, 60, 90), play_rect, border_radius=8)
    pygame.draw.rect(screen, TEXT_COLOR, play_rect, 2, border_radius=8)
    play_txt = font.render("PLAY", True, TEXT_COLOR)
    screen.blit(play_txt, play_txt.get_rect(center=play_rect.center))

    hs = load_highscore("realtime")
    if hs > 0:
        hs_txt = small_font.render(f"Best: Wave {hs}", True, (150, 150, 180))
        screen.blit(hs_txt,
                    hs_txt.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 60)))

    controls = [
        "Left click / hold — Fire gun",
        "Right click — Fire mortar (later)",
        "Space — Pause",
        "Esc — Menu",
    ]
    for i, line in enumerate(controls):
        t = small_font.render(line, True, (110, 110, 140))
        screen.blit(t, t.get_rect(center=(WIDTH // 2,
                                          HEIGHT * 2 // 3 + i * 24)))

    return play_rect


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("BricksRT")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("Arial", 22, bold=True)
    small_font = pygame.font.SysFont("Arial", 16, bold=True)

    game = Game()
    play_rect: pygame.Rect | None = None
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
                    if play_rect and play_rect.collidepoint(mx, my):
                        game.start()
                elif game.phase == "gameover":
                    game.phase = "menu"

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if game.phase == "playing":
                    game.fire_mortar()

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                mouse_held = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    if game.phase == "playing":
                        game.phase = "paused"
                    elif game.phase == "paused":
                        game.phase = "playing"
                if event.key == pygame.K_ESCAPE:
                    if game.phase in ("playing", "paused"):
                        game.phase = "menu"

        mouse_pos = pygame.mouse.get_pos()

        if game.phase == "menu":
            play_rect = draw_menu(screen, font, small_font)
            pygame.display.flip()
            continue

        # Update aim and fire while playing
        if game.phase == "playing":
            game.update_aim(mouse_pos)
            if mouse_held:
                game.fire_gun()
            game.update(dt)

        # Hide system cursor when crosshair is shown
        pygame.mouse.set_visible(game.phase != "playing")

        draw_game(screen, game, font, small_font)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
