"""BricksRT sound — procedural cues, no asset files.

Plays the cue names the game queues (Game.drain_events). Per DESIGN.md:
sound the meaning, not every event. Rare cues always play; brick kills
and explosions are rate-limited and folded (several in one burst play
once, louder); gun fire and bounces stay silent.

Every sound is synthesized once at startup from short sine / noise
envelopes in plain Python (no numpy), at whatever rate and channel
count the mixer actually opened with.
"""

import math
import random
from array import array

import pygame

MIX_RATE = 22050   # plenty for short effects; halves synthesis time
MIX_BUFFER = 512   # low latency so kills feel attached to the action
MASTER = 0.6
KILL_INTERVAL = 0.07     # s between kill pops (DESIGN: max 1 per ~70ms)
EXPLODE_INTERVAL = 0.06  # s between blast sounds (chains fold into one)
REPEAT_INTERVAL = 0.03   # any other cue: once per frame, no doubling


def pre_init():
    """Call before pygame.init() so the mixer opens with low latency."""
    pygame.mixer.pre_init(MIX_RATE, -16, 1, MIX_BUFFER)


# ---------------------------------------------------------------------------
# Synthesis: each builder returns float samples in -1..1 at `rate`
# ---------------------------------------------------------------------------

def _tone(rate: int, dur: float, f0: float, f1: float, decay: float,
          shape: str = "sine", vibrato: float = 0.0,
          tremolo: float = 0.0) -> list[float]:
    """Pitch sweep f0 -> f1 (exponential) with a fast attack and an
    exponential decay. shape: sine | saw | square (soft)."""
    n = int(rate * dur)
    out = []
    phase = 0.0
    for i in range(n):
        t = i / rate
        f = f0 * (f1 / f0) ** (t / dur)
        if vibrato:
            f *= 1 + 0.03 * math.sin(math.tau * vibrato * t)
        phase += f / rate
        p = phase % 1.0
        if shape == "saw":
            v = 2 * p - 1
        elif shape == "square":
            v = math.tanh(3 * math.sin(math.tau * p))  # soft-clipped
        else:
            v = math.sin(math.tau * p)
        env = min(1.0, t / 0.004) * math.exp(-t / decay)
        if tremolo:
            env *= 0.6 + 0.4 * math.sin(math.tau * tremolo * t)
        out.append(v * env)
    return out


def _noise(rate: int, dur: float, decay: float, lowpass: float,
           rng: random.Random, crackle: bool = False) -> list[float]:
    """Filtered noise burst. lowpass: one-pole coefficient (0..1, lower =
    darker). crackle gates it on and off in ~3ms grains."""
    n = int(rate * dur)
    grain = max(1, int(rate * 0.003))
    out = []
    y = 0.0
    gate = 1.0
    for i in range(n):
        if crackle and i % grain == 0:
            gate = 1.0 if rng.random() < 0.45 else 0.0
        y += lowpass * (rng.uniform(-1, 1) - y)
        t = i / rate
        out.append(y * gate * min(1.0, t / 0.002) * math.exp(-t / decay))
    return out


def _mix(rate: int, *parts: tuple[float, list[float], float]) -> list[float]:
    """Sum (start_s, samples, gain) layers into one buffer."""
    length = max(int(s * rate) + len(x) for s, x, _ in parts)
    out = [0.0] * length
    for start, samples, gain in parts:
        o = int(start * rate)
        for i, v in enumerate(samples):
            out[o + i] += v * gain
    return out


