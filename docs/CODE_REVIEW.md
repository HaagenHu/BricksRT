# Code Review — v0.6.0 → v0.7.0

Reviewed 2026-09-24. Scope: the code changes in `v0.6.0...v0.7.0`
(`game.py`, `render.py`, `main.py`, `sound.py`) — paddles, A/D turret
movement, the swept wall fix, four-way trapezoids, half/wrapped shield
bands, HP-number centroids. Docs-only commits were not reviewed.

Method: line-by-line diff read, removed-behavior audit, caller/callee
tracing, plus reuse / simplification / efficiency passes. The two top
findings were confirmed with headless simulations (below).

## Summary

| # | Severity | Area | Finding | Status |
|---|----------|------|---------|--------|
| 1 | High | Walls | Bricks resting on a wall get hit *through* it | Fixed |
| 2 | High | Paddles | Kick paddles let tip hits pass through | Fixed |
| 3 | Medium | Collisions | Swept checks use a stale `prev` after a relocation | Fixed |
| 4 | Medium | Paddles | Overrun test uses the full cell, not the brick's shape | Open |
| 5 | Low | Paddles | Spawn ignores walls, pickups, AoE icons, mines | Open |
| 6 | Low | Render | Paddle help icon doesn't use the `_bar` helper | Open |
| 7 | Low | Docs | `panic_gun` docstring still says W | Open |
| 8 | Low | Perf | Overrun check rebuilds every brick rect per frame | Open |

## Findings

### 1. Bricks resting on a wall get hit through it — High

`game.py:762` — in the projectile loop `_collide_bricks` runs before
`_collide_walls`.

Bricks pinned by a wall sit with their bottom on the wall line. A ball
rising toward the wall enters the brick's expanded rect in the same
10 px step, so the brick collision reflects it (and damages the brick)
first; `_collide_walls` then sees a ball moving *down* that came from
below and does nothing. To the player the ball "passes through" the
wall, and the wall no longer shields the bricks it holds — likely what
was still being seen after the v0.7.0 leak fix.

**Evidence:** 40 shots rising into a wall with a brick resting on it:
the brick was damaged 35/40 times, the wall chipped only 5/40.

**Fix:** resolve walls (static, full-width geometry) before brick
collisions in the projectile loop.

**Fixed:** the per-shot collisions moved into `_collide_projectile`,
walls first. `test_wall_shields_brick_resting_on_it` fails on the old
order and passes now (0/40 brick hits).

### 2. Kick paddles let tip hits pass through — High

`game.py:1522` — a kick paddle turns 15° right after a bounce.

The ball is left `r + 1` = 6 px off the line, then the line rotates
about the paddle's center. At |t| > ~23 px from the center the line
moves `t · sin 15°` ≥ 6 px — onto or past the ball. Next frame
`p.prev` and `p.pos` straddle the *new* line, the crossing branch fires,
and the ball is reflected back and placed on the far side: through.

**Evidence:** rising shots across the whole bar: 6 of 35 per kick
direction ended above the paddle (the outer tips).

**Fix:** after kicking, re-place the ball `r + 1` px off the rotated
line (or skip the swept test for that paddle on the ball's next frame).

**Fixed:** the kicker turns first and the ball is then placed `r + 1`
off the turned bar. `test_kick_paddle_tips_hold` (35 shots tip to tip,
both kick directions) fails on the old code and passes now.

### 3. Swept checks use a stale `prev` after a relocation — Medium

`game.py:1501` (paddles) and `game.py:2173` (walls) sweep along
`p.prev → p.pos`, but `p.prev` is the point before *this frame's move*
— not updated when an earlier collision in the same frame (a brick
bounce) teleported the ball. The swept test can then see a crossing
the ball never made and reflect it a second time, placing it on the
wrong side.

**Fix:** set `p.prev` to `p.pos` after every positional correction
(brick, wall, paddle), or resolve static geometry before bricks
(see #1) so relocations happen last.

**Fixed:** both — walls now go first (#1), and every brick, wall and
paddle bounce resets `prev` to the ball's new position
(`test_bounces_restart_the_sweep`).

### 4. Paddle overrun uses the full cell, not the brick's shape — Medium

`game.py:1453` — `_paddle_blocked` tests 9 points along the bar against
each brick's full 60×60 `cell_rect_full`, whatever its shape. A diamond's
empty corners (or a round brick's, or the 2 px gap) reach the paddle up
to ~17 px before its outline does, so the paddle shatters while
visibly clear. The same test decides spawn clearance.

**Fix:** test against `brick_outline()` (point-in-polygon, circle for
round), inflated by the margin.

### 5. Paddle spawn ignores walls, pickups, AoE icons, mines — Low

`game.py:1476` — `_spawn_paddle` only avoids bricks and other paddles.
A paddle can land along a wall line (balls double-reflect off paddle
and wall in one frame) or over a freeze / lightning icon, hiding it and
deflecting the shots that would trigger it.

**Fix:** also require clearance from `placed_walls` (a y-band),
`pickups`, placed AoE items and mines.

### 6. Paddle help icon doesn't use the `_bar` helper — Low

`render.py:687` — `draw_paddle_icon` draws with thick diagonal
`pygame.draw.line`, which renders thinner than its width — the exact
problem `_bar()` (a few lines above) exists to fix. The icon looks
unlike the in-game paddle. **Fix:** call `_bar()`.

### 7. `panic_gun` docstring still says W — Low

`game.py:1676` — "Panic load (W)"; the key moved to E in v0.7.0.

### 8. Overrun check rebuilds every brick rect per frame — Low

`game.py:1533` — each frame, every paddle runs `_paddle_blocked`: ~90
`Rect` constructions and ~810 point tests with 2 paddles and 45 bricks,
to detect an event that happens once per paddle. **Fix:** only test
bricks whose rect overlaps the paddle's bounding box.
