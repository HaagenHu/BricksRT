# BricksRT

Real-time brick breaker with gun and mortar mechanics. Based on [Bricks](https://github.com/HaagenHu/Bricks).

## Concept

Bricks advance slowly in real-time. Player has a crosshair and two weapons:

- **Gun (Left mouse):** Fires projectiles — Fireball, Homing
- **Mortar (Right mouse):** Launches area weapons — Bomb, Mine, Acid, Wall
  (select type with scroll wheel or 1-4)
- **AoE (Pickup):** Field effects — Freeze, Reverse, Lightning, Skull

## Status

Work in progress. Branched from the turn-based Bricks game.

## Requirements

- Python 3.10+
- pygame-ce (`pip install pygame-ce`)

## Run

```
pip install -r requirements.txt
py main.py
```

## Tests

```
py tests/test_game.py
```
