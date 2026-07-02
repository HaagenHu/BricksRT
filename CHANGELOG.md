# Changelog

## v0.3.2 — Mortar order (2026-07-02)

- Mortar types reordered to match unlock sequence (mine, wall, bomb,
  tar, acid) — HUD slots, keys 1-5, cycling, and help screen follow
- Pickup unlocks doubled: one new type every 10th wave — mine 10,
  wall 20, bomb 30, tar 40, fireball 50, acid 60, freeze 70,
  reverse 80, lightning 90, homing 100

## v0.3.1 — Lightning rebalance, volley scaling (2026-07-02)

- Pickup unlocks respread: one new type every 5th wave — mines 5,
  wall 10, bombs 15, tar 20, fireball 25, acid 30, freeze 35,
  reverse 40, lightning 45, homing 50 (previously bunched in waves 3-20)
- **Tar mortar** (wave 20+): fifth mortar type — lands as a sticky zone
  that halves brick advance speed inside it for 8s; stacks bricks
  behind slowed ones; synergizes with acid (more ticks in the zone)
- Volley scaling: big ammo pools fire multiple shots per trigger in a
  small spread (2 at 15+, 3 at 30+, 4 at 45+ ammo) — surplus ammo now
  converts to bounce volume instead of sitting idle; HUD shows the
  multiplier next to the ammo count

- Lightning nerfed: strikes now deal light damage (wave/5 instead of
  full wave) and stun struck bricks for 1s — stunned bricks stop
  advancing (yellow frame) while the rest of the field keeps moving
- Bricks catching up with a stunned brick stack on top of it (same
  behavior as stacking on wall-held bricks) instead of overlapping
- Mortar HUD highlight follows the ammo: it moves to the next stocked
  type when the selected one runs out, and syncs when firing falls
  back from an empty selection

## v0.3.0 — Lightning, Skull, Merging (2026-07-02)

- **Lightning** (pickup, wave 20+): chain-strikes 6 random bricks for
  wave-level damage each, with jagged bolt visuals
- **Skull**: spawns in the bottom rows every 5 minutes after 10 minutes
  of play; triggering it halves every brick's HP and shields — but also
  your total gun ammo (including reloading and in-flight shots, which
  are consumed as they return)
- **Merging** (wave 70+): a spawning square brick can fuse with the
  square directly below into a tall brick with combined HP
- AoE trigger handling (ball hit / brick contact) unified across
  freeze, reverse, lightning, and skull
- **Help screen**: HELP button on the menu opens a legend of every
  pickup icon with its effect and unlock wave

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
