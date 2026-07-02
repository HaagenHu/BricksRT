# Changelog

## v0.4.0 — Unified ammo, panic buttons, juice (2026-07-02)

### Unified ammo system

- **One shared ammo inventory** replaces separate mortar ammo and gun
  charges: each pickup gives 1 unit; a unit fires one mortar round
  (right click) OR loads the gun with 5 special bullets (R, queued in
  firing order — repeat to stack). Scroll / keys 1-6 select the type
- Dual-use effects, matched by theme: Wall = barrier / full 2s stop on
  the hit brick; Bomb = area blast / piercing fire bullet (the old
  fireball); Tar = slow zone / +15% slow per hit (stacks to a stop, 3s
  from last hit); Acid = damage zone / melt DoT (1 dmg/s, 3s from last
  hit); Homing = rocket that flies to the brick nearest the gun and
  explodes / steering shots; Mine = contact trap / sticky charge that
  rides the first brick hit and blows after 1.5s (the ball bounces
  on) — every type is dual-use
- The center shot of each volley fires the next queued special bullet,
  straight at the aim point; the rest of the volley stays normal
- Fireball and tar-shot pickups are gone (folded into bomb and tar);
  the HUD shows six inventory slots and the gun's queued load
- **Panic gun** (W): loads one unit of every stocked gun-capable type
  into the gun queue at once — the mortar panic stays on Q
- Shields have counterplay beyond from-below bounces: explosions
  (bomb/mine/rocket) halve them, acid melts them (zone and DoT ticks
  strip shield points before hp), and fire bullets chip 1 shield per
  pass-through

### Gameplay

- New brick rows slide down from behind the top HUD (0.2s) instead of
  popping in; killed bricks shrink out over 0.12s in their own shape
  and color
- Starry background: three parallax layers of dim stars drift slowly
  down the play field (frozen while paused) and across the menu and
  help screens
- 5% of spawning bricks have double HP (stacks with the wide-brick
  doubling)
- Shots now launch from the gun's barrel tip instead of its base
- **Panic button** (Q): fires one shell of each stocked mortar type
  (walls excluded) spread along the lowest occupied brick row,
  bypassing the mortar cooldown; mines land a cell below the row; the
  crosshair (and mouse) snap to the biggest brick on that row
- Red danger gradient over the last three rows fades in as the lowest
  brick approaches the death line (completes ambient depth)
- Skull hit feedback: each brick flashes purple-white for 0.3s as the
  ring sweeps over it, and the gun-ammo count pulses purple for 1.5s
  after the ammo cut
- Lightning stun doubled to 2s
- Clearing the board drops a random unlocked pickup in the upper rows
  as a reward
- Crosshair is now azure blue with a dark outline instead of thin gray
  lines — readable over bright bricks, explosions, and text
- Recolored near-duplicate pickups: ammo is gold (matches the HUD
  ammo bullets, no longer green like homing), mines are steel with a
  red ring (no longer red like bombs) — placed mines match
- Help screen: one AMMO list with each type's mortar and gun effect
  plus unlock wave on a single line, and the AoE legend
- Fixed bricks jumping forward when a mortar wall broke or expired:
  the wall's hold-back now converts to lag, so bricks resume advancing
  from where they stopped at the wall
- Skull reset is now permanent on the supply side too: each skull adds
  half the current spawn HP to a lasting deduction on new-brick HP
  (skull at wave 110 → new bricks spawn at wave − 55; stacks per
  skull), applied to wave spawns and blocked-column HP alike
- Menu controls list updated (1-6, R, panic keys) — it still said 1-4
- Grazing shots no longer slide along the screen borders: bounces off
  the side walls and ceiling leave at a minimum 8° angle
- Fixed shots sticking to a mortar wall: a grazing hit used to
  re-bounce every frame (flickering across the line and chipping the
  wall's capacity each frame); now it bounces once, away, at the same
  minimum angle
- DESIGN.md: added suggestion sections for new pickups, sound design,
  and graphics improvements
- Volley size locks while the trigger is held: the burst keeps its
  shot count until you release or the pool empties, instead of
  stepping down mid-burst as ammo drains — but it can still step up
  if a pickup grows the pool mid-fire
- Fixed hexagon shield drawn along the top edges instead of the bottom
- Fixed stale volley lock: a skull emptying the pool mid-hold no longer
  leaves the old burst size active when reloaded shots return
- Fixed wave-70+ merge replaying the slide-in on the whole tall brick,
  which made the absorbed on-screen brick visibly jump up a cell
- Fixed death ghosts of bricks killed during the slide-in appearing at
  the logical cell (up to one cell below where the brick was drawn)

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
