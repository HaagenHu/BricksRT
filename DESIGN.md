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
  (exit at bottom = ammo returns after a 1s reload delay, then feeds
  back one ball at a time at up to 10/s, and the gun drifts toward the
  exit point). The feeder caps sustained fire, so a big pool is a
  burst reserve rather than endless fire
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
| Mine | Lands armed, explodes on brick contact (chains) | Sticky charge: rides the first brick hit, blows after 1.5s; the ball drops as a spent shell | 10 |
| Wall | Barrier holding the field until overloaded | Full stop on hit brick, 2s | 20 |
| Bomb | Explodes at target, area damage, halves shields | Fire bullet: pierces through bricks, chips 1 shield per pass | 30 |
| Tar | Zone halving brick advance speed, 8s | +15% slow per hit, stacks to a stop, 3s from last hit | 40 |
| Acid | Area DoT zone, 5s — melts shields before hp, at 2x | Acid burn: 2/s for 3s, shield first at 2x (shield glows green); the ball drops as a spent shell | 60 |
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
- Shields (bottom protection): a bounce hits the shield if it lands
  on a downward-facing face, or within 9px of the corners where the
  band wraps (all shapes but round and upward triangles) — the
  drawn band is exactly the protected area
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

### Deflectors

**Status:** the **paddle** is implemented (Unreleased) as a random
field appearance, not a mortar type: from wave 50, 20% chance per new
wave, max 2, 6s, random tilt up to 60 deg, kinds still 40% / spin
(60 deg/s) 30% / kick (15 deg per hit) 30% — continuous spin was kept
after all: a 4x volley spread is already about as random. The rest of
this section is the original proposal.

Stationary objects that change a ball's direction or position — a
generalization of Updraft. They sit in the bounce economy: since the
reload feeder (v0.6.0) caps sustained fire at ~10 balls/s, damage
comes from how long each ball stays in play, so steering balls back
into the bricks is strong without adding raw damage.

| Variant | Behavior | Verdict |
|---------|----------|---------|
| Paddle, still | Straight line; mirror bounce (same angle out) | **Build first** — readable, rewards bank shots; reuses the brick/wall reflection code |
| Paddle, rotates on impact | Each hit turns it a few degrees | Good follow-up: a volley fans out across the bricks |
| Paddle, rotating continuously | Spins on its own | Skip — the bounce becomes luck instead of aim |
| V-shape | Two joined paddles | Risky: balls can get trapped inside the V; adds little over a tilted line |
| Portal pair | Enter one, exit the other, velocity kept | **Build second** — most novel; bottom-to-top catches balls about to leave. Needs a limit (below) |
| Black hole | Gravity well bends passing shots | Later / rare — best visuals, hardest to tune (orbits, unpredictable paths) |

Rules:

- **Lifetime**: ~6s (in line with acid 5s / tar 8s — 3s is barely two
  field crossings at 600 px/s), or a charge count (e.g. 15
  deflections), which scales fairly with volley size
- **Overrun**: a brick touching it destroys it (visible shatter), like
  placed mines and AoE pickups
- **Loops**: each deflector hit counts toward the ball's `border_hits`,
  so the anti-loop gravity still kicks in; portals get a per-ball
  cooldown (no ping-pong); a black hole caps how far it can turn a
  shot
- **Portal limit**: without one, bottom-to-top portals keep balls up
  forever and make the reload feeder irrelevant — use a charge count,
  or only take balls moving downward
- **Who it affects**: normal, fire and homing balls deflect; spent
  shells (acid/mine) pass straight through

Open question — **delivery**:

- **Mortar ammo type** (lands at the crosshair): most skill, sits next
  to Wall; the paddle's angle can come from the aim direction
- **Field pickup** (spawns among bricks, activates when shot, like
  freeze/lightning): random, no aiming

Proposed first version: the still paddle as a mortar type, angle from
the aim at launch, ~6s or ~15 hits, shatters when overrun; neon
visuals + a cue. Portal pair next, with a charge limit.

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

## Sound

**Status (v0.5.1):** the "Always" and "Rate-limited" tiers are
implemented in `sound.py` (15 cues; blasts are rate-limited too). The
"Mostly silent" tier is still silent — playtest before adding ticks.
Deviations from the notes below: synthesis is plain Python (no numpy
dependency) at 22050 Hz with a 512-sample buffer, and the game logic
only queues cue names (`Game.drain_events`), keeping `game.py`
audio-free.

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

1. Hit flash + kill particles — **implemented**: brick flashes white
   60ms on hit; on death it pops white and bursts into 8-12 spinning
   shards of its own color (`Game.shards`, own RNG)
2. Projectile trails — **implemented**: last 8 positions as a tapering,
   fading streak — makes ricochet paths readable (core mechanic!)
3. Screen shake — **implemented**: trauma (0..1) added by blasts, wall
   breaks and skulls, drained over time; the field (not HUD, gun or
   crosshair) scrolls by trauma^2 x 10px
4. Additive glow — **implemented**: `BLEND_ADD` over cached
   radial-gradient sprites for projectiles/shells/explosions/pickups;
   bricks get a blurred HP-color halo pass plus a light rim
5. Brick depth — **implemented**: bevel lit from the top-left on every
   shape. Damage cracks were tried and dropped (looked noisy)
8. Layered explosions — **implemented**: white-hot core, fading glow,
   shockwave ring, spark streaks and smoke puffs
9. Mortar landing reticle — **implemented**: the round's footprint at
   the target (dashed line for walls) plus a ring closing in on landing
10. Zone textures — **implemented**: acid bubbles, glossy wobbling tar,
    honeycomb energy walls (flicker rises with load), freeze wash +
    frost glints
11. Gun turret + crosshair — **implemented**: recoiling barrel, muzzle
    flash, loaded-ammo tint; crosshair keeps its azure but gains a
    mortar-type pip and reload ring
12. Backdrop, HUD, typeface, menu — **implemented**: nebula + scrolling
    dot grid; gradient HUD panels, labeled values, badge timers, inset
    ammo slots; Bahnschrift (system font, no bundled asset); glowing
    hue-cycling title over shattering demo bricks, hover-lit buttons
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
