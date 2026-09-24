# BricksRT

Real-time brick breaker with gun and mortar mechanics. Based on [Bricks](https://github.com/HaagenHu/Bricks).

![Gameplay and menu](docs/screenshot.png)

## Concept

Bricks advance continuously; the run ends when one reaches the bottom.
You steer a turret along the bottom and aim with the mouse:

- **Gun:** fires your pool of balls. They bounce around the field and
  come back off the bottom (after 1s, then reloading up to 10/s). The
  more balls ready, the wider each volley: 2 shots at 15, 3 at 30, 4 at 45
- **Shared ammo:** six types — Mine, Wall, Bomb, Tar, Acid, Homing —
  collected as pickups. Each unit either fires one **mortar** round at
  the crosshair or **loads the gun** with 5 special bullets (fire,
  acid burn, tar slow, sticky mine, wall stun, homing)
- **Field pickups:** shoot them to collect — extra balls, ammo units,
  and area effects (Freeze, Reverse, Lightning, Skull) that also fire
  when a brick touches them
- **Paddles** (wave 50+): deflectors that appear on their own for 6s;
  still, spinning, or turned by each hit
- **Bricks** unlock new shapes as the waves climb; from wave 60 some
  carry a **shield** that blocks hits on its glowing band (acid melts
  shields twice as fast)

## Controls

| Input | Action |
|---|---|
| Mouse | Aim |
| Left click / hold | Fire gun |
| Right click | Fire mortar |
| A / D | Move turret |
| Scroll / 1–6 | Select ammo type |
| R / Middle click | Load gun: 1 unit = 5 special bullets |
| Q | Panic mortar: one shell of every stocked type (no walls) at the lowest row |
| E | Panic gun: load one unit of every type |
| Space | Pause |
| M | Sound on / off |
| Esc | Menu |

## Graphics

Neon-vector look, all drawn in code — no image assets:

- **Glow:** additive glow on shots, shells, blasts, pickups, gun and
  crosshair; bricks get a halo in their HP color and a bevel
- **Motion:** shots leave fading trails; bricks flash on hits and shatter
  into shards on kills; blasts, wall breaks and skulls shake the field
- **Explosions:** white-hot core, shockwave ring, sparks and smoke
- **Zones:** bubbling acid, glossy tar, honeycomb energy walls, frost
  while frozen; lightning crackles and forks through its targets
- **Shields:** a pulsing energy band that thickens with strength,
  flashes on each absorbed hit and turns green under acid
- **Readability:** mortar rounds mark their landing footprint; bricks
  about to reach the death line flash white with a red glow
- **Gun and HUD:** recoiling turret tinted by the loaded ammo, a mortar
  reload ring on the crosshair, gradient HUD panels, nebula backdrop
- **Menu:** glowing title over falling, shattering demo bricks

See [CHANGELOG.md](CHANGELOG.md) for details.

## Sound

Procedural sound effects, synthesized at startup (no audio files):
kills, blasts, mortar launches and landings, pickups, area effects,
game over and new best. Frequent events are rate-limited so busy
moments don't turn into noise. **M** toggles sound.

## Status

Work in progress. Branched from the turn-based Bricks game.

## Requirements

- Python 3.10+
- pygame-ce (`pip install pygame-ce`)
- UI font: Bahnschrift (ships with Windows 10+); falls back to Arial

## Run

```
pip install -r requirements.txt
py main.py
```

Practice start for testing — jump to a wave with a matching arsenal
(the balls a perfect run would have collected by then on average, plus
3 of each unlocked ammo type); records no highscore:

```
py main.py --wave 100
```

## Tests

```
py tests/test_game.py
```
