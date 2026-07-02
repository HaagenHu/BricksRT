"""BricksRT rendering — all drawing, no game logic."""

import colorsys
import math

import pygame

from game import (
    WIDTH, HEIGHT, TOP_UI_HEIGHT, BOTTOM_AREA_HEIGHT, GRID_TOP, GRID_BOTTOM,
    CELL_SIZE, BRICK_SIZE, PROJECTILE_RADIUS, BOMB_RADIUS_CELLS,
    ACID_RADIUS_CELLS, MORTAR_TYPES, UNLOCK, Brick, Game, cell_rect,
)

# Colors
BG_COLOR = (20, 20, 30)
TEXT_COLOR = (255, 255, 255)
CROSSHAIR_COLOR = (200, 200, 200)
COLLECTIBLE_COLOR = (100, 255, 130)
BOMB_COLOR = (255, 80, 50)
AMMO_COLOR = (220, 200, 100)
SHIELD_COLOR = (0, 220, 255)
MINE_COLOR = (255, 50, 50)
MORTAR_BOMB_COLOR = (255, 80, 50)
MORTAR_ACID_COLOR = (120, 255, 0)
MORTAR_WALL_COLOR = (255, 160, 40)
FREEZE_COLOR = (150, 230, 255)
REVERSE_COLOR = (255, 80, 80)
FIREBALL_COLOR = (255, 100, 0)
HOMING_COLOR = (0, 255, 150)
LIGHTNING_COLOR = (255, 240, 120)
SKULL_COLOR = (200, 100, 255)
GAMEOVER_OVERLAY = (0, 0, 0, 180)
HUD_BG = (30, 30, 45)

# Field pickup style: type -> (color, label, radius factor)
PICKUP_STYLE = {
    "ammo": (COLLECTIBLE_COLOR, "+", 0.20),
    "bomb": (BOMB_COLOR, "B", 0.22),
    "mine": (MINE_COLOR, "M", 0.22),
    "acid": (MORTAR_ACID_COLOR, "A", 0.22),
    "wall": (MORTAR_WALL_COLOR, "W", 0.22),
    "fireball": (FIREBALL_COLOR, "F", 0.22),
    "homing": (HOMING_COLOR, "H", 0.22),
}

MORTAR_STYLE = {
    "bomb": (MORTAR_BOMB_COLOR, "B"),
    "mine": (MINE_COLOR, "M"),
    "acid": (MORTAR_ACID_COLOR, "A"),
    "wall": (MORTAR_WALL_COLOR, "W"),
}


def draw_pickup_icon(screen: pygame.Surface, font: pygame.font.Font,
                     ptype: str, cx: int, cy: int):
    color, label, rfactor = PICKUP_STYLE[ptype]
    radius = int(BRICK_SIZE * rfactor)
    pygame.draw.circle(screen, color, (cx, cy), radius)
    if ptype == "mine":
        pygame.draw.circle(screen, (255, 200, 200), (cx, cy), radius, 2)
    elif ptype == "fireball":
        pygame.draw.circle(screen, (255, 200, 50), (cx, cy),
                           int(BRICK_SIZE * 0.14))
    txt = font.render(label, True, BG_COLOR)
    screen.blit(txt, txt.get_rect(center=(cx, cy)))


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


def draw_brick(screen: pygame.Surface, brick: Brick,
               font: pygame.font.Font, y_offset: float = 0,
               danger: bool = False, time: float = 0.0,
               frozen: bool = False, in_acid: bool = False,
               reversing: bool = False):
    shape = brick.shape
    color = brick_color(brick.hp)
    rect = cell_rect(brick.col, brick.row, shape, y_offset)

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
        d = brick.tri_dir
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
    txt = font.render(str(brick.hp), True, TEXT_COLOR)
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
        bottom = (GRID_TOP + (brick.row + 1) * CELL_SIZE
                  + brick.extra_height + boff)
        danger = bottom >= danger_y
        draw_brick(screen, brick, small_font, boff, danger, game.game_time,
                   game.freeze_timer > 0, brick.acid_t > 0,
                   game.reverse_timer > 0)

    # Field pickups
    for pu in game.pickups:
        rect = cell_rect(pu["col"], pu["row"], "square", off)
        draw_pickup_icon(screen, small_font, pu["type"], *rect.center)

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
        weight = game.wall_weight
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

    # Placed AoE pickups (stationary icons)
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
                surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(surf, (*wcolor, alpha), (r, r), r, 3)
                screen.blit(surf, (int(wave["x"]) - r, int(wave["y"]) - r))

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
        sc = MORTAR_STYLE.get(shell["type"], (TEXT_COLOR, "?"))[0]
        pygame.draw.circle(screen, sc, (int(x), int(y)), 6)
        # Trail
        if t > 0.05:
            t2 = t - 0.05
            x2 = sx + (tx - sx) * t2
            y2 = sy + (ty - sy) * t2 - arc_height * math.sin(t2 * math.pi)
            pygame.draw.line(screen, sc, (int(x2), int(y2)),
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
    if game.ammo_debt > 0:
        sub_parts.append(f"-{game.ammo_debt} skull")
    if sub_parts:
        fly_txt = small_font.render("  ".join(sub_parts), True, (130, 130, 160))
        screen.blit(fly_txt, (12 + 5 * 16 + 6, bullet_cy + 6))

    # Mortar ammo — one slot per type (right side), ring marks selection
    slot_w = 58
    mortar_start_x = WIDTH - len(MORTAR_TYPES) * slot_w + 14
    for i, mtype in enumerate(MORTAR_TYPES):
        mx = mortar_start_x + i * slot_w
        count = game.mortar_ammo[mtype]
        color, label = MORTAR_STYLE[mtype]
        if count <= 0:
            color = (60, 60, 75)
        pygame.draw.circle(screen, color, (mx, bullet_cy), 11)
        if i == game.mortar_sel:
            pygame.draw.circle(screen, TEXT_COLOR, (mx, bullet_cy), 14, 2)
        t = small_font.render(label, True, BG_COLOR)
        screen.blit(t, t.get_rect(center=(mx, bullet_cy)))
        cnt_color = TEXT_COLOR if count > 0 else (100, 100, 120)
        cnt = small_font.render(f"x{count}", True, cnt_color)
        screen.blit(cnt, (mx + 15, bullet_cy - 8))

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
        if game.new_best:
            new_txt = font.render("NEW BEST!", True, AMMO_COLOR)
            screen.blit(new_txt,
                        new_txt.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 40)))
        hint = small_font.render("Click to continue", True, (180, 180, 180))
        screen.blit(hint,
                    hint.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 70)))


