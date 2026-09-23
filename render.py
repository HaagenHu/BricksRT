"""BricksRT rendering — all drawing, no game logic."""

import colorsys
import math
import random

import pygame

from game import (
    WIDTH, HEIGHT, TOP_UI_HEIGHT, BOTTOM_AREA_HEIGHT, GRID_TOP, GRID_BOTTOM,
    CELL_SIZE, BRICK_SIZE, PROJECTILE_RADIUS, GUN_BARREL_LEN,
    BOMB_RADIUS_CELLS,
    ACID_RADIUS_CELLS, TAR_RADIUS_CELLS, AMMO_TYPES, UNLOCK,
    SPAWN_ANIM_TIME, DEATH_ANIM_TIME, BRICK_FLASH_TIME, AMMO_FLASH_TIME,
    HIT_FLASH_TIME, GUN_KICK_TIME, MORTAR_COOLDOWN, COLS, MAX_ROWS,
    Brick, Game, cell_rect, make_shards, step_shards,
)

# UI typeface: first installed name wins (Bahnschrift ships with
# Windows 10+; Arial is the fallback elsewhere)
UI_FONT = "bahnschrift,arial"

# Colors
BG_COLOR = (20, 20, 30)
TEXT_COLOR = (255, 255, 255)
CROSSHAIR_COLOR = (60, 160, 255)  # azure — the one hue bricks never use
CROSSHAIR_OUTLINE = (10, 10, 15)
COLLECTIBLE_COLOR = (235, 210, 90)  # gold, matches the HUD ammo bullets
BOMB_COLOR = (255, 80, 50)
AMMO_COLOR = (220, 200, 100)
SHIELD_COLOR = (0, 220, 255)
MINE_COLOR = (225, 228, 238)  # steel — separates it from the red bomb
MORTAR_BOMB_COLOR = (255, 80, 50)
MORTAR_ACID_COLOR = (120, 255, 0)
MORTAR_WALL_COLOR = (255, 160, 40)
TAR_COLOR = (150, 125, 90)
FREEZE_COLOR = (150, 230, 255)
REVERSE_COLOR = (255, 80, 80)
FIREBALL_COLOR = (255, 100, 0)
HOMING_COLOR = (0, 255, 150)
LIGHTNING_COLOR = (255, 240, 120)
SKULL_COLOR = (200, 100, 255)
GAMEOVER_OVERLAY = (0, 0, 0, 180)
HUD_BG = (30, 30, 45)
HUD_TOP = (38, 38, 58)     # panel gradient, outer edge
HUD_LABEL = (130, 130, 170)
SLOT_BG = (19, 19, 30)
GRID_DOT = (46, 46, 70)
TURRET_METAL = (92, 96, 128)

SHAKE_PX = 10  # max field offset at full shake trauma

# Mortar landing reticle radius per round type (px)
MORTAR_FOOTPRINT = {
    "bomb": BOMB_RADIUS_CELLS * CELL_SIZE,
    "homing": BOMB_RADIUS_CELLS * CELL_SIZE,
    "acid": ACID_RADIUS_CELLS * CELL_SIZE,
    "tar": TAR_RADIUS_CELLS * CELL_SIZE,
    "mine": 12,
}


def _shell_pos(shell: dict, t: float) -> tuple[float, float]:
    """Point on a mortar shell's parabolic arc at progress t (0..1)."""
    sx, sy, tx, ty = shell["sx"], shell["sy"], shell["tx"], shell["ty"]
    arc_height = min(150, math.hypot(tx - sx, ty - sy) * 0.4)
    return (sx + (tx - sx) * t,
            sy + (ty - sy) * t - arc_height * math.sin(t * math.pi))


# Field pickup style: type -> (color, label, radius factor)
PICKUP_STYLE = {
    "ammo": (COLLECTIBLE_COLOR, "+", 0.20),
    "mine": (MINE_COLOR, "M", 0.22),
    "wall": (MORTAR_WALL_COLOR, "W", 0.22),
    "bomb": (BOMB_COLOR, "B", 0.22),
    "tar": (TAR_COLOR, "T", 0.22),
    "acid": (MORTAR_ACID_COLOR, "A", 0.22),
    "homing": (HOMING_COLOR, "H", 0.22),
}

# HUD slot / shell style per shared-ammo type
AMMO_STYLE = {
    "mine": (MINE_COLOR, "M"),
    "wall": (MORTAR_WALL_COLOR, "W"),
    "bomb": (MORTAR_BOMB_COLOR, "B"),
    "tar": (TAR_COLOR, "T"),
    "acid": (MORTAR_ACID_COLOR, "A"),
    "homing": (HOMING_COLOR, "H"),
}

# Starfield: parallax layers as (speed px/s, radius, shade, star count).
# Positions are generated once from a fixed seed.
_STAR_LAYER_SPECS = ((3.0, 1, 70, 45), (6.0, 1, 110, 26), (11.0, 2, 160, 12))
_star_layers: list[tuple[float, int, tuple[int, int, int],
                         list[tuple[int, int]]]] = []


def draw_starfield(screen: pygame.Surface, t: float,
                   top: int = GRID_TOP, bottom: int = GRID_BOTTOM):
    """Dim stars drifting slowly downward; nearer layers are brighter,
    bigger, and faster. Driven by game time, so pause freezes it."""
    if not _star_layers:
        rng = random.Random(12)
        for speed, size, shade, count in _STAR_LAYER_SPECS:
            color = (shade, shade, min(255, shade + 25))
            stars = [(rng.randrange(WIDTH), rng.randrange(HEIGHT))
                     for _ in range(count)]
            _star_layers.append((speed, size, color, stars))
    span = bottom - top
    for speed, size, color, stars in _star_layers:
        drift = t * speed
        for sx, sy in stars:
            y = top + (sy + drift) % span
            pygame.draw.circle(screen, color, (sx, int(y)), size)


# Danger gradient: pre-rendered red glow, alpha 0 at the top to max at
# the bottom, scaled at blit time by how close the lowest brick is
DANGER_GRAD_H = CELL_SIZE * 3
_danger_grad: pygame.Surface | None = None


def _danger_gradient() -> pygame.Surface:
    global _danger_grad
    if _danger_grad is None:
        surf = pygame.Surface((WIDTH, DANGER_GRAD_H), pygame.SRCALPHA)
        for yy in range(DANGER_GRAD_H):
            a = int(85 * (yy / DANGER_GRAD_H) ** 2)
            pygame.draw.line(surf, (255, 40, 30, a), (0, yy), (WIDTH, yy))
        _danger_grad = surf
    return _danger_grad


def _mix(a: tuple[int, int, int], b: tuple[int, int, int],
         t: float) -> tuple[int, int, int]:
    """Linear blend from color a (t=0) to color b (t=1)."""
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _blit_centered(screen: pygame.Surface, txt: pygame.Surface,
                   center: tuple[float, float]):
    """Blit rendered text so its visible glyphs (not its line box) are
    centered on the point. Bahnschrift's line box sits ~3px low around
    its capitals, so box-centering floats labels above their shapes."""
    ink = txt.get_bounding_rect()
    screen.blit(txt, (int(center[0] - ink.centerx),
                      int(center[1] - ink.centery)))


# Additive glow: radial-gradient sprites on black, blitted with
# BLEND_ADD (black adds nothing). Built once and cached — never per
# frame. Color, radius and strength are quantized so the cache stays
# small even for animated effects and the endless HP color range.
GLOW_LEVELS = 8
_glow_cache: dict[tuple, pygame.Surface] = {}


