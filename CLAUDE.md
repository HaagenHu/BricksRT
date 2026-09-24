# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

BricksRT is a real-time brick breaker in Python + pygame-ce (see README.md
for gameplay and controls, DESIGN.md for the full design and rules,
CHANGELOG.md for per-version detail).

## Commands

The project venv is `.venv` (Windows); use its interpreter directly.

```
.\.venv\Scripts\python.exe main.py              # run the game
.\.venv\Scripts\python.exe main.py --wave 100   # practice start at a wave (no highscore saved)
.\.venv\Scripts\python.exe tests\test_game.py   # run all tests
```

pytest is not installed; the test file has its own runner (`_run_all`
auto-discovers every `test_*` function). Run a single test with:

```
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'tests'); import test_game as t; t.test_kick_paddle_tips_hold()"
```

Tests force `SDL_VIDEODRIVER`/`SDL_AUDIODRIVER=dummy` and redirect
`HIGHSCORE_FILE` to a temp file. There is no build or lint step.

## Architecture

Four modules with a strict split:

- **game.py** — all game state and rules, no display or audio. `Game`
  holds bricks, projectiles, pickups, placed walls/zones, paddles and
  ammo; `Game.update(dt)` advances one frame. Tuning lives in module
  constants at the top (speeds, timings, `UNLOCK` wave thresholds per
  feature). Instead of playing sounds, logic queues cue names with
  `Game._emit(name)`; the frontend pulls them via `drain_events()`.
- **render.py** — all drawing (neon glow via cached `BLEND_ADD`
  sprites, HUD, menu, help screens). Reads `Game` state; never mutates
  gameplay.
- **sound.py** — cues synthesized procedurally at startup in plain
  Python (no numpy, no audio files), with rate limiting for frequent
  events.
- **main.py** — event loop and input: maps keys/mouse to `Game`
  methods, then `sfx.play_events(game.drain_events())` and `draw_game`.

Cross-module conventions worth knowing:

- **Two RNGs**: gameplay uses `random`; purely visual randomness
  (shards, sparks, lightning seeds) uses `game._FX_RNG` so effects never
  change gameplay and tests stay deterministic under `random.seed`.
- **Collisions** for a live shot run in `Game._collide_projectile`,
  walls first (static full-width lines), then bricks, pickups, paddles,
  placed AoE. Walls and paddles are swept along `Projectile.prev ->
  pos` so fast steps can't tunnel; any bounce that moves the ball must
  reset `prev` to the new position.
- **Shield geometry is shared**: `shape_points`, `brick_outline`,
  `down_faces`, `shield_wraps`, `shield_half` and the `SHIELD_*`
  constants in game.py define both what the shield blocks
  (`_shield_absorbs`) and the band render.py draws. Change them in one
  place so the drawn band stays equal to the protected area.
- Timing is in seconds (`dt`), speeds in px/s, so behavior is
  frame-rate independent; tests often step `1/60` and `1/30`.

## Conventions

- Release commits are prefixed `vX.Y.Z:` and get an annotated git tag;
  each version has a CHANGELOG.md section. The version is not stored
  in code.
- `docs/CODE_REVIEW.md` tracks review findings with an Open/Fixed
  status table; update it when fixing one.
- The UI font is Bahnschrift (falls back to Arial); use render.py's
  `_ui_font` cache, and `_blit_centered` when text must be centered on
  its glyphs.
