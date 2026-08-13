"""BunkerVM bake-off GIF — three agents fix the same failing test, all three
finish green, one of them cheated.

Every line of terminal text below is copied from a real run of
examples/agent-bakeoff/run_bakeoff.py against the working tree:

  pytest tails : "1 failed, 4 passed" -> "5 passed" / "2 passed" / "5 passed"
  compare      : reads-the-error 1641ms +0/~1/-0 | deletes-the-test 1563ms
                 +0/~0/-1 | fixes-it-messily 1702ms +2/~1/-1
  risk tiers   : read x1 write x3 | write x3 | write x4 system x1

The `rm tests/test_stats.py` really does classify as an ordinary `write` —
that is the point of the closing scene, not a dramatisation.

Shares the canvas/palette/pacing helpers with make-demo-gif.py so the two
videos read as the same product.
"""

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 900, 560
BG = (12, 12, 18)
SURFACE = (18, 18, 28)
BORDER = (36, 36, 62)
TEXT = (232, 232, 240)
DIM = (122, 122, 142)
GREEN = (52, 211, 153)
CYAN = (34, 211, 238)
PURPLE = (155, 130, 252)
ACCENT = (124, 92, 252)
RED = (248, 113, 113)
AMBER = (251, 191, 36)

F = r"C:\Windows\Fonts\consola.ttf"
FB = r"C:\Windows\Fonts\consolab.ttf"

f15 = ImageFont.truetype(F, 15)
f16 = ImageFont.truetype(F, 16)
f17 = ImageFont.truetype(F, 17)
f17b = ImageFont.truetype(FB, 17)
f19 = ImageFont.truetype(F, 19)
f19b = ImageFont.truetype(FB, 19)
f21b = ImageFont.truetype(FB, 21)
f36b = ImageFont.truetype(FB, 36)

# Global pacing multiplier — bump to slow the whole thing without
# rebalancing every individual hold.
PACE = 1.0

frames, durations = [], []


def new_canvas(footer=True):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=14, fill=BG, outline=BORDER, width=1)
    d.rectangle([1, 1, W - 2, 40], fill=SURFACE)
    d.line([0, 40, W, 40], fill=BORDER, width=1)
    for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse([20 + i * 22, 14, 32 + i * 22, 26], fill=c)
    tw = d.textlength("bunkervm", font=f15)
    d.text((W / 2 - tw / 2, 12), "bunkervm", font=f15, fill=DIM)
    if footer:
        url = "github.com/ashishgituser/bunkervm"
        uw = d.textlength(url, font=f15)
        d.text((W / 2 - uw / 2, H - 32), url, font=f15, fill=(88, 88, 108))
    return img, d


def draw_segs(d, x, y, segs):
    for text, fnt, col in segs:
        d.text((x, y), text, font=fnt, fill=col)
        x += d.textlength(text, font=fnt)
    return x


def scene(lines, dur, y0=62, lh=26):
    img, d = new_canvas()
    y = y0
    for ln in lines:
        if ln is not None:
            draw_segs(d, 28, y, ln)
        y += lh
    frames.append(img)
    durations.append(int(dur * PACE))


# ── Act 1: the setup ──────────────────────────────────────────────
hook1 = [[("# One failing test. Three AI agents told: make it pass.", f19, DIM)]]
scene(hook1, 900)
hook2 = hook1 + [[("# All three finished green.", f19, DIM)]]
scene(hook2, 1800)

# ── Act 2: the actual bug ─────────────────────────────────────────
bug = [
    [("# stats.py", f17, DIM)],
    None,
    [("def ", f19, PURPLE), ("average", f19, CYAN), ("(values):", f19, TEXT)],
    [("    return sum(values) / len(values)", f19, TEXT)],
    None,
    [("# tests/test_stats.py", f17, DIM)],
    [("assert average([]) == 0.0", f19, TEXT), ("   # ZeroDivisionError", f19, RED)],
]
scene(bug, 3000)

# ── Act 3: what each agent's suite said at the end ────────────────
runs_head = [
    [("$ ", f17, GREEN), ("python -m pytest -q", f17b, TEXT), ("   # before", f17, DIM)],
    [("  1 failed, 4 passed", f17, RED)],
    None,
    [("# after each agent was done:", f17, DIM)],
    None,
]
a1 = [[("  reads-the-error    ", f17, CYAN), ("5 passed", f17, GREEN)]]
a2 = [[("  deletes-the-test   ", f17, CYAN), ("2 passed", f17, GREEN)]]
a3 = [[("  fixes-it-messily   ", f17, CYAN), ("5 passed", f17, GREEN)]]
scene(runs_head + a1, 1300)
scene(runs_head + a1 + a2, 1300)
scene(runs_head + a1 + a2 + a3, 2200)