def _build_all(rate: int) -> dict[str, list[list[float]]]:
    """Every cue -> one or more variants (picked at random per play)."""
    rng = random.Random(1)
    M = lambda *parts: _mix(rate, *parts)  # noqa: E731
    T = lambda *a, **k: _tone(rate, *a, **k)  # noqa: E731
    N = lambda *a, **k: _noise(rate, *a, rng=rng, **k)  # noqa: E731
    cues: dict[str, list[list[float]]] = {}

    # Brick kill: short downward chirp + click, three pitches. Kept
    # below the blast: it's by far the most frequent cue
    cues["kill"] = [M((0, T(0.07, 900 * k, 320 * k, 0.025), 0.6),
                      (0, N(0.02, 0.006, 0.6), 0.25))
                    for k in (0.9, 1.0, 1.12)]
    # Blast: dark noise + low thump
    cues["explode"] = [M((0, N(0.5, 0.16, 0.08), 1.0),
                            (0, T(0.35, 95, 38, 0.12), 0.9))]
    # Mortar launch: hollow "thoomp"
    cues["mortar_launch"] = [M((0, T(0.16, 230, 80, 0.06), 0.9),
                                  (0, N(0.06, 0.02, 0.3), 0.35))]
    # Mine armed: two metallic ticks
    cues["mine_set"] = [M((0, T(0.04, 1700, 1650, 0.012), 0.7),
                             (0.045, T(0.04, 2300, 2250, 0.012), 0.7))]
    # Acid: a handful of rising bubble blips
    cues["acid"] = [M(*[(rng.uniform(0, 0.22),
                            T(0.05, rng.uniform(300, 500),
                              rng.uniform(650, 900), 0.02), 0.6)
                           for _ in range(6)])]
    # Tar: wet low splat
    cues["tar"] = [M((0, N(0.2, 0.06, 0.05), 1.0),
                        (0, T(0.18, 150, 70, 0.07), 0.6))]
    # Wall up: rising hum
    cues["wall_up"] = [M((0, T(0.3, 180, 360, 0.2, "square", 7), 0.45))]
    # Wall break: crunch + falling saw
    cues["wall_break"] = [M((0, N(0.3, 0.1, 0.15), 0.9),
                               (0, T(0.35, 420, 90, 0.15, "saw"), 0.45))]
    # Shield break: glassy shatter — two bright falling tones + a hiss
    cues["shield_break"] = [M((0, T(0.22, 2600, 2100, 0.07), 0.4),
                              (0.015, T(0.2, 3400, 2800, 0.06), 0.35),
                              (0, N(0.12, 0.04, 0.9), 0.3))]
    # Pickup: bright two-note blip
    cues["pickup"] = [M((0, T(0.08, 880, 880, 0.05), 0.6),
                           (0.07, T(0.1, 1320, 1320, 0.06), 0.6))]
    # Freeze: shimmering high chord
    cues["freeze"] = [M(*[(0, T(0.6, f, f * 1.01, 0.25, tremolo=18), 0.3)
                             for f in (1800, 2400, 3150)])]
    # Reverse: slow upward sweep
    cues["reverse"] = [M((0, T(0.45, 250, 1100, 0.4, "square"), 0.35))]
    # Lightning: crackle + zap
    cues["lightning"] = [M((0, N(0.4, 0.15, 0.7, crackle=True), 0.8),
                              (0, T(0.1, 2000, 600, 0.05, "saw"), 0.4))]
    # Skull: ominous falling octave + fifth, wobbling
    cues["skull"] = [M((0, T(0.8, 220, 110, 0.5, "saw", 6), 0.35),
                          (0, T(0.8, 330, 165, 0.5, vibrato=6), 0.35))]
    # Game over: falling minor triad; new best: rising arpeggio
    cues["gameover"] = [M(*[(i * 0.2, T(0.3, f, f, 0.15, "square"), 0.4)
                               for i, f in enumerate((440, 349.2, 261.6))])]
    cues["new_best"] = [M(*[(i * 0.1, T(0.35 if i == 3 else 0.12, f, f,
                                           0.2 if i == 3 else 0.06), 0.45)
                               for i, f in enumerate((523.3, 659.3, 784,
                                                      1046.5))])]
    return cues


def _to_sound(samples: list[float], channels: int) -> pygame.mixer.Sound:
    peak = max(1e-6, max(abs(v) for v in samples))
    scale = 32767 * MASTER / max(1.0, peak)  # never clip
    buf = array("h")
    for v in samples:
        s = int(v * scale)
        buf.extend([s] * channels)  # interleave for stereo mixers
    return pygame.mixer.Sound(buffer=buf.tobytes())


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

class Sounds:
    """Cue player. Silently does nothing if no audio device is available."""

    def __init__(self):
        self.enabled = False
        self.muted = False
        self.cues: dict[str, list[pygame.mixer.Sound]] = {}
        self._last: dict[str, float] = {}
        self._rng = random.Random()
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            rate, _fmt, channels = pygame.mixer.get_init()
        except pygame.error as e:
            print(f"sound disabled: {e}")
            return
        pygame.mixer.set_num_channels(16)
        self.cues = {name: [_to_sound(v, channels) for v in variants]
                     for name, variants in _build_all(rate).items()}
        self.enabled = True

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        if self.muted and self.enabled:
            pygame.mixer.stop()
        return self.muted

    def play_events(self, events: list[str], now: float | None = None):
        """Play one frame's cues. Duplicates within the frame fold into a
        single, louder play; kills and blasts are also rate-limited."""
        if not events or not self.enabled or self.muted:
            return
        if now is None:
            now = pygame.time.get_ticks() / 1000.0
        counts: dict[str, int] = {}
        for name in events:
            counts[name] = counts.get(name, 0) + 1
        for name, count in counts.items():
            variants = self.cues.get(name)
            if not variants:
                continue
            interval = (KILL_INTERVAL if name == "kill"
                        else EXPLODE_INTERVAL if name == "explode"
                        else REPEAT_INTERVAL)
            if now - self._last.get(name, -1.0) < interval:
                continue  # dropped (rate limit)
            self._last[name] = now
            snd = self._rng.choice(variants)
            snd.set_volume(min(1.0, 0.7 + 0.1 * (count - 1)))
            snd.play()
