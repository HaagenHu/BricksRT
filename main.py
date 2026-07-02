"""BricksRT — Real-time brick breaker with continuous advancement."""

import pygame

from game import FPS, HEIGHT, WIDTH, Game
from render import draw_game, draw_menu

MORTAR_KEYS = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3}


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
        # Clamp dt so frame stutter can't tunnel projectiles through bricks
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30)

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

            if event.type == pygame.MOUSEWHEEL:
                if game.phase == "playing" and event.y != 0:
                    game.cycle_mortar(-1 if event.y > 0 else 1)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    if game.phase == "playing":
                        game.phase = "paused"
                    elif game.phase == "paused":
                        game.phase = "playing"
                if event.key in MORTAR_KEYS and game.phase == "playing":
                    game.select_mortar(MORTAR_KEYS[event.key])
                if event.key == pygame.K_ESCAPE:
                    if game.phase in ("playing", "paused"):
                        game.save_if_record()
                        game.phase = "menu"

        mouse_pos = pygame.mouse.get_pos()

        if game.phase == "menu":
            play_rect = draw_menu(screen, font, small_font, game.highscore)
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
