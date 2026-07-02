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
Fires single projectiles from the barrel tip. Rapid fire with cooldown.

- Normal balls bounce off bricks, 1 damage per hit; the pool circulates
  (exit at bottom = ammo returns after a short reload delay, and the
  gun drifts toward the exit point)
- Volley scaling: surplus ammo converts to shots per trigger in a
  small spread — 2 at 15+ ammo, 3 at 30+, 4 at 45+. While firing, the
  size can grow if the pool grows (pickups) but never shrinks as it
  drains; it recomputes on release or an empty pool
- Loading (R): spends 1 unit of the selected ammo type for 5 special
  bullets, queued in firing order (repeat R stacks). The CENTER shot
  of each volley fires the next queued bullet, straight at the aim
  point; the rest of the volley stays normal

### Shared Ammo Inventory
One counter per type (pickups give +1 unit). Each unit fires one
mortar round (right click, 0.6s cooldown, arcs to the crosshair) OR
loads the gun with 5 special bullets (R). Selected with scroll or
keys 1-6; firing with an empty/incapable selection falls back to the
first stocked type.

| Type | Mortar round | Gun load (5 bullets) | Unlock |
|------|--------------|----------------------|--------|
| Mine | Lands armed, explodes on brick contact (chains) | Sticky charge: rides the first brick hit, blows after 1.5s | 10 |
| Wall | Barrier holding the field until overloaded | Full stop on hit brick, 2s | 20 |
| Bomb | Explodes at target, area damage, halves shields | Fire bullet: pierces through bricks, chips 1 shield per pass | 30 |
| Tar | Zone halving brick advance speed, 8s | +15% slow per hit, stacks to a stop, 3s from last hit | 40 |
| Acid | Area DoT zone, 5s — melts shields before hp | Acid DoT: 1/s for 3s, shield first | 60 |
| Homing | Rocket: flies to the brick nearest the gun and explodes on it | Shots steer toward the nearest brick, 10s | 100 |

- Panic mortar (Q): fires one shell of each stocked mortar-capable
  type (walls excluded) spread along the lowest occupied brick row,
  bypassing the cooldown; mines land one cell below the row; the
  crosshair snaps to the biggest brick on that row
- Panic gun (W): loads one unit of EVERY stocked gun-capable type
  into the gun queue at once

### AoE (Passive)
Field-wide effects triggered by shooting a field pickup (or when a brick
touches it).

| Type | Effect | Source |
|------|--------|--------|
| Freeze | Stops all brick advancement for 5 seconds | Pickup |
| Reverse | Bricks move upward for 3 seconds | Pickup |
| Lightning | Zaps 6 random bricks (wave/5 dmg) and stuns them 2s | Pickup (wave 90+) |
| Skull | Halves brick HP/shields AND total gun ammo (incl. in-flight); also permanently cuts new-brick spawn HP by half the current spawn HP (stacks per skull) | Spawns in bottom rows every 5 min after 10 min |

---

## Brick System

### Shapes
Reuse all shapes from Bricks:
- Square, Wide, Tall, Round, Diamond, Hexagon, Trapezoid, Triangle (4 orientations)

### Properties
- HP scales with game time / wave number; 5% of spawns have double HP
- Spawn HP = wave − skull cut: each skull permanently adds half the
  then-current spawn HP to the cut (e.g. skull at wave 110 → new
  bricks spawn at wave − 55)
- Shields (bottom protection)
- Merging (wave 70+): a spawning square can fuse with the square below it
  into a tall brick with combined HP
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

Clearing the board drops one random unlocked collectible pickup
(ammo or any inventory type, no AoE) in the upper rows as a reward.

| Pickup | Gives |
|--------|-------|
| Ammo | +1 normal gun ball |
| Mine / Wall / Bomb / Tar / Acid / Homing | +1 unit of shared ammo inventory |
| Freeze / Reverse / Lightning | Immediate AoE effect |

### Pickup Ideas (suggestions, not implemented)

Candidates for the wave 55-95 unlock gaps. The strongest ones deepen
the bounce economy (shot longevity / bounce density) rather than
adding raw damage.

