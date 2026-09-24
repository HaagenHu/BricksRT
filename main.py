"""BricksRT — Real-time brick breaker with continuous advancement.

    py main.py             normal game
    py main.py --wave 60   practice start at wave 60 (testing; no highscore)
"""

import argparse

import pygame

from game import FPS, HEIGHT, WIDTH, Game
import sound
from render import UI_FONT, draw_game, draw_help, draw_menu

AMMO_KEYS = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3,
             pygame.K_5: 4, pygame.K_6: 5}


def main(start_wave: int = 1):
    sound.pre_init()  # mixer settings must precede pygame.init()
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("BricksRT")
    clock = pygame.time.Clock()

    # Bahnschrift (DIN-style, ships with Windows 10+) with Arial fallback
    font = pygame.font.SysFont(UI_FONT, 22, bold=True)
    small_font = pygame.font.SysFont(UI_FONT, 16, bold=True)

    sfx = sound.Sounds()  # synthesizes the cues once, at startup
    game = Game()
    play_rect: pygame.Rect | None = None
    help_rect: pygame.Rect | None = None
    show_help = False
    mouse_held = False

    running = True
    while running:
        # Clamp dt so frame stutter can't tunnel projectiles through bricks
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_held = True
                mx, my = event.pos
                if game.phase == "menu":
                    if show_help:
                        show_help = False
                    elif play_rect and play_rect.collidepoint(mx, my):
                        game.start(start_wave)
                    elif help_rect and help_rect.collidepoint(mx, my):
                        show_help = True
                elif game.phase == "gameover":
                    game.phase = "menu"

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if game.phase == "playing":
                    game.fire_mortar()

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                mouse_held = False
                game.stop_fire()

            if event.type == pygame.MOUSEWHEEL:
                if game.phase == "playing" and event.y != 0:
                    game.cycle_mortar(-1 if event.y > 0 else 1)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    if game.phase == "playing":
                        game.phase = "paused"
                    elif game.phase == "paused":
                        game.phase = "playing"
                if event.key == pygame.K_m:
                    sfx.toggle_mute()
                if event.key in AMMO_KEYS and game.phase == "playing":
                    game.select_mortar(AMMO_KEYS[event.key])
                if event.key == pygame.K_r and game.phase == "playing":
                    game.load_gun()
                if event.key == pygame.K_w and game.phase == "playing":
                    game.panic_gun()
                if event.key == pygame.K_q and game.phase == "playing":
                    if game.panic():
                        # Panic snaps the crosshair to the biggest brick
                        # on the lowest row — move the mouse along so
                        # the next frame doesn't snap it back
                        pygame.mouse.set_pos(game.crosshair)
                if event.key == pygame.K_ESCAPE:
                    if show_help:
                        show_help = False
                    elif game.phase in ("playing", "paused"):
                        game.save_if_record()
                        game.phase = "menu"

        mouse_pos = pygame.mouse.get_pos()

        # Hide the system cursor only while the crosshair is shown. Set
        # every frame before the menu branch: Esc from play goes straight
        # to the menu, which must bring the cursor back
        pygame.mouse.set_visible(game.phase != "playing")

        if game.phase == "menu":
            if show_help:
                draw_help(screen, font, small_font)
            else:
                play_rect, help_rect = draw_menu(screen, font, small_font,
                                                 game.highscore, start_wave)
            pygame.display.flip()
            continue

        # Update aim and fire while playing
        if game.phase == "playing":
            game.update_aim(mouse_pos)
            if mouse_held:
                game.fire_gun()
            game.update(dt)
        # Cues from this frame's input (mortar fire) and update
        sfx.play_events(game.drain_events())

        draw_game(screen, game, font, small_font, muted=sfx.muted)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BricksRT")
    parser.add_argument("--wave", type=int, default=1, metavar="N",
                        help="practice start at wave N with a matching "
                             "arsenal (for testing; records no highscore)")
    args = parser.parse_args()
    main(max(1, args.wave))