def draw_menu(screen: pygame.Surface, font: pygame.font.Font,
              small_font: pygame.font.Font,
              highscore: int) -> tuple[pygame.Rect, pygame.Rect]:
    """Returns (play button rect, help button rect)."""
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

    # Help button
    help_rect = pygame.Rect(WIDTH // 2 - 60, HEIGHT // 2 + 44, 120, 36)
    pygame.draw.rect(screen, (45, 45, 70), help_rect, border_radius=8)
    pygame.draw.rect(screen, (150, 150, 180), help_rect, 2, border_radius=8)
    help_txt = small_font.render("HELP", True, TEXT_COLOR)
    screen.blit(help_txt, help_txt.get_rect(center=help_rect.center))

    if highscore > 0:
        hs_txt = small_font.render(f"Best: Wave {highscore}", True, (150, 150, 180))
        screen.blit(hs_txt,
                    hs_txt.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 106)))

    controls = [
        "Left click / hold — Fire gun",
        "Right click — Fire mortar",
        "Scroll / 1-4 — Select mortar type",
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
    screen.fill(BG_COLOR)

    title = font.render("PICKUPS", True, TEXT_COLOR)
    screen.blit(title, title.get_rect(center=(WIDTH // 2, 40)))

    icon_x, text_x = 40, 68
    header_color = (150, 150, 180)
    text_color = (200, 200, 215)
    y = 84

    def header(label: str):
        nonlocal y
        t = small_font.render(label, True, header_color)
        screen.blit(t, (24, y))
        y += 30

    def row(icon_fn, desc: str):
        nonlocal y
        icon_fn(y)
        t = small_font.render(desc, True, text_color)
        screen.blit(t, (text_x, y - 9))
        y += 30

    def pickup(ptype):
        return lambda ry: draw_pickup_icon(screen, small_font, ptype,
                                           icon_x, ry)

    header("FIELD PICKUPS — shoot to collect")
    row(pickup("ammo"), "Ammo — +1 gun ammo")
    row(pickup("mine"), f"Mine — +1 mortar mine (wave {UNLOCK['mines']}+)")
    row(pickup("wall"), f"Wall — +1 mortar wall (wave {UNLOCK['wall']}+)")
    row(pickup("bomb"), f"Bomb — +1 mortar bomb (wave {UNLOCK['bombs']}+)")
    row(pickup("fireball"),
        f"Fireball — next 5 shots pierce (wave {UNLOCK['fireball']}+)")
    row(pickup("acid"), f"Acid — +1 mortar acid (wave {UNLOCK['acid']}+)")
    row(pickup("homing"),
        f"Homing — next 5 shots steer (wave {UNLOCK['homing']}+)")

    y += 10
    header("AOE — shoot it, or it fires when a brick touches it")
    row(lambda ry: draw_freeze_icon(screen, icon_x, ry),
        f"Freeze — stops advance 5s (wave {UNLOCK['freeze']}+)")
    row(lambda ry: draw_reverse_icon(screen, icon_x, ry),
        f"Reverse — bricks retreat 3s (wave {UNLOCK['reverse']}+)")
    row(lambda ry: draw_lightning_icon(screen, icon_x, ry),
        f"Lightning — strikes 6 random bricks (wave {UNLOCK['lightning']}+)")
    row(lambda ry: draw_skull_icon(screen, icon_x, ry),
        "Skull — halves brick HP/shields AND your ammo")
    t = small_font.render("(appears in the bottom rows after 10 minutes)",
                          True, (130, 130, 160))
    screen.blit(t, (text_x, y - 6))
    y += 34

    header("MORTAR — right click, targets the crosshair")
    row(lambda ry: draw_pickup_icon(screen, small_font, "bomb", icon_x, ry),
        "Bomb — area damage, chains to other bombs")
    row(lambda ry: draw_pickup_icon(screen, small_font, "mine", icon_x, ry),
        "Mine — lands armed, explodes on brick contact")
    row(lambda ry: draw_pickup_icon(screen, small_font, "acid", icon_x, ry),
        "Acid — damage zone, ticks for 5s")
    row(lambda ry: draw_pickup_icon(screen, small_font, "wall", icon_x, ry),
        "Wall — barrier that holds bricks until overloaded")

    hint = small_font.render("Click or Esc to return", True, (180, 180, 180))
    screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT - 30)))
