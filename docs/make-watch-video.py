"""BunkerVM `watch` / `review` demo video — light theme, SVG-rendered.

Frames are authored as SVG and rasterised with resvg (pure Rust, no system
Cairo), at 2x then downsampled, so type stays crisp instead of the aliased
bitmap text a direct PIL render gives you.

Every terminal block below is copied from a real `bunkervm review` run against
sessions recorded through the actual Claude Code hook:

  scenario A  npm test 12 -> 9 total, after `rm src/__tests__/auth.test.js`
  scenario B  pytest -q  47 total both times, silenced 0 -> 1

Scenario B is the one worth watching for: nothing was deleted and the total
never moved, so a diff of test counts alone would have missed it.

Outputs: docs/watch.mp4 (H.264 + silent AAC) and docs/watch.gif.

Deps: pip install resvg-py pillow imageio imageio-ffmpeg numpy
"""

import io
import os
import subprocess
from xml.sax.saxutils import escape

import imageio
import imageio_ffmpeg
import numpy as np
import resvg_py
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1200, 750
SCALE = 2  # render at 2x, downsample — cheap way to get clean glyph edges
FPS = 25

# Colour is used semantically only (pass / warn / fail); the brand tone is a
# deep ink navy carried by type weight rather than a hue. Keeps it from looking
# like every other gradient-accent dev-tool page.
GROUND = "#F6F7F9"
CARD = "#FFFFFF"
BORDER = "#E2E5EA"
INK = "#16233A"
TEXT = "#2B3444"
MUTED = "#6E7889"
FAINT = "#98A1B0"
GREEN = "#0B7A5A"
AMBER = "#B4690E"
RED = "#C0332B"
CODEBG = "#F2F4F7"

UI = "Segoe UI"
MONO = "Consolas"

frames: list[Image.Image] = []
durations: list[int] = []


def esc(s: str) -> str:
    return escape(str(s))


