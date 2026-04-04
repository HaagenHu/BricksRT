# BricksRT — Design Document

## Overview

Real-time brick breaker where bricks advance continuously. Player uses a crosshair to aim two weapon types: a gun (left mouse) and mortar (right mouse). Powerups are categorized into weapon types rather than field pickups.

Based on the turn-based [Bricks](https://github.com/HaagenHu/Bricks) game, reusing brick shapes, collision physics, and visual effects.

---

## Core Loop

1. Bricks advance slowly downward in real-time (pixels per second, not per-round)
2. New brick rows spawn at the top at regular intervals
3. Player aims with crosshair (always visible) and fires weapons
4. Game over when any brick reaches the bottom

**Key difference from Bricks:** No turns. No "fire all balls". Continuous action.

---

## Weapons

### Gun (Left Mouse)
Fires single projectiles from the bottom center. Rapid fire with cooldown.

| Ammo Type | Effect | Source |
|-----------|--------|--------|
| Normal | Bounces off bricks, 1 damage per hit | Default, infinite |
| Fireball | Passes through bricks, 1 damage each | Pickup |
| Homing | Gently steers toward nearest brick | Pickup |

- Ammo is shared pool (like ball count in Bricks)
- Fireball/homing are temporary upgrades applied to next N shots
- Projectiles still bounce off walls and ceiling
- Projectile exits at bottom = lost (no return)

### Mortar (Right Mouse)
Fires arcing/direct projectile to crosshair position. Slower cooldown, limited ammo.

| Ammo Type | Effect | Source |
|-----------|--------|--------|
| Bomb | Explodes at target, area damage | Pickup |
| Acid | Area DoT at target position (10s, radius 3) | Pickup |
| Wall | Places energy barrier blocking brick column | Pickup |

- Mortar ammo is collected, not infinite
- Mortar fires TO the crosshair position (targeted, not bouncing)
- Explosion/effect happens at impact point

### AoE (Passive)
Field-wide effects triggered by pickups.

| Type | Effect | Source |
|------|--------|--------|
| Freeze | Stops all brick advancement for N seconds | Pickup |
| Lightning | Chain strikes on random bricks | Pickup |
| Skull | Halves everything (at high levels) | Spawns at intervals |

---

## Brick System

### Shapes
Reuse all shapes from Bricks:
- Square, Wide, Tall, Round, Diamond, Hexagon, Trapezoid, Triangle (4 orientations)

### Properties
- HP scales with game time / wave number
- Shields (bottom protection)
- Merging (tall bricks from overlapping spawns)
- Rainbow color gradient by HP

### Advancement
- Bricks move downward at a constant speed (e.g. 5 pixels/second)
- Speed increases gradually over time
- Freeze stops advancement temporarily
- Wall blocker stops a column

---

## Spawning

### Brick Waves
- New row spawns every N seconds (e.g. every 10 seconds)
- 3-6 bricks per row (random columns)
- HP = wave number (scaled by difficulty)
- Shapes unlock progressively (same gates as Bricks)

### Pickups
Pickups spawn among bricks (like +ball in Bricks). Player must shoot them to collect.

| Pickup | Gives |
|--------|-------|
| Ammo Crate | +N normal ammo |
| Fireball | Next N shots are fireballs |
| Homing | Next N shots are homing |
| Bomb x1 | +1 mortar bomb |
| Acid x1 | +1 mortar acid |
| Wall x1 | +1 mortar wall |
| Freeze | Immediate freeze effect |
| Lightning | Immediate lightning strikes |

---

## HUD

```
[ Wave: 15 ]  [ Best: 42 ]  [ Ammo: 87 ]
|                                        |
|          GAME AREA                     |
|          (bricks + projectiles)        |
|                                        |
|  [Bomb: 2] [Acid: 1] [Wall: 0]        |
|            [+]  crosshair              |
```

- Top: wave number, highscore, gun ammo count
- Bottom: mortar ammo counts
- Crosshair: always visible, follows mouse
- Mortar selection: cycle with scroll wheel or number keys

---

## Difficulty Scaling

| Time | Change |
|------|--------|
| 0-60s | Squares only, slow advance, frequent ammo |
| 1-3 min | New shapes, moderate advance |
| 3-5 min | Shields appear, less ammo |
| 5-10 min | All shapes, faster advance |
| 10+ min | Skull spawns periodically, max speed |

Advance speed: `base_speed + time_elapsed * 0.1` (capped)

---

## Controls

| Input | Action |
|-------|--------|
| Mouse move | Aim crosshair |
| Left click | Fire gun |
| Left hold | Rapid fire gun |
| Right click | Fire mortar at crosshair |
| Scroll / 1-3 | Cycle mortar ammo type |
| Space | Pause |
| Escape | Menu |

---

## Visual Effects (Reuse from Bricks)

- Freeze wave (expanding ice circle)
- Skull wave (expanding purple circle)
- Lightning bolts (jagged lines between targets)
- Laser beams (bright line with glow)
- Explosions (fading circles)
- Acid overlay (green tint on affected bricks)
- Wall barrier (glowing horizontal line)
- Fireball glow (orange trail on projectile)
- Homing trail (green projectile)
- Danger flash (pulsing red on low bricks)

---

## Reusable Code from Bricks

| Module | Status |
|--------|--------|
| Brick shapes + drawing | Direct reuse |
| Collision (rect, round, polygon) | Direct reuse |
| PU effects (explode, lightning, acid, freeze) | Adapt triggers |
| Visual effects (waves, bolts, beams) | Direct reuse |
| Color system (rainbow HP) | Direct reuse |
| Highscore persistence | Direct reuse |
| Menu system | Adapt (fewer modes) |
| Help pages | Rewrite for new controls |
| Ball/projectile physics | Adapt (one-way, no return) |
| Turn-based game loop | Replace entirely |
| Aim line / crosshair | Adapt (always visible) |

---

## Implementation Plan

### Phase 1 — Core Loop
1. Replace turn-based loop with real-time loop
2. Continuous brick advancement (pixels/sec)
3. Wave spawning on timer
4. Gun: left click fires single projectile
5. Projectile physics (bounce walls/ceiling, exit at bottom)
6. Basic collision with bricks

### Phase 2 — Weapons
7. Gun cooldown and rapid fire
8. Mortar: right click fires to crosshair position
9. Bomb explosion at mortar impact
10. Ammo system (gun ammo + mortar ammo)
11. Ammo pickups on field

### Phase 3 — Powerups
12. Fireball gun ammo
13. Homing gun ammo
14. Acid mortar
15. Wall mortar
16. Freeze AoE
17. Lightning AoE

### Phase 4 — Polish
18. HUD (ammo counts, wave, mortar selector)
19. Difficulty scaling
20. Progressive unlocks
21. Skull at high levels
22. Help screen
23. Highscores

---

## Open Questions

- Should gun projectiles return (bounce off bottom) or exit?
- Mortar arc animation or instant impact?
- Max projectiles on screen at once?
- Ammo regeneration or pickup-only?
- Pause behavior — freeze everything or menu overlay?
