# Changelog

## v0.2.0 — Physics fixes, mortar selection, restructure (2026-07-02)

### Gameplay
- Mortar now has a 0.6s cooldown and per-type ammo selection
  (scroll wheel / keys 1-4); firing an empty type falls back to
  the first type with ammo
- Highscore is saved when quitting a run with Esc, not only on game over

### Fixes
- Physics are frame-rate independent: projectile speed, homing steer,
  and anti-bounce gravity now scale with frame time; dt is clamped so
  stutter can't tunnel projectiles through bricks
- Wide bricks can no longer spawn overlapping a surviving row-0 brick
- "NEW BEST!" no longer shows when merely tying the old record
- Menu no longer re-reads highscores.json from disk every frame

### Internal
- Split into modules: `game.py` (logic), `render.py` (drawing), `main.py` (loop)
- Bricks are a dataclass instead of raw dicts
- Seven per-type pickup lists unified into one pickup system
- Added logic test suite (`tests/test_game.py`) and `requirements.txt`
- Removed unused `merging` unlock entry

## v0.1.0 — Real-time conversion (2026-04-07)

Initial real-time version, converted from the turn-based [Bricks](https://github.com/HaagenHu/Bricks) game.

### Core changes
- Replaced turn-based loop with continuous real-time gameplay
- Bricks advance downward in real-time (speed increases over time)
- New brick rows spawn on a timer instead of per-turn

### Weapons
- **Gun** (left click): rapid-fire projectiles from bottom center with cooldown and reload
- **Mortar** (right click): targeted projectile to crosshair position
- Ammo types: normal, fireball (pass-through), homing (steers toward bricks)
- Mortar types: bomb (area explosion), acid (area DoT), wall (column blocker)

### Pickups & effects
- Mines, freeze, reverse, fireball, homing, bomb, acid, wall pickups
- Freeze stops brick advancement temporarily
- Reverse pushes bricks upward temporarily

### HUD
- Gun ammo displayed left, mortar ammo right
- Gun position indicator at bottom center
- Wave counter, highscore, mortar selector

### Progressive unlocks
- Mines (wave 3), wall (3), bombs (5), fireball (7), acid (8)
- Freeze/reverse (10), homing (11), round/diamond shapes (15)
- Hexagon/trapezoid/wide shapes (30)