def render(body: str, dur_ms: int) -> None:
    """Rasterise one SVG frame and hold it for dur_ms."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W * SCALE}" height="{H * SCALE}" '
        f'viewBox="0 0 {W} {H}">'
        f'<rect width="{W}" height="{H}" fill="{GROUND}"/>'
        f"{body}</svg>"
    )
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg))
    img = Image.open(io.BytesIO(png)).convert("RGB")
    if SCALE != 1:
        img = img.resize((W, H), Image.LANCZOS)
    frames.append(img)
    durations.append(dur_ms)


def text(x, y, s, size=20, fill=TEXT, family=UI, weight="400", anchor="start", spacing=None):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{ls}'
        f' xml:space="preserve">{esc(s)}</text>'
    )


def spans(x, y, parts, size=17, family=MONO, weight="400"):
    """One line built from (text, colour) or (text, colour, weight) pieces."""
    inner = ""
    for p in parts:
        s, col = p[0], p[1]
        w = p[2] if len(p) > 2 else weight
        inner += f'<tspan fill="{col}" font-weight="{w}">{esc(s)}</tspan>'
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'xml:space="preserve">{inner}</text>'
    )


def card(x, y, w, h, radius=14, fill=CARD):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'fill="{fill}" stroke="{BORDER}" stroke-width="1"/>'
    )


def window(x, y, w, h, title=""):
    """A terminal panel: chrome bar, three dots, rounded body."""
    out = card(x, y, w, h)
    out += f'<path d="M{x} {y + 40} h{w}" stroke="{BORDER}" stroke-width="1"/>'
    for i, c in enumerate(("#E5695F", "#E0B341", "#57B65A")):
        out += f'<circle cx="{x + 22 + i * 20}" cy="{y + 20}" r="6" fill="{c}"/>'
    if title:
        out += text(x + w / 2, y + 26, title, 14, FAINT, UI, anchor="middle")
    return out


def footer():
    return text(W / 2, H - 26, "github.com/ashishgituser/bunkervm", 15, FAINT, UI, anchor="middle")


# ── 1. The setup ──────────────────────────────────────────────────
base = footer()
render(base + text(80, 300, "Your agent finished while you were away.", 40, INK, UI, "600"), 1900)
render(
    base
    + text(80, 300, "Your agent finished while you were away.", 40, INK, UI, "600")
    + text(80, 356, "It says all the tests pass.", 30, MUTED, UI, "400"),
    2100,
)
render(
    base
    + text(80, 300, "It says all the tests pass.", 40, INK, UI, "600")
    + text(80, 356, "It's telling the truth.", 30, MUTED, UI, "400"),
    2400,
)

# ── 2. Three ways green can be a lie ──────────────────────────────
ways = [
    ("It deleted the failing test.", "the suite is smaller"),
    ("It marked it @pytest.mark.skip.", "the suite is the same size"),
    ("It marked it xfail.", "the suite is the same size"),
]
head = text(80, 150, "Three ways that happens without the bug being fixed", 32, INK, UI, "600")
acc = base + head
for i, (line, note) in enumerate(ways):
    y = 290 + i * 110
    acc += card(80, y - 46, W - 160, 84)
    acc += f'<rect x="80" y="{y - 46}" width="4" height="84" rx="2" fill="{AMBER}"/>'
    acc += text(112, y - 8, line, 24, TEXT, UI, "600")
    acc += text(112, y + 22, note, 18, MUTED, UI)
    render(acc, 1500 if i < 2 else 2600)

# ── 3. Why the diff doesn't save you ──────────────────────────────
render(
    base
    + text(80, 320, "git diff shows you a deleted file.", 34, INK, UI, "600")
    + text(80, 378, "It doesn't show you a smaller suite.", 34, MUTED, UI, "400"),
    3000,
)

# ── 4. Turn it on ─────────────────────────────────────────────────
on = base + text(80, 130, "Turn it on once, per repo", 32, INK, UI, "600")
on += window(80, 180, W - 160, 130)
on += spans(112, 262, [("$ ", GREEN, "700"), ("bunkervm watch", INK, "700")], size=24)
on += text(80, 360, "Every command your agent runs is recorded from then on.", 22, MUTED, UI)
on += text(80, 394, "No VM, no KVM. macOS, Linux, Windows.", 22, MUTED, UI)
render(on, 3000)

# ── 5. review — scenario A (real output) ──────────────────────────
a = base + text(80, 116, "When it says it's done, ask what it did", 30, INK, UI, "600")
# Sized to the finished output — an oversized panel spends the build-up
# frames mostly empty, which reads as a rendering mistake rather than a pause.
a += window(80, 156, W - 160, 400)
ay = 236
a += spans(112, ay, [("$ ", GREEN, "700"), ("bunkervm review", INK, "700")], size=19)
a += spans(112, ay + 44, [("Session A   4 commands, 1 edit", MUTED)], size=18)
render(a, 2000)

a += spans(
    112,
    ay + 92,
    [("! ", AMBER, "700"), ("test count dropped: 12 -> 9 (3 fewer) running ", AMBER),
     ("`npm test`", AMBER, "700")],
    size=18,
)
render(a, 2600)

a += spans(112, ay + 126, [("! ", AMBER, "700"), ("deleted: src/__tests__/auth.test.js", AMBER)], size=18)
render(a, 2600)

a += spans(112, ay + 186, [("test runs: 3    tests in last run: 9", FAINT)], size=18)
a += spans(112, ay + 216, [("files edited: 1", FAINT)], size=18)
a += spans(136, ay + 246, [("src/auth.js", FAINT)], size=18)
render(a, 2800)

# ── 6. scenario B — nothing deleted, total unchanged ──────────────
b = base + text(80, 116, "And when it deletes nothing at all", 30, INK, UI, "600")
b += window(80, 156, W - 160, 470)
by = 236
b += spans(112, by, [("$ ", GREEN, "700"), ("bunkervm review", INK, "700")], size=19)
b += spans(112, by + 44, [("Session B   2 commands, 1 edit", MUTED)], size=18)
b += spans(
    112,
    by + 92,
    [("! ", AMBER, "700"), ("1 more test skipped or xfailed (0 -> 1)", AMBER, "700")],
    size=18,
)
b += spans(136, by + 122, [("running ", AMBER), ("`pytest -q`", AMBER, "700")], size=18)
b += spans(136, by + 152, [("silenced tests turn a suite green without", AMBER)], size=18)
b += spans(136, by + 182, [("fixing anything", AMBER)], size=18)
b += spans(112, by + 236, [("test runs: 2    tests in last run: 47", FAINT)], size=18)
render(b, 2200)

b += f'<rect x="80" y="{by + 268}" width="{W - 160}" height="2" fill="{BORDER}"/>'
b += text(112, by + 312, "47 tests before. 47 after. Nothing deleted.", 21, TEXT, UI, "600")
render(b, 3400)

# ── 7. The point ──────────────────────────────────────────────────
render(
    base
    + text(80, 300, "A test count is a number.", 36, MUTED, UI, "400")
    + text(80, 360, "Numbers are hard to skim past.", 36, INK, UI, "600"),
    3000,
)

# ── 8. Brand card ─────────────────────────────────────────────────
end = f'<rect width="{W}" height="{H}" fill="{CARD}"/>'
end += text(W / 2, 268, "BunkerVM", 58, INK, UI, "700", anchor="middle")
end += text(
    W / 2, 322, "See what your coding agent actually did.", 26, MUTED, UI, anchor="middle"
)
end += f'<rect x="{W / 2 - 220}" y="382" width="440" height="62" rx="12" fill="{CODEBG}" stroke="{BORDER}"/>'
end += text(W / 2, 421, "pip install bunkervm", 26, INK, MONO, "700", anchor="middle")
end += text(
    W / 2, 500, "github.com/ashishgituser/bunkervm", 24, INK, UI, "600", anchor="middle"
)
end += text(W / 2, 542, "free  ·  MIT  ·  macOS, Linux, Windows", 18, FAINT, UI, anchor="middle")
render(end, 4200)


# ── Encode ────────────────────────────────────────────────────────
total_s = sum(durations) / 1000
print(f"frames: {len(frames)} | {total_s:.1f}s")

gif = os.path.join(HERE, "watch.gif")
frames[0].save(
    gif, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True
)
print(f"wrote {gif} ({os.path.getsize(gif) / 1024:.0f} KB)")

silent = os.path.join(HERE, "_watch_silent.mp4")
final = os.path.join(HERE, "watch.mp4")
writer = imageio.get_writer(
    silent,
    fps=FPS,
    codec="libx264",
    quality=9,
    macro_block_size=2,
    pixelformat="yuv420p",
    output_params=["-profile:v", "high", "-level", "4.0"],
)
for img, dur in zip(frames, durations):
    arr = np.asarray(img)
    for _ in range(max(1, round(dur * FPS / 1000))):
        writer.append_data(arr)
writer.close()

ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
res = subprocess.run(
    [ffmpeg, "-y", "-loglevel", "error", "-i", silent,
     "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
     "-c:v", "copy", "-c:a", "aac", "-shortest", "-movflags", "+faststart", final],
    capture_output=True, text=True,
)
if res.returncode != 0:
    print("audio mux failed, keeping video-only:", res.stderr.strip()[:300])
    os.replace(silent, final)
else:
    os.remove(silent)
print(f"wrote {final} ({os.path.getsize(final) / (1024 * 1024):.2f} MB)")