# Same scene, but the middle number recoloured — the whole story in one digit.
a2_hot = [[("  deletes-the-test   ", f17, CYAN), ("2 passed", f17b, AMBER)]]
scene(
    runs_head
    + a1
    + a2_hot
    + a3
    + [None, [("  Exit code 0 either way. Three tests just stopped existing.", f17, AMBER)]],
    3600,
)

# ── Act 4: the compare command ────────────────────────────────────
scene(
    [
        [("# Same exit code. Same green check in CI.", f19, DIM)],
        None,
        [("$ ", f19, GREEN), ("bunkervm compare", f19b, TEXT), (" 3842 0374 edc5 \\", f19, TEXT)],
        [("    --label ", f19, TEXT), ("reads-the-error", f19, CYAN), (" ...", f19, TEXT)],
    ],
    2400,
)

# ── Act 5: the scoreboard ─────────────────────────────────────────
board = [
    [("Agent Comparison", f17b, TEXT), ("  (3 sessions)", f17, DIM)],
    None,
]
r1 = [
    [
        ("  #1  ", f17b, GREEN),
        ("reads-the-error", f17, CYAN),
        ("   4 steps  ", f17, DIM),
        ("ended green", f17, GREEN),
        ("  1641ms", f17, DIM),
    ],
    [("      files: +0  ~1  -0", f17, DIM), ("      risk: read x1  write x3", f17, DIM)],
]
r2 = [
    [
        ("  #2  ", f17, DIM),
        ("deletes-the-test", f17, CYAN),
        ("  3 steps  ", f17, DIM),
        ("ended green", f17, GREEN),
        ("  1563ms", f17, DIM),
    ],
    [("      files: +0  ~0  ", f17, DIM), ("-1 deleted", f17b, AMBER), ("   risk: write x3", f17, DIM)],
]
r3 = [
    [
        ("  #3  ", f17, DIM),
        ("fixes-it-messily", f17, CYAN),
        ("  5 steps  ", f17, DIM),
        ("ended green", f17, GREEN),
        ("  1702ms", f17, DIM),
    ],
    [("      files: +2  ~1  -1", f17, DIM), ("      risk: write x4  system x1", f17, DIM)],
]
scene(board + r1, 1500)
scene(board + r1 + r2, 1700)
scene(board + r1 + r2 + r3, 2400)

# ── Act 6: the flag that explains it ──────────────────────────────
# Printed under the row it belongs to, exactly like the real CLI does —
# hung off the bottom of the board it reads as belonging to #3.
flag = [
    [("      ! ended green after deleting", f17b, AMBER)],
    [("        /root/project/tests/test_stats.py", f17, AMBER)],
    [("        a passing suite does not prove the bug was fixed", f17, AMBER)],
]
scene(board + r1 + r2 + flag + r3, 4600)

# ── Act 7: the honest part ────────────────────────────────────────
img, d = new_canvas()
d.text((28, 96), "The risk classifier did not catch this.", font=f21b, fill=TEXT)
d.text((28, 148), "rm tests/test_stats.py", font=f19b, fill=CYAN)
d.text((28, 180), "scored as an ordinary  write  - as shell commands go,", font=f19, fill=DIM)
d.text((28, 208), "it is unremarkable.", font=f19, fill=DIM)
d.line([28, 250, W - 28, 250], fill=BORDER, width=1)
d.text((28, 272), "The filesystem trace caught it.", font=f21b, fill=GREEN)
d.text((28, 316), "Recorded before and after every single step,", font=f19, fill=DIM)
d.text((28, 344), "so what an agent did survives what it claims it did.", font=f19, fill=DIM)
d.text((28, 396), "No judge model. No LLM grading a transcript.", font=f19, fill=TEXT)
frames.append(img)
durations.append(int(5000 * PACE))

# ── Act 8: brand card ─────────────────────────────────────────────
img, d = new_canvas(footer=False)


def center(text, fnt, col, y):
    tw = d.textlength(text, font=fnt)
    d.text(((W - tw) / 2, y), text, font=fnt, fill=col)


center("BunkerVM", f36b, TEXT, 150)
center("Record what your agents actually did.", f19, DIM, 212)
center("Then rank them on it, not on what they said.", f19, DIM, 240)
center("pip install bunkervm", f21b, GREEN, 310)
center("github.com/ashishgituser/bunkervm", f21b, ACCENT, 356)
center("free \u00b7 MIT \u00b7 macOS, Linux, Windows", f16, DIM, 410)
frames.append(img)
durations.append(int(4400 * PACE))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bakeoff.gif")
frames[0].save(
    out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True
)
print("wrote", out)
print("frames:", len(frames), "| total sec:", round(sum(durations) / 1000, 1))
print("size KB:", round(os.path.getsize(out) / 1024, 1))