def _glow_sprite(color: tuple[int, int, int], radius: int,
                 strength: float) -> pygame.Surface:
    color = tuple(c // 16 * 16 for c in color)
    # Fine steps for small sprites, coarse for big ones (memory)
    step = 4 if radius <= 32 else 16
    radius = max(4, (radius + step - 1) // step * step)
    level = max(1, min(GLOW_LEVELS, round(strength * GLOW_LEVELS)))
    key = (color, radius, level)
    surf = _glow_cache.get(key)
    if surf is None:
        surf = pygame.Surface((radius * 2, radius * 2))
        k = level / GLOW_LEVELS
        for r in range(radius, 0, -1):
            f = k * (1 - r / radius) ** 2
            pygame.draw.circle(surf, [int(c * f) for c in color],
                               (radius, radius), r)
        _glow_cache[key] = surf
    return surf


def draw_glow(screen: pygame.Surface, color: tuple[int, int, int],
              x: float, y: float, radius: float, strength: float = 1.0):
    if strength <= 0:
        return
    surf = _glow_sprite(color, int(radius), strength)
    r = surf.get_width() // 2
    screen.blit(surf, (int(x) - r, int(y) - r),
                special_flags=pygame.BLEND_ADD)


# Brick halos: the brick's silhouette in a dimmed HP color, blurred,
# with a margin for the glow to bleed into. Cached per shape + color.
HALO_PAD = 10
_halo_cache: dict[tuple, pygame.Surface] = {}


def _brick_halo(shape: str, tri_dir: str,
                color: tuple[int, int, int]) -> pygame.Surface:
    color = tuple(c // 16 * 16 for c in color)
    key = (shape, tri_dir, color)
    surf = _halo_cache.get(key)
    if surf is None:
        body = cell_rect(0, 0, shape)
        surf = pygame.Surface((body.width + HALO_PAD * 2,
                               body.height + HALO_PAD * 2))
        local = pygame.Rect(HALO_PAD, HALO_PAD, body.width, body.height)
        dim = [int(c * 0.8) for c in color]
        pts = shape_points(shape, tri_dir, *local.center, BRICK_SIZE / 2)
        if shape == "round":
            pygame.draw.circle(surf, dim, local.center, BRICK_SIZE // 2)
        elif pts is not None:
            pygame.draw.polygon(surf, dim, pts)
        else:
            pygame.draw.rect(surf, dim, local, border_radius=4)
        surf = pygame.transform.gaussian_blur(surf, 6)
        _halo_cache[key] = surf
    return surf


# Translucent discs (acid/tar zones) and smoke puffs: SRCALPHA sprites
# cached per radius and quantized alpha instead of rebuilt every frame
_disc_cache: dict[tuple, pygame.Surface] = {}
_smoke_cache: dict[int, pygame.Surface] = {}


def _alpha_disc(color: tuple[int, int, int], radius: int,
                alpha: int) -> pygame.Surface:
    key = (color, radius, alpha // 8)
    surf = _disc_cache.get(key)
    if surf is None:
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*color, alpha // 8 * 8),
                           (radius, radius), radius)
        _disc_cache[key] = surf
    return surf


_nebula_bg: pygame.Surface | None = None


def _nebula() -> pygame.Surface:
    """Full-screen backdrop: faint purple/blue/teal clouds on the bg
    color. Painted at quarter size, blurred, then smooth-scaled up —
    built once from a fixed seed."""
    global _nebula_bg
    if _nebula_bg is None:
        rng = random.Random(5)
        lw, lh = WIDTH // 4, HEIGHT // 4
        clouds = pygame.Surface((lw, lh))
        palette = ((70, 30, 110), (25, 50, 120), (15, 85, 105),
                   (95, 30, 80))
        for _ in range(9):
            k = rng.uniform(0.25, 0.5)
            pygame.draw.circle(clouds, [int(c * k) for c in rng.choice(palette)],
                               (rng.randrange(lw), rng.randrange(lh)),
                               rng.randint(12, 34))
        clouds = pygame.transform.gaussian_blur(clouds, 14)
        base = pygame.Surface((lw, lh))
        base.fill(BG_COLOR)
        base.blit(clouds, (0, 0), special_flags=pygame.BLEND_ADD)
        _nebula_bg = pygame.transform.smoothscale(base, (WIDTH, HEIGHT))
    return _nebula_bg


# HUD bars: vertical gradient panels with an azure accent line on the
# edge facing the field
_hud_cache: dict[tuple[int, bool], pygame.Surface] = {}


def _hud_panel(height: int, edge_at_bottom: bool) -> pygame.Surface:
    key = (height, edge_at_bottom)
    surf = _hud_cache.get(key)
    if surf is None:
        surf = pygame.Surface((WIDTH, height))
        for y in range(height):
            t = y / max(1, height - 1)
            if not edge_at_bottom:
                t = 1 - t
            surf.fill(_mix(HUD_TOP, HUD_BG, t), (0, y, WIDTH, 1))
        edge_y = height - 1 if edge_at_bottom else 0
        surf.fill(_mix(BG_COLOR, CROSSHAIR_COLOR, 0.45), (0, edge_y, WIDTH, 1))
        _hud_cache[key] = surf
    return surf


def _pill(screen: pygame.Surface, font: pygame.font.Font, text: str,
          color: tuple[int, int, int], center: tuple[int, int]):
    """Status badge: text in a dark rounded capsule with a colored rim."""
    txt = font.render(text, True, color)
    r = txt.get_rect(center=center).inflate(20, 8)
    pygame.draw.rect(screen, SLOT_BG, r, border_radius=r.height // 2)
    pygame.draw.rect(screen, _mix(BG_COLOR, color, 0.7), r, 1,
                     border_radius=r.height // 2)
    _blit_centered(screen, txt, center)


# Glowing text (titles, overlays): the text blurred on black, blitted
# additively under a crisp copy. Cached per font, text and color.
_text_glow_cache: dict[tuple, pygame.Surface] = {}
_ui_fonts: dict[tuple[int, bool], pygame.font.Font] = {}


def _ui_font(size: int, bold: bool = True) -> pygame.font.Font:
    """UI typeface at any size. Bahnschrift's bold is synthesized and
    ~15% wider, so dense text (help rows, HUD status) uses regular."""
    key = (size, bold)
    if key not in _ui_fonts:
        _ui_fonts[key] = pygame.font.SysFont(UI_FONT, size, bold=bold)
    return _ui_fonts[key]


def draw_glow_text(screen: pygame.Surface, font: pygame.font.Font,
                   text: str, color: tuple[int, int, int],
                   center: tuple[int, int],
                   glow_color: tuple[int, int, int] | None = None):
    glow_color = glow_color or color
    key = (id(font), text, glow_color)
    glow = _text_glow_cache.get(key)
    if glow is None:
        txt = font.render(text, True, glow_color)
        pad = 18
        glow = pygame.Surface((txt.get_width() + pad * 2,
                               txt.get_height() + pad * 2))
        glow.blit(txt, (pad, pad))
        glow = pygame.transform.gaussian_blur(glow, 9)
        _text_glow_cache[key] = glow
    screen.blit(glow, glow.get_rect(center=center),
                special_flags=pygame.BLEND_ADD)
    txt = font.render(text, True, color)
    screen.blit(txt, txt.get_rect(center=center))


# Soft glow around a rounded rect (hovered buttons), cached per size
_rect_glow_cache: dict[tuple, pygame.Surface] = {}


def _rect_glow(size: tuple[int, int],
               color: tuple[int, int, int]) -> pygame.Surface:
    key = (size, color)
    surf = _rect_glow_cache.get(key)
    if surf is None:
        pad = 14
        surf = pygame.Surface((size[0] + pad * 2, size[1] + pad * 2))
        pygame.draw.rect(surf, [int(c * 0.6) for c in color],
                         (pad, pad, *size), border_radius=8)
        surf = pygame.transform.gaussian_blur(surf, 8)
        _rect_glow_cache[key] = surf
    return surf


def _button(screen: pygame.Surface, rect: pygame.Rect, label: str,
            font: pygame.font.Font, fill: tuple[int, int, int],
            edge: tuple[int, int, int]):
    """Menu button; hovering lifts the fill and lights an azure rim."""
    hover = rect.collidepoint(pygame.mouse.get_pos())
    if hover:
        glow = _rect_glow(rect.size, CROSSHAIR_COLOR)
        screen.blit(glow, glow.get_rect(center=rect.center),
                    special_flags=pygame.BLEND_ADD)
        fill = _mix(fill, TEXT_COLOR, 0.12)
        edge = CROSSHAIR_COLOR
    pygame.draw.rect(screen, fill, rect, border_radius=8)
    pygame.draw.rect(screen, edge, rect, 2, border_radius=8)
    _blit_centered(screen, font.render(label, True, TEXT_COLOR), rect.center)


_freeze_tint: pygame.Surface | None = None


def _freeze_overlay() -> pygame.Surface:
    """Field-sized icy wash, alpha set per frame to fade it out."""
    global _freeze_tint
    if _freeze_tint is None:
        _freeze_tint = pygame.Surface((WIDTH, GRID_BOTTOM - GRID_TOP))
        _freeze_tint.fill(FREEZE_COLOR)
    return _freeze_tint


def _smoke_sprite(radius: int) -> pygame.Surface:
    radius = max(8, (radius + 7) // 8 * 8)
    surf = _smoke_cache.get(radius)
    if surf is None:
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        # Concentric fills overwrite (no blending) -> soft radial falloff
        for r in range(radius, 0, -1):
            a = int(120 * (1 - r / radius) ** 1.5)
            pygame.draw.circle(surf, (75, 72, 88, a), (radius, radius), r)
        _smoke_cache[radius] = surf
    return surf


# Brick bevel: light from the top-left — edges facing it are lighter,
# edges facing away darker, so flat fills read as raised tiles
LIGHT_DIR = (-0.6, -0.8)


def _bevel_colors(color):
    return _mix(color, TEXT_COLOR, 0.5), _mix(color, (0, 0, 0), 0.45)


def _bevel_polygon(screen: pygame.Surface, pts, color):
    hi, lo = _bevel_colors(color)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    for a, b in zip(pts, pts[1:] + pts[:1]):
        # Outward direction ~ edge midpoint minus centroid (convex)
        ox = (a[0] + b[0]) / 2 - cx
        oy = (a[1] + b[1]) / 2 - cy
        lit = ox * LIGHT_DIR[0] + oy * LIGHT_DIR[1] > 0
        pygame.draw.line(screen, hi if lit else lo, a, b, 2)


def _bevel_rect(screen: pygame.Surface, r: pygame.Rect, color):
    hi, lo = _bevel_colors(color)
    pygame.draw.line(screen, hi, (r.left + 3, r.top + 1),
                     (r.right - 4, r.top + 1), 2)
    pygame.draw.line(screen, hi, (r.left + 1, r.top + 3),
                     (r.left + 1, r.bottom - 4), 2)
    pygame.draw.line(screen, lo, (r.left + 3, r.bottom - 2),
                     (r.right - 4, r.bottom - 2), 2)
    pygame.draw.line(screen, lo, (r.right - 2, r.top + 3),
                     (r.right - 2, r.bottom - 4), 2)


def _bevel_circle(screen: pygame.Surface, center, radius: int, color):
    hi, lo = _bevel_colors(color)
    box = pygame.Rect(0, 0, radius * 2, radius * 2)
    box.center = center
    # Angles run counter-clockwise from +x (y up): 45..225 deg = top-left
    pygame.draw.arc(screen, hi, box, math.pi / 4, 5 * math.pi / 4, 2)
    pygame.draw.arc(screen, lo, box, 5 * math.pi / 4, 9 * math.pi / 4, 2)


def draw_pickup_icon(screen: pygame.Surface, font: pygame.font.Font,
                     ptype: str, cx: int, cy: int):
    color, label, rfactor = PICKUP_STYLE[ptype]
    radius = int(BRICK_SIZE * rfactor)
    pygame.draw.circle(screen, color, (cx, cy), radius)
    if ptype == "mine":
        pygame.draw.circle(screen, (220, 60, 60), (cx, cy), radius, 2)
    _blit_centered(screen, font.render(label, True, BG_COLOR), (cx, cy))


def draw_freeze_icon(screen: pygame.Surface, fx: int, fy: int):
    # Snowflake: 3 crossing lines
    size = 10
    for i in range(3):
        angle = i * math.pi / 3
        dx = int(size * math.cos(angle))
        dy = int(size * math.sin(angle))
        pygame.draw.line(screen, FREEZE_COLOR,
                         (fx - dx, fy - dy), (fx + dx, fy + dy), 2)


def draw_reverse_icon(screen: pygame.Surface, rx: int, ry: int):
    # Up arrow
    pygame.draw.line(screen, REVERSE_COLOR, (rx, ry + 8), (rx, ry - 8), 2)
    pygame.draw.line(screen, REVERSE_COLOR, (rx - 5, ry - 3), (rx, ry - 8), 2)
    pygame.draw.line(screen, REVERSE_COLOR, (rx + 5, ry - 3), (rx, ry - 8), 2)


def draw_lightning_icon(screen: pygame.Surface, lx: int, ly: int):
    pts = [(lx + 4, ly - 9), (lx - 3, ly - 1), (lx + 1, ly - 1),
           (lx - 4, ly + 9)]
    pygame.draw.lines(screen, LIGHTNING_COLOR, False, pts, 3)


def draw_skull_icon(screen: pygame.Surface, sx: int, sy: int):
    pygame.draw.circle(screen, SKULL_COLOR, (sx, sy - 1), 9)
    pygame.draw.rect(screen, SKULL_COLOR, (sx - 5, sy + 4, 10, 5))
    pygame.draw.circle(screen, BG_COLOR, (sx - 3, sy - 2), 2)
    pygame.draw.circle(screen, BG_COLOR, (sx + 3, sy - 2), 2)


def brick_color(hp: int) -> tuple[int, int, int]:
    """Map HP to rainbow gradient. Low HP = green, high HP = red/violet."""
    t = min(1.0, math.log(1 + hp) / math.log(1 + 100))
    hue = 0.33 - t * 0.5
    if hue < 0:
        hue += 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.95)
    return (int(r * 255), int(g * 255), int(b * 255))


def shape_points(shape: str, tri_dir: str, cx: float, cy: float,
                 h: float) -> list[tuple[float, float]] | None:
    """Polygon vertices for a brick shape with half-size h, or None for
    shapes drawn as a circle/rect (round, square, wide, tall)."""
    if shape == "diamond":
        return [(cx, cy - h), (cx + h, cy), (cx, cy + h), (cx - h, cy)]
    if shape == "hexagon":
        return [(cx + h * math.cos(math.pi / 6 + i * math.pi / 3),
                 cy + h * math.sin(math.pi / 6 + i * math.pi / 3))
                for i in range(6)]
    if shape == "trapezoid":
        tw = h * 0.6
        return [(cx - tw, cy - h), (cx + tw, cy - h),
                (cx + h, cy + h), (cx - h, cy + h)]
    if shape == "triangle":
        if tri_dir == "up":
            return [(cx, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
        if tri_dir == "down":
            return [(cx - h, cy - h), (cx + h, cy - h), (cx, cy + h)]
        if tri_dir == "left":
            return [(cx - h, cy), (cx + h, cy - h), (cx + h, cy + h)]
        return [(cx - h, cy - h), (cx - h, cy + h), (cx + h, cy)]
    return None


def draw_brick(screen: pygame.Surface, brick: Brick,
               font: pygame.font.Font, y_offset: float = 0,
               danger: bool = False, time: float = 0.0,
               frozen: bool = False, in_acid: bool = False,
               reversing: bool = False, stunned: bool = False):
    shape = brick.shape
    color = brick_color(brick.hp)
    rect = cell_rect(brick.col, brick.row, shape, y_offset)

    # Skip if fully outside game area
    if rect.bottom < GRID_TOP or rect.top > GRID_BOTTOM:
        return

    # Frozen/stun/reverse: frame drawn after shape
    draw_ice_frame = frozen
    draw_stun_frame = stunned and not frozen
    draw_reverse_frame = reversing and not frozen and not stunned

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

    # Skull sweep: bright purple-white flash fading out
    if brick.flash > 0:
        mix = 0.85 * (brick.flash / BRICK_FLASH_TIME)
        color = tuple(int(c * (1 - mix) + f * mix)
                      for c, f in zip(color, (235, 190, 255)))

    # Hit flash: brief white pop on every damaging hit
    if brick.hit_t > 0:
        color = _mix(color, TEXT_COLOR, 0.75 * brick.hit_t / HIT_FLASH_TIME)

    frame_color = (FREEZE_COLOR if draw_ice_frame
                   else LIGHTNING_COLOR if draw_stun_frame
                   else TAR_COLOR if brick.slow_t > 0 and not reversing
                   else REVERSE_COLOR if draw_reverse_frame else None)

    pts = shape_points(shape, brick.tri_dir, *rect.center, BRICK_SIZE / 2)
    if shape == "round":
        pygame.draw.circle(screen, color, rect.center, BRICK_SIZE // 2)
        _bevel_circle(screen, rect.center, BRICK_SIZE // 2, color)
        if frame_color:
            pygame.draw.circle(screen, frame_color, rect.center,
                               BRICK_SIZE // 2 + 2, 2)
    elif pts is not None:  # diamond, hexagon, trapezoid, triangle
        pygame.draw.polygon(screen, color, pts)
        if frame_color:  # the frame sits on the edges, replacing the bevel
            pygame.draw.polygon(screen, frame_color, pts, 2)
        else:
            _bevel_polygon(screen, pts, color)
    else:  # square, wide, tall
        pygame.draw.rect(screen, color, rect, border_radius=4)
        _bevel_rect(screen, rect, color)
        if frame_color:
            pygame.draw.rect(screen, frame_color, rect.inflate(4, 4),
                             2, border_radius=5)

    # Shield (shape-aware)
    if brick.shield > 0:
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
            d = brick.tri_dir
            if d == "up":
                pygame.draw.line(screen, SHIELD_COLOR,
                                 (cx - h, cy + h), (cx + h, cy + h), 3)
            elif d == "down":
                pygame.draw.lines(screen, SHIELD_COLOR, False, [
                    (cx - h // 2, cy), (cx, cy + h), (cx + h // 2, cy)], 3)
            elif d == "left":
                # Bottom slant: apex (left) to bottom-right corner
                pygame.draw.line(screen, SHIELD_COLOR,
                                 (cx - h, cy), (cx + h, cy + h), 3)
            else:
                # Bottom slant: bottom-left corner to apex (right)
                pygame.draw.line(screen, SHIELD_COLOR,
                                 (cx - h, cy + h), (cx + h, cy), 3)
        elif shape == "hexagon":
            r = BRICK_SIZE / 2 + 2
            # Bottom three vertices (screen y grows downward)
            pts = [(int(cx + r * math.cos(math.pi / 6 + i * math.pi / 3)),
                    int(cy + r * math.sin(math.pi / 6 + i * math.pi / 3)))
                   for i in range(3)]
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

    # Frost glint: while frozen, each brick twinkles now and then at a
    # fixed spot (seeded by its cell; frozen bricks don't move rows)
    if frozen:
        seed = brick.col * 7 + brick.row * 13
        twinkle = max(0.0, math.sin(time * 3 + seed)) ** 6
        if twinkle > 0.05:
            gx = rect.left + 8 + (seed * 37) % max(1, rect.width - 16)
            gy = rect.top + 8 + (seed * 53) % max(1, rect.height - 16)
            draw_glow(screen, TEXT_COLOR, gx, gy, 8, 0.8 * twinkle)
            arm = int(5 * twinkle)
            if arm:
                pygame.draw.line(screen, TEXT_COLOR, (gx - arm, gy),
                                 (gx + arm, gy), 1)
                pygame.draw.line(screen, TEXT_COLOR, (gx, gy - arm),
                                 (gx, gy + arm), 1)

    # HP text
    _blit_centered(screen, font.render(str(brick.hp), True, TEXT_COLOR),
                   rect.center)


def draw_dying_brick(screen: pygame.Surface, d: dict):
    """Shrinking ghost of a killed brick — starts white-hot, cools to
    its own color as it shrinks (the shards carry the rest)."""
    s = max(0.0, d["timer"] / DEATH_ANIM_TIME)
    if s <= 0:
        return
    color = _mix(brick_color(d["hp"]), TEXT_COLOR, 0.7 * s)
    cx, cy = int(d["cx"]), int(d["cy"])
    h = (BRICK_SIZE / 2) * s
    shape = d["shape"]
    pts = shape_points(shape, d["tri_dir"], cx, cy, h)
    if shape == "round":
        pygame.draw.circle(screen, color, (cx, cy), int(h))
    elif pts is not None:  # diamond, hexagon, trapezoid, triangle
        pygame.draw.polygon(screen, color, pts)
    else:  # square, wide, tall — shrink the bounding box
        w2 = h * (2.0 if shape == "wide" else 1.0)
        h2 = h * (2.0 if shape == "tall" else 1.0)
        rect = pygame.Rect(int(cx - w2), int(cy - h2),
                           int(w2 * 2), int(h2 * 2))
        pygame.draw.rect(screen, color, rect, border_radius=3)


def draw_shards(screen: pygame.Surface, shards: list[dict]):
    """Kill shards: spinning triangles that shrink and cool toward the bg."""
    for s in shards:
        f = s["timer"] / s["life"]
        color = brick_color(s["hp"])
        size = s["size"] * (0.4 + 0.6 * f)
        pts = [(s["x"] + size * math.cos(s["rot"] + k * math.tau / 3),
                s["y"] + size * math.sin(s["rot"] + k * math.tau / 3))
               for k in range(3)]
        draw_glow(screen, color, s["x"], s["y"], 10, 0.4 * f)
        pygame.draw.polygon(screen, _mix(BG_COLOR, color, 0.35 + 0.65 * f),
                            pts)


def draw_game(screen: pygame.Surface, game: Game,
              font: pygame.font.Font, small_font: pygame.font.Font):
    screen.blit(_nebula(), (0, 0))
    off = game.brick_offset

    # --- Clip region for game area ---
    clip = pygame.Rect(0, GRID_TOP, WIDTH, GRID_BOTTOM - GRID_TOP)
    screen.set_clip(clip)

    draw_starfield(screen, game.game_time)

    # Floor grid: faint dots at the inner cell corners, scrolling with
    # the advance so the field's motion reads between row spawns
    for row in range(-1, MAX_ROWS + 1):
        y = int(GRID_TOP + row * CELL_SIZE + off)
        for col in range(1, COLS):
            screen.fill(GRID_DOT, (col * CELL_SIZE - 1, y - 1, 2, 2))

    # Red danger glow at the bottom — fades in as the lowest brick
    # enters the last three rows, full strength at the death line
    if game.bricks:
        lowest = max(GRID_TOP + (b.row + 1) * CELL_SIZE + b.extra_height
                     + game._brick_off(b) for b in game.bricks)
        p = (lowest - (GRID_BOTTOM - DANGER_GRAD_H)) / DANGER_GRAD_H
        if p > 0:
            grad = _danger_gradient()
            grad.set_alpha(int(255 * min(1.0, p)))
            screen.blit(grad, (0, GRID_BOTTOM - DANGER_GRAD_H))

    # Bricks (per-brick offset for wall blocking)
    danger_y = GRID_BOTTOM - CELL_SIZE
    placed: list[tuple[Brick, float]] = []
    for brick in game.bricks:
        boff = game._brick_off(brick)
        # Spawn slide-in: start one cell up, behind the HUD (visual only)
        if brick.spawn_t > 0:
            boff -= CELL_SIZE * (brick.spawn_t / SPAWN_ANIM_TIME)
        placed.append((brick, boff))

    # Halos in their own pass first, so one brick's glow never washes
    # over a neighbor's face — it only lights the gaps between them
    for brick, boff in placed:
        rect = cell_rect(brick.col, brick.row, brick.shape, boff)
        halo = _brick_halo(brick.shape, brick.tri_dir, brick_color(brick.hp))
        screen.blit(halo, halo.get_rect(center=rect.center),
                    special_flags=pygame.BLEND_ADD)

    for brick, boff in placed:
        bottom = (GRID_TOP + (brick.row + 1) * CELL_SIZE
                  + brick.extra_height + boff)
        danger = bottom >= danger_y
        draw_brick(screen, brick, small_font, boff, danger, game.game_time,
                   game.freeze_timer > 0, brick.acid_t > 0,
                   game.reverse_timer > 0, brick.stun > 0)

    # Freeze: icy wash over the field, fading over the last half second
    if game.freeze_timer > 0:
        tint = _freeze_overlay()
        tint.set_alpha(int(30 * min(1.0, game.freeze_timer / 0.5)))
        screen.blit(tint, (0, GRID_TOP))

    # Dying bricks (shrink out)
    for d in game.dying_bricks:
        draw_dying_brick(screen, d)

    draw_shards(screen, game.shards)

    # Explosion smoke: soft gray puffs that swell, drift up and thin out
    for s in game.smoke:
        f = s["timer"] / s["life"]
        puff = _smoke_sprite(int(s["r"]))
        puff.set_alpha(int(255 * f))
        r = puff.get_width() // 2
        screen.blit(puff, (int(s["x"]) - r, int(s["y"]) - r))

    # Sticky charges riding bricks: blinking mine dot
    for ch in game.sticky_charges:
        b = ch["brick"]
        if b not in game.bricks:
            continue
        rect = cell_rect(b.col, b.row, b.shape, game._brick_off(b))
        blink = int(ch["timer"] * 8) % 2 == 0
        dot = (255, 70, 70) if blink else MINE_COLOR
        pygame.draw.circle(screen, dot,
                           (rect.centerx + 14, rect.centery - 14), 5)

    # Field pickups
    for pu in game.pickups:
        rect = cell_rect(pu["col"], pu["row"], "square", off)
        draw_glow(screen, PICKUP_STYLE[pu["type"]][0], *rect.center, 22, 0.5)
        draw_pickup_icon(screen, small_font, pu["type"], *rect.center)

    # Placed mines (stationary, waiting for brick contact)
    for mine in game.placed_mines:
        mx, my = int(mine["x"]), int(mine["y"])
        draw_glow(screen, (255, 70, 70), mx, my, 20, 0.45)
        pygame.draw.circle(screen, MINE_COLOR, (mx, my), 10)
        pygame.draw.circle(screen, (255, 100, 100), (mx, my), 10, 2)
        pygame.draw.line(screen, (200, 40, 40),
                         (mx - 4, my - 4), (mx + 4, my + 4), 2)
        pygame.draw.line(screen, (200, 40, 40),
                         (mx - 4, my + 4), (mx + 4, my - 4), 2)

    # Placed acid zones: pulsing green pool with bubbles that rise,
    # swell and pop; fades out over its last half second
    bubble_color = (170, 255, 90)
    for acid in game.placed_acids:
        ax, ay = int(acid["x"]), int(acid["y"])
        acid_r = int(ACID_RADIUS_CELLS * CELL_SIZE)
        t = acid["timer"]  # counts down
        fade = min(1.0, t / 0.5)
        pulse = 0.5 + 0.5 * math.sin(t * 3)
        alpha = int((40 + 30 * pulse) * fade)
        screen.blit(_alpha_disc((120, 255, 0), acid_r, alpha),
                    (ax - acid_r, ay - acid_r))
        pygame.draw.circle(screen, _mix(BG_COLOR, MORTAR_ACID_COLOR, fade),
                           (ax, ay), acid_r, 1)
        # Bubbles: deterministic per zone (seeded by its position), spread
        # by the golden angle, each on its own rise-swell-pop cycle
        seed = ax * 31 + ay * 17
        for i in range(10):
            a = seed * 0.37 + i * 2.39996
            rr = acid_r * 0.85 * math.sqrt((i + 0.5) / 10)
            phase = (-t * (0.6 + 0.07 * (i % 5)) + i * 0.137) % 1.0
            bx = ax + math.cos(a) * rr
            by = ay + math.sin(a) * rr - phase * 8
            if phase < 0.85:
                br = 2.5 + 3 * phase / 0.85
                bcol = _mix(BG_COLOR, bubble_color, 0.8 * fade)
            else:  # pop: quick expanding, fading ring
                pop = (phase - 0.85) / 0.15
                br = 5 + 4 * pop
                bcol = _mix(BG_COLOR, bubble_color, 0.8 * fade * (1 - pop))
            pygame.draw.circle(screen, bcol, (int(bx), int(by)), int(br), 1)

    # Placed tar zones: dark pool with a slowly wobbling edge and a
    # glossy highlight; fades out over its last moments
    for tar in game.placed_tars:
        tx, ty = int(tar["x"]), int(tar["y"])
        tar_r = int(TAR_RADIUS_CELLS * CELL_SIZE)
        t = tar["timer"]
        fade = min(1.0, t / 0.6)
        screen.blit(_alpha_disc((60, 50, 35), tar_r, int(130 * fade)),
                    (tx - tar_r, ty - tar_r))
        edge = []
        for k in range(36):
            a = k * math.tau / 36
            wob = (1 + 0.018 * math.sin(3 * a + t * 1.7)
                   + 0.010 * math.sin(5 * a - t * 1.1))
            edge.append((tx + math.cos(a) * tar_r * wob,
                         ty + math.sin(a) * tar_r * wob))
        pygame.draw.polygon(screen, _mix(BG_COLOR, TAR_COLOR, fade), edge, 2)
        gloss = pygame.Rect(0, 0, int(tar_r * 1.3), int(tar_r * 1.3))
        gloss.center = (int(tx - tar_r * 0.12), int(ty - tar_r * 0.12))
        pygame.draw.arc(screen, _mix(BG_COLOR, (215, 195, 160), 0.6 * fade),
                        gloss, math.pi * 0.55, math.pi * 0.95, 3)

    # Placed walls: energy barrier — glowing core line inside a honeycomb
    # strip that flickers faster as the load nears breaking; dimmer
    # while still arming (grace period)
    hex_r = 6
    for wall in game.placed_walls:
        wy = int(wall["y"])
        weight = game.wall_weight
        ratio = weight / wall["max_weight"] if wall["max_weight"] > 0 else 0
        # Color shifts from orange to red as weight increases
        r_val = min(255, int(160 + 95 * ratio))
        g_val = max(0, int(160 * (1 - ratio)))
        wcolor = (r_val, g_val, 0)
        power = 0.5 if wall.get("grace", 0) > 0 else 1.0
        for gx in range(12, WIDTH, 24):
            draw_glow(screen, wcolor, gx, wy, 16, 0.45 * power)
        t = game.game_time
        for i in range(int(WIDTH / (hex_r * 1.5)) + 2):
            cx = i * hex_r * 1.5
            cy = wy + (hex_r * 0.43 if i % 2 else -hex_r * 0.43)
            flick = 0.55 + 0.45 * math.sin(t * (6 + 20 * ratio) + i * 1.7)
            hcol = _mix(BG_COLOR, wcolor, (0.3 + 0.5 * flick) * power)
            pygame.draw.polygon(screen, hcol, [
                (cx + hex_r * math.cos(k * math.pi / 3),
                 cy + hex_r * math.sin(k * math.pi / 3)) for k in range(6)], 1)
        pygame.draw.line(screen, _mix(wcolor, TEXT_COLOR, 0.35 * power),
                         (0, wy), (WIDTH, wy), 2)
        # Weight indicator
        ttl = wall.get("ttl", 0)
        wt_txt = small_font.render(f"{weight}/{wall['max_weight']}  {ttl:.0f}s",
                                   True, MORTAR_WALL_COLOR)
        screen.blit(wt_txt, (4, wy + 4))

    # Placed AoE pickups (stationary icons)
    for items, gcolor in ((game.placed_freezes, FREEZE_COLOR),
                          (game.placed_reverses, REVERSE_COLOR),
                          (game.placed_lightnings, LIGHTNING_COLOR),
                          (game.placed_skulls, SKULL_COLOR)):
        for it in items:
            draw_glow(screen, gcolor, it["x"], it["y"], 20, 0.5)
    for fz in game.placed_freezes:
        draw_freeze_icon(screen, int(fz["x"]), int(fz["y"]))
    for rv in game.placed_reverses:
        draw_reverse_icon(screen, int(rv["x"]), int(rv["y"]))
    for lt in game.placed_lightnings:
        draw_lightning_icon(screen, int(lt["x"]), int(lt["y"]))
    for sk in game.placed_skulls:
        draw_skull_icon(screen, int(sk["x"]), int(sk["y"]))

    # Lightning bolts (brief jagged flashes)
    for bolt in game.lightning_bolts:
        pts = [(int(x), int(y)) for x, y in bolt["points"]]
        if len(pts) >= 2:
            for gx, gy in pts[::2]:
                draw_glow(screen, LIGHTNING_COLOR, gx, gy, 16, 0.4)
            pygame.draw.lines(screen, LIGHTNING_COLOR, False, pts, 3)
            pygame.draw.lines(screen, TEXT_COLOR, False, pts, 1)

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

    # Freeze/skull wave visuals (expanding circles)
    for wave, wcolor in ((game.freeze_wave, FREEZE_COLOR),
                         (game.skull_wave, SKULL_COLOR)):
        if wave:
            r = int(wave["radius"])
            if r > 0:
                alpha = max(0, min(180, int(180 * (1 - wave["radius"] / wave["max_radius"]))))
                # Direct ring blended toward the bg: these grow past the
                # screen size, so a per-frame alpha surface would be huge
                pygame.draw.circle(screen, _mix(BG_COLOR, wcolor, alpha / 255),
                                   (int(wave["x"]), int(wave["y"])), r, 3)

    # Projectiles
    for p in game.projectiles:
        if p.alive:
            if p.fireball:
                pcolor = FIREBALL_COLOR
            elif p.homing:
                pcolor = HOMING_COLOR
            elif p.tar:
                pcolor = TAR_COLOR
            elif p.acid:
                pcolor = MORTAR_ACID_COLOR
            elif p.wallshot:
                pcolor = MORTAR_WALL_COLOR
            else:
                pcolor = TEXT_COLOR
            # Trail: a tapering streak cooling toward the bg (segments
            # plus round joints); glow on every other point keeps the
            # blit count down in big volleys
            pts = list(p.trail) + [(p.pos.x, p.pos.y)]
            n = len(p.trail)
            for i in range(n):
                f = (i + 1) / (n + 1)
                (x1, y1), (x2, y2) = pts[i], pts[i + 1]
                if i % 2 == n % 2:
                    draw_glow(screen, pcolor, x1, y1,
                              PROJECTILE_RADIUS * 3, 0.5 * f)
                tcolor = _mix(BG_COLOR, pcolor, 0.75 * f)
                w = max(1, int(PROJECTILE_RADIUS * 1.6 * f))
                pygame.draw.line(screen, tcolor, (int(x1), int(y1)),
                                 (int(x2), int(y2)), w)
                pygame.draw.circle(screen, tcolor, (int(x1), int(y1)),
                                   max(1, w // 2))
            draw_glow(screen, pcolor, p.pos.x, p.pos.y,
                      PROJECTILE_RADIUS * 4, 0.8)
            pygame.draw.circle(screen, pcolor,
                               (int(p.pos.x), int(p.pos.y)),
                               PROJECTILE_RADIUS)

    # Mortar shells in flight
    for shell in game.mortar_shells:
        t = shell["t"]
        tx, ty = shell["tx"], shell["ty"]
        mtype = shell["type"]
        sc = AMMO_STYLE.get(mtype, (TEXT_COLOR, "?"))[0]

        # Landing reticle: the round's footprint at the target, plus a
        # ring that closes in on it as the shell comes down
        foot = MORTAR_FOOTPRINT.get(mtype, 12)
        dim = _mix(BG_COLOR, sc, 0.45)
        itx, ity = int(tx), int(ty)
        if mtype == "wall":
            for dx in range(0, WIDTH, 16):
                pygame.draw.line(screen, dim, (dx, ity), (dx + 8, ity), 2)
        else:
            pygame.draw.circle(screen, dim, (itx, ity), int(foot), 1)
        pygame.draw.circle(screen, sc, (itx, ity),
                           int(foot * (1 - t)) + 4, 2)

        # Fading trail along the arc, then the shell itself
        prev = _shell_pos(shell, t)
        for k in range(1, 7):
            t2 = t - k * 0.025
            if t2 <= 0:
                break
            cur = _shell_pos(shell, t2)
            f = 1 - k / 7
            pygame.draw.line(screen, _mix(BG_COLOR, sc, f),
                             (int(prev[0]), int(prev[1])),
                             (int(cur[0]), int(cur[1])),
                             max(1, int(4 * f)))
            prev = cur
        x, y = _shell_pos(shell, t)
        draw_glow(screen, sc, x, y, 20, 0.8)
        pygame.draw.circle(screen, sc, (int(x), int(y)), 6)

    # Explosions: white-hot core for the first moments, hot glow that
    # fades, and a shockwave ring racing out past the blast radius
    blast_px = BOMB_RADIUS_CELLS * CELL_SIZE
    for e in game.explosions:
        age = 1 - max(0.0, e["timer"]) / 0.4  # 0 -> 1
        ex, ey = e["x"], e["y"]
        draw_glow(screen, (255, 160, 70), ex, ey, blast_px * 1.2, 1 - age)
        if age < 0.25:
            draw_glow(screen, TEXT_COLOR, ex, ey, blast_px * 0.6,
                      1 - age / 0.25)
        ring_r = int(blast_px * (0.3 + 0.9 * age ** 0.6))
        pygame.draw.circle(screen, _mix(BG_COLOR, (255, 215, 160), 1 - age),
                           (int(ex), int(ey)), ring_r,
                           max(1, int(6 * (1 - age))))

    # Explosion sparks: short streaks along their velocity
    for s in game.sparks:
        f = s["timer"] / s["life"]
        x, y = s["x"], s["y"]
        tail = (x - s["vx"] * 0.03, y - s["vy"] * 0.03)
        color = _mix(BG_COLOR, s["color"], f)
        pygame.draw.line(screen, color, (int(tail[0]), int(tail[1])),
                         (int(x), int(y)), 2)
        draw_glow(screen, s["color"], x, y, 8, 0.5 * f)

    # Screen shake: nudge the whole field (HUD, gun and crosshair stay
    # put so aiming never shakes). Deterministic wobble from game time.
    if game.shake > 0 and game.phase == "playing":
        amp = SHAKE_PX * game.shake ** 2
        t = game.game_time
        dx = int(amp * math.sin(t * 91.0) * math.cos(t * 23.0))
        dy = int(amp * math.cos(t * 83.0) * math.sin(t * 31.0 + 1.3))
        if dx or dy:
            screen.scroll(dx, dy)

    screen.set_clip(None)

    # --- Gun turret: dome on the HUD edge (the bottom bar covers its
    # lower half), tapered barrel along the aim that recoils on each
    # trigger, muzzle flash at the tip. The tip band and dome core
    # show the next loaded special bullet's color. ---
    gx = int(game.gun_x)
    gy = GRID_BOTTOM
    load_color = (AMMO_STYLE[game.gun_queue[0]][0] if game.gun_queue
                  else AMMO_COLOR)
    kick = game.gun_kick / GUN_KICK_TIME
    draw_glow(screen, load_color, gx, gy, 28, 0.45)
    if game.phase in ("playing", "paused"):
        ca, sa = math.cos(game.aim_angle), math.sin(game.aim_angle)
        nx, ny = -sa, ca  # barrel normal
        length = GUN_BARREL_LEN - 6 * kick  # recoil pulls it in

        def along(d: float, w: float) -> tuple[float, float]:
            return gx + ca * d + nx * w, gy + sa * d + ny * w

        barrel = [along(0, 5), along(length, 3),
                  along(length, -3), along(0, -5)]
        pygame.draw.polygon(screen, TURRET_METAL, barrel)
        pygame.draw.polygon(screen, CROSSHAIR_OUTLINE, barrel, 1)
        pygame.draw.polygon(screen, load_color, [
            along(length - 6, 3.4), along(length, 3),
            along(length, -3), along(length - 6, -3.4)])
        if kick > 0.4:  # muzzle flash at the (unrecoiled) launch point
            tip_x, tip_y = along(GUN_BARREL_LEN, 0)
            # Kept soft: fresh shots add their own glow right here
            draw_glow(screen, (255, 235, 180), tip_x, tip_y, 16, 0.4 * kick)
            for spread in (-0.5, 0, 0.5):
                a = game.aim_angle + spread
                ray = 9 * kick if spread else 13 * kick
                pygame.draw.line(screen, (255, 245, 210),
                                 (int(tip_x), int(tip_y)),
                                 (int(tip_x + math.cos(a) * ray),
                                  int(tip_y + math.sin(a) * ray)), 2)
    pygame.draw.circle(screen, TURRET_METAL, (gx, gy), 14)
    _bevel_circle(screen, (gx, gy), 14, TURRET_METAL)
    pygame.draw.circle(screen, load_color, (gx, gy), 5)

    # --- Crosshair (dark outline under a bright stroke for contrast) ---
    if game.phase == "playing":
        mx, my = game.crosshair
        size = 12
        draw_glow(screen, CROSSHAIR_COLOR, mx, my, 24, 0.35)
        # Selected mortar round: a pip in its color at the lower right,
        # and a ring filling clockwise from the top while it reloads
        sel = AMMO_TYPES[game.ammo_sel]
        if game.ammo_inv[sel] > 0:
            scol = AMMO_STYLE[sel][0]
            pygame.draw.circle(screen, CROSSHAIR_OUTLINE,
                               (mx + size + 5, my + size + 5), 5)
            pygame.draw.circle(screen, scol,
                               (mx + size + 5, my + size + 5), 4)
            ready = 1 - max(0.0, game.mortar_cooldown) / MORTAR_COOLDOWN
            if ready < 1:
                box = pygame.Rect(0, 0, 2 * size + 10, 2 * size + 10)
                box.center = (mx, my)
                pygame.draw.arc(screen, scol, box,
                                math.pi / 2 - math.tau * ready, math.pi / 2,
                                2)
        pygame.draw.line(screen, CROSSHAIR_OUTLINE,
                         (mx - size, my), (mx + size, my), 5)
        pygame.draw.line(screen, CROSSHAIR_OUTLINE,
                         (mx, my - size), (mx, my + size), 5)
        pygame.draw.circle(screen, CROSSHAIR_OUTLINE, (mx, my), size, 3)
        pygame.draw.line(screen, CROSSHAIR_COLOR,
                         (mx - size, my), (mx + size, my), 2)
        pygame.draw.line(screen, CROSSHAIR_COLOR,
                         (mx, my - size), (mx, my + size), 2)
        pygame.draw.circle(screen, CROSSHAIR_COLOR, (mx, my), size, 1)

    # --- HUD: Top bar ---
    screen.blit(_hud_panel(TOP_UI_HEIGHT, True), (0, 0))
    # Muted small-caps label beside a bright value, both centered
    mid = TOP_UI_HEIGHT // 2
    lbl = small_font.render("WAVE", True, HUD_LABEL)
    num = font.render(str(game.wave), True, TEXT_COLOR)
    screen.blit(lbl, lbl.get_rect(midleft=(12, mid + 1)))
    screen.blit(num, num.get_rect(midleft=(12 + lbl.get_width() + 8, mid)))
    num = font.render(str(game.highscore), True, TEXT_COLOR)
    num_rect = num.get_rect(midright=(WIDTH - 12, mid))
    lbl = small_font.render("BEST", True, HUD_LABEL)
    screen.blit(lbl, lbl.get_rect(midright=(num_rect.left - 8, mid + 1)))
    screen.blit(num, num_rect)

    # Freeze/reverse timer on top bar (centered badge)
    if game.reverse_timer > 0:
        _pill(screen, small_font, f"REVERSE {game.reverse_timer:.1f}s",
              REVERSE_COLOR, (WIDTH // 2, mid))
    elif game.freeze_timer > 0:
        _pill(screen, small_font, f"FROZEN {game.freeze_timer:.1f}s",
              FREEZE_COLOR, (WIDTH // 2, mid))

    # --- HUD: Bottom bar ---
    screen.blit(_hud_panel(BOTTOM_AREA_HEIGHT, False), (0, GRID_BOTTOM))

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

    # Ammo count + volley indicator
    ammo_label = f"x{available}"
    volley = game.volley_size()
    if volley > 1 and available > 0:
        ammo_label += f" ({volley}x)"
    count_color = (AMMO_STYLE[game.gun_queue[0]][0] if game.gun_queue
                   else AMMO_COLOR)
    if game.ammo_flash > 0:
        # Skull just cut the pool: pulse the count purple
        mix = ((0.5 + 0.5 * math.sin(game.game_time * 14))
               * game.ammo_flash / AMMO_FLASH_TIME)
        count_color = tuple(int(c * (1 - mix) + s * mix)
                            for c, s in zip(count_color, SKULL_COLOR))
    count_txt = font.render(ammo_label, True, count_color)
    screen.blit(count_txt, (12 + 5 * 16 + 6, bullet_cy - 12))

    # In-flight / reloading / gun load indicator
    sub_parts: list[str] = []
    if in_flight > 0:
        sub_parts.append(f"{in_flight} flying")
    if game.gun_reloading > 0:
        sub_parts.append(f"{game.gun_reloading} reload")
    if game.gun_queue:
        # Compress the queue into per-type counts in firing order
        runs: dict[str, int] = {}
        for t in game.gun_queue:
            runs[t] = runs.get(t, 0) + 1
        load = " ".join(f"{AMMO_STYLE[t][1]}{n}" for t, n in runs.items())
        sub_parts.append(f"load {load}")
    if game.ammo_debt > 0:
        sub_parts.append(f"-{game.ammo_debt} skull")
    if sub_parts:
        fly_txt = _ui_font(15, bold=False).render("  ".join(sub_parts), True,
                                                  (130, 130, 160))
        screen.blit(fly_txt, (12 + 5 * 16 + 6, bullet_cy + 6))

    # Shared ammo — one inset slot per type (right side): beveled type
    # ball with its count below; the selected slot gets a rim in its
    # type color and a glow (a neutral rim if it's empty)
    slot_w = 40
    slot_cy = GRID_BOTTOM + 20
    ammo_start_x = WIDTH - len(AMMO_TYPES) * slot_w + 14
    for i, mtype in enumerate(AMMO_TYPES):
        mx = ammo_start_x + i * slot_w
        count = game.ammo_inv[mtype]
        color, label = AMMO_STYLE[mtype]
        stocked = count > 0
        slot = pygame.Rect(0, 0, slot_w - 6, BOTTOM_AREA_HEIGHT - 8)
        slot.center = (mx, GRID_BOTTOM + BOTTOM_AREA_HEIGHT // 2)
        pygame.draw.rect(screen, SLOT_BG, slot, border_radius=7)
        if i == game.ammo_sel:
            if stocked:
                draw_glow(screen, color, mx, slot_cy, 22, 0.45)
            pygame.draw.rect(screen, color if stocked else HUD_LABEL, slot,
                             2, border_radius=7)
        if not stocked:
            color = (60, 60, 75)
        pygame.draw.circle(screen, color, (mx, slot_cy), 11)
        if stocked:
            _bevel_circle(screen, (mx, slot_cy), 11, color)
        _blit_centered(screen, small_font.render(label, True, BG_COLOR),
                       (mx, slot_cy))
        cnt_color = TEXT_COLOR if count > 0 else (100, 100, 120)
        cnt = small_font.render(str(count), True, cnt_color)
        screen.blit(cnt, cnt.get_rect(center=(mx, slot_cy + 24)))

    # --- Pause overlay ---
    if game.phase == "paused":
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))
        draw_glow_text(screen, _ui_font(40), "PAUSED", TEXT_COLOR,
                       (WIDTH // 2, HEIGHT // 2 - 8), CROSSHAIR_COLOR)
        hint = small_font.render("Space to resume  |  Esc for menu",
                                 True, (180, 180, 180))
        screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 30)))

    # --- Game over overlay ---
    if game.phase == "gameover":
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill(GAMEOVER_OVERLAY)
        screen.blit(overlay, (0, 0))
        draw_glow_text(screen, _ui_font(44), "GAME OVER", TEXT_COLOR,
                       (WIDTH // 2, HEIGHT // 2 - 34), REVERSE_COLOR)
        w_txt = font.render(f"Wave {game.wave}", True, TEXT_COLOR)
        screen.blit(w_txt,
                    w_txt.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 10)))
        if game.new_best:
            draw_glow_text(screen, font, "NEW BEST!", AMMO_COLOR,
                           (WIDTH // 2, HEIGHT // 2 + 40))
        hint = small_font.render("Click to continue", True, (180, 180, 180))
        screen.blit(hint,
                    hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 70)))


# Menu backdrop: dimmed demo bricks drift down in the grid columns and
# shatter at a random height. Wall-clock driven (the menu has no game
# time); own RNG so it never touches gameplay randomness.
MENU_SHAPES = ("square", "round", "diamond", "hexagon", "triangle",
               "trapezoid")
MENU_MAX_BRICKS = 10
_menu_rng = random.Random()
_menu_fx: dict = {"last": None, "spawn": 0.0, "bricks": [], "shards": []}


def _draw_menu_bricks(screen: pygame.Surface, now: float):
    fx = _menu_fx
    dt = 0.0 if fx["last"] is None else min(0.05, max(0.0, now - fx["last"]))
    fx["last"] = now
    rng = _menu_rng

    fx["spawn"] -= dt
    if fx["spawn"] <= 0 and len(fx["bricks"]) < MENU_MAX_BRICKS:
        fx["spawn"] = rng.uniform(0.5, 1.1)
        fx["bricks"].append({
            "x": rng.randrange(COLS) * CELL_SIZE + CELL_SIZE / 2,
            "y": -CELL_SIZE / 2, "v": rng.uniform(18, 40),
            "shape": rng.choice(MENU_SHAPES),
            "tri_dir": rng.choice(("up", "down")),
            "hp": rng.randint(1, 100),
            "pop_y": rng.uniform(0.3, 0.95) * HEIGHT,
        })
    alive = []
    for b in fx["bricks"]:
        b["y"] += b["v"] * dt
        if b["y"] >= b["pop_y"]:
            fx["shards"].extend(make_shards(b["x"], b["y"], BRICK_SIZE,
                                            BRICK_SIZE, b["hp"]))
        else:
            alive.append(b)
    fx["bricks"] = alive
    fx["shards"] = step_shards(fx["shards"], dt)

    for b in fx["bricks"]:
        color = _mix(BG_COLOR, brick_color(b["hp"]), 0.5)
        center = (int(b["x"]), int(b["y"]))
        halo = _brick_halo(b["shape"], b["tri_dir"], color)
        screen.blit(halo, halo.get_rect(center=center),
                    special_flags=pygame.BLEND_ADD)
        pts = shape_points(b["shape"], b["tri_dir"], *center, BRICK_SIZE / 2)
        if b["shape"] == "round":
            pygame.draw.circle(screen, color, center, BRICK_SIZE // 2)
            _bevel_circle(screen, center, BRICK_SIZE // 2, color)
        elif pts is not None:
            pygame.draw.polygon(screen, color, pts)
            _bevel_polygon(screen, pts, color)
        else:
            rect = pygame.Rect(0, 0, BRICK_SIZE, BRICK_SIZE)
            rect.center = center
            pygame.draw.rect(screen, color, rect, border_radius=4)
            _bevel_rect(screen, rect, color)
    draw_shards(screen, fx["shards"])


def draw_menu(screen: pygame.Surface, font: pygame.font.Font,
              small_font: pygame.font.Font,
              highscore: int) -> tuple[pygame.Rect, pygame.Rect]:
    """Returns (play button rect, help button rect)."""
    now = pygame.time.get_ticks() / 1000.0
    screen.blit(_nebula(), (0, 0))
    draw_starfield(screen, now, 0, HEIGHT)
    _draw_menu_bricks(screen, now)

    # Title: slow hue cycle in the glow, near-white letters on top
    r, g, b = colorsys.hsv_to_rgb(int(now / 12 * 36) % 36 / 36, 0.7, 1.0)
    hue = (int(r * 255), int(g * 255), int(b * 255))
    draw_glow_text(screen, _ui_font(60), "BRICKS RT",
                   _mix(TEXT_COLOR, hue, 0.2), (WIDTH // 2, HEIGHT // 3 - 44),
                   hue)
    sub = small_font.render("Real-time brick breaker", True, (150, 150, 180))
    screen.blit(sub, sub.get_rect(center=(WIDTH // 2, HEIGHT // 3 + 4)))

    play_rect = pygame.Rect(WIDTH // 2 - 80, HEIGHT // 2 - 20, 160, 50)
    _button(screen, play_rect, "PLAY", font, (60, 60, 90), TEXT_COLOR)
    help_rect = pygame.Rect(WIDTH // 2 - 60, HEIGHT // 2 + 44, 120, 36)
    _button(screen, help_rect, "HELP", small_font, (45, 45, 70),
            (150, 150, 180))

    if highscore > 0:
        hs_txt = small_font.render(f"Best: Wave {highscore}", True, (150, 150, 180))
        screen.blit(hs_txt,
                    hs_txt.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 106)))

    controls = [
        "Left click / hold — Fire gun",
        "Right click — Fire mortar",
        "Scroll / 1-6 — Select ammo type",
        "R — Load gun: 1 unit = 5 bullets of it",
        "Q — Panic mortars at lowest row",
        "W — Panic gun: load all types",
        "Space — Pause",
        "Esc — Menu",
    ]
    for i, line in enumerate(controls):
        t = small_font.render(line, True, (110, 110, 140))
        screen.blit(t, t.get_rect(center=(WIDTH // 2,
                                          HEIGHT * 2 // 3 + 20 + i * 24)))

    return play_rect, help_rect


def draw_help(screen: pygame.Surface, font: pygame.font.Font,
              small_font: pygame.font.Font):
    """Pickup legend: every field icon with its effect and unlock wave."""
    screen.blit(_nebula(), (0, 0))
    draw_starfield(screen, pygame.time.get_ticks() / 1000.0, 0, HEIGHT)

    draw_glow_text(screen, _ui_font(34), "PICKUPS", TEXT_COLOR,
                   (WIDTH // 2, 42), CROSSHAIR_COLOR)

    icon_x, text_x = 40, 68
    header_color = (150, 150, 180)
    text_color = (200, 200, 215)
    text_font = _ui_font(16, bold=False)  # long lines: regular fits
    y = 84

    def header(label: str):
        nonlocal y
        t = text_font.render(label, True, header_color)
        screen.blit(t, (24, y))
        y += 28

    def row(icon_fn, desc: str):
        nonlocal y
        icon_fn(y)
        t = text_font.render(desc, True, text_color)
        screen.blit(t, (text_x, y - 9))
        y += 28

    def pickup(ptype):
        return lambda ry: draw_pickup_icon(screen, small_font, ptype,
                                           icon_x, ry)

    header("AMMO — 1 unit: right click = mortar, R = load gun (5 shots)")
    row(pickup("ammo"), "Ammo — +1 gun ball (gun only)")
    row(pickup("mine"),
        f"Mine — contact trap / sticky blast (wave {UNLOCK['mines']}+)")
    row(pickup("wall"),
        f"Wall — barrier / stop brick 2s (wave {UNLOCK['wall']}+)")
    row(pickup("bomb"),
        f"Bomb — area blast / piercing fire (wave {UNLOCK['bombs']}+)")
    row(pickup("tar"),
        f"Tar — slow zone 8s / slow 15% per hit (wave {UNLOCK['tar']}+)")
    row(pickup("acid"),
        f"Acid — melts shields then hp, 1/s (wave {UNLOCK['acid']}+)")
    row(pickup("homing"),
        f"Homing — rocket / steering shots (wave {UNLOCK['homing']}+)")

    y += 8
    header("AOE — shoot it, or it fires when a brick touches it")
    row(lambda ry: draw_freeze_icon(screen, icon_x, ry),
        f"Freeze — stops advance 5s (wave {UNLOCK['freeze']}+)")
    row(lambda ry: draw_reverse_icon(screen, icon_x, ry),
        f"Reverse — bricks retreat 3s (wave {UNLOCK['reverse']}+)")
    row(lambda ry: draw_lightning_icon(screen, icon_x, ry),
        f"Lightning — zaps + stuns 6 bricks 2s (wave {UNLOCK['lightning']}+)")
    row(lambda ry: draw_skull_icon(screen, icon_x, ry),
        "Skull — halves brick HP/shields + ammo (10 min+)")

    hint = small_font.render("Click or Esc to return", True, (180, 180, 180))
    screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT - 30)))