| Idea | System | Effect | Notes |
|------|--------|--------|-------|
| Split shot | Gun charges | Next N shots split into 3 (±30°) on first brick hit | Bounce-volume multiplier; clones must NOT refund ammo on exit or the pool inflates |
| Rubber shot | Gun charges | No anti-bounce gravity, slight speed gain per bounce | Pure longevity buff; nearly free to build |
| Updraft | Mortar | Zone that deflects projectiles upward, back into the field | Terrain for your shots — mirror image of tar; extends shot lifetimes |
| Tesla pylon | Mortar | Zaps nearest brick every 1s for ~8s (light dmg + 1s stun) | Sustained positional lightning; reuses bolt + stun infra |
| Overcharge | AoE | Gun cooldown halved for ~6s | Stacks multiplicatively with volley — check it doesn't trivialize the fire-rate cap |
| Kill spark | AoE | For ~5s each brick kill emits a quarter-strength explosion | Chain-reaction payoff in dense low-HP fields |

Recommended first: Split shot + Updraft.

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
| Scroll / 1-6 | Select ammo type |
| R | Load gun: 1 unit of selected type = 5 special bullets (queues) |
| Q | Panic mortar: one shell of each stocked type (no walls) at the lowest brick row |
| W | Panic gun: load one unit of every gun-capable type |
| Space | Pause |
| Escape | Menu (saves highscore) |

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

## Sound (suggestion, not implemented)

Per-event audio would be white noise at this event density (volleys up
to 8 triggers/s x 4 shots, dozens of bouncing projectiles). Sound the
meaning, not the events:

| Tier | Events | Rule |
|------|--------|------|
| Always | Mortar launch/impact, pickup collected, AoE triggers (distinct voice each), wall placed/broken, game over, new best | Rare and meaningful — 1-3/s at peak |
| Rate-limited | Brick kills (not hits) | Short pop, max 1 per ~70ms; extras dropped or folded into one louder pop |
| Mostly silent | Gun fire, bounces, brick hits | One soft tick per trigger (not per volley shot) or a hum while held; wall/ceiling bounces silent; hit ticks only when in-flight count is low (mute above ~8) |

Implementation notes:
- `pygame.mixer.pre_init(44100, -16, 2, 256)` before `pygame.init()`
  for low latency so kills feel connected to the action
- Sounds can be generated procedurally with numpy at startup (short
  sine/noise envelopes) — no asset files, repo stays self-contained
- Rate limiter = dict of last-played timestamps checked before `.play()`
- Start with the "Always" tier + rate-limited kills (~10 tiny sounds),
  playtest density before adding fire/bounce ticks

---

## Graphics improvements (suggestions)

Juice over art assets — ranked by impact per effort:

1. Hit flash + kill particles: brick flashes white ~50ms on hit; on
   death bursts into 8-12 shards of its own color (particle list like
   `explosions`)
2. Projectile trails: last ~8 positions as shrinking, fading circles —
   makes ricochet paths readable (core mechanic!)
3. Screen shake: decaying random offset on bomb/wall break/skull
4. Additive glow: `BLEND_ADD` over pre-rendered radial-gradient
   sprites for projectiles/explosions/waves — neon look on dark bg
5. Brick depth + damage states: dark bottom-right edge, light top
   edge; cracks below ~30% of spawn HP (needs `max_hp` on Brick)
6. Spawn/death animation — **implemented**: rows slide down from
   behind the HUD; killed bricks shrink out over ~0.12s
7. Ambient depth — **implemented**: three parallax star layers drift
   slowly down the field (game-time driven, freezes on pause), and a
   red danger gradient over the last three rows fades in as the lowest
   brick approaches the death line (full strength at the line)

Performance: fine at 480x720/60 in pygame-ce if glow sprites are
pre-rendered once (never build per-pixel alpha surfaces per frame).

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

## Resolved Decisions

- Gun projectiles exit at the bottom and their ammo returns to the pool
  after a 1s reload delay — max projectiles on screen equals the ammo pool.
- Mortar shells fly a parabolic arc (0.2-0.6s depending on distance).
- Ammo comes from pickups plus returned shots; no passive regeneration.
- Pause freezes everything (timers, projectiles, advancement).

## Code Layout

| Module | Contents |
|--------|----------|
| `game.py` | Constants, `Brick`/`Projectile`/`Game`, all logic — no display |
| `render.py` | Colors and all drawing functions |
| `main.py` | Event loop and input handling |
| `tests/test_game.py` | Logic tests (run with `py -m pytest` or directly) |
