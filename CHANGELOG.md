# Changelog

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
