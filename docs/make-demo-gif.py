"""BunkerVM social GIF v2 — leads with `bunkervm compare` (multi-agent ranking),
then the rewind demo, then a brand card.

All terminal text is copied from real verified runs of the released v0.11.1:
  - compare output: `bunkervm compare b7c96 66025 dbb6c --label ...`
  - risk_counts:    careful read*4 | thorough read*3 system*1 | reckless read*2
  - rewind:         1100 -> restore(2) -> 11

The CLI's text output only annotates destructive/blocked risk, so the
system-tier flag is shown in the report-card scene (where it genuinely
appears as an HTML badge), not fabricated into the CLI output.
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

f17 = ImageFont.truetype(F, 17)
f17b = ImageFont.truetype(FB, 17)
f19 = ImageFont.truetype(F, 19)
f19b = ImageFont.truetype(FB, 19)
f21b = ImageFont.truetype(FB, 21)
f15 = ImageFont.truetype(F, 15)
f36b = ImageFont.truetype(FB, 36)
f16 = ImageFont.truetype(F, 16)

# Global pacing multiplier. Bump this to slow the whole GIF down without
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
        # Persistent repo URL — the brand card only appears at the very end,
        # so anyone glancing mid-loop still sees where to find this.
        url = "github.com/ashishgituser/bunkervm"
        uw = d.textlength(url, font=f15)
        d.text((W / 2 - uw / 2, H - 32), url, font=f15, fill=(88, 88, 108))
    return img, d


def draw_segs(d, x, y, segs):
    """segs: list of (text, font, color) drawn inline, left to right."""
    for text, fnt, col in segs:
        d.text((x, y), text, font=fnt, fill=col)
        x += d.textlength(text, font=fnt)
    return x


def scene(lines, dur, y0=62, lh=26):
    """lines: list of None (blank) or list-of-segments."""
    img, d = new_canvas()
    y = y0
    for ln in lines:
        if ln is not None:
            draw_segs(d, 28, y, ln)
        y += lh
    frames.append(img)
    durations.append(int(dur * PACE))


# ── Act 1: the hook ───────────────────────────────────────────────
hook1 = [[("# 3 AI agents. Same task: clean a messy CSV.", f19, DIM)]]
hook2 = hook1 + [[("# Which one actually did it right?", f19, DIM)]]
scene(hook1, 750)
scene(hook2, 1500)

# ── Act 2: the compare command ────────────────────────────────────
cmd = hook2 + [
    None,
    [("$ ", f19, GREEN), ("bunkervm compare", f19b, TEXT), (" b7c96 66025 dbb6c \\", f19, TEXT)],
]
scene(cmd, 800)
cmd2 = cmd + [
    [
        ("    --label ", f19, TEXT),
        ("careful-agent", f19, CYAN),
        (" --label ", f19, TEXT),
        ("thorough-agent", f19, CYAN),
        (" --label ", f19, TEXT),
        ("reckless-agent", f19, CYAN),
    ]
]
scene(cmd2, 2000)  # let people actually read the full command

# ── Act 3: results land, one rank at a time ───────────────────────
base = [
    [("$ ", f17, GREEN), ("bunkervm compare", f17b, TEXT), (" b7c96 66025 dbb6c ...", f17, TEXT)],
    None,
    [("Agent Comparison", f17b, TEXT), ("  (3 sessions)", f17, DIM)],
    None,
]
r2 = [
    [
        ("  #2  ", f17, DIM),
        ("careful-agent", f17, CYAN),
        ("   [local]  4 steps  ", f17, DIM),
        ("completed", f17, GREEN),
        ("  203ms", f17, DIM),
    ],
    [("      files: +1 created  ~0 modified  -0 deleted", f17, DIM)],
]
r1 = [
    [
        ("  #1  ", f17b, GREEN),
        ("thorough-agent", f17, CYAN),
        ("  [local]  4 steps  ", f17, DIM),
        ("completed", f17, GREEN),
        ("  187ms", f17, DIM),
    ],
    [("      files: +1 created  ~0 modified  -0 deleted", f17, DIM)],
]
r3 = [
    [
        ("  #3  ", f17, DIM),
        ("reckless-agent", f17, CYAN),
        ("  [local]  2 steps  ", f17, DIM),
        ("failed (step 2)", f17, RED),
        ("  110ms", f17, DIM),
    ],
    [("      files: +0 created  ~0 modified  -0 deleted", f17, DIM)],
]
scene(base + r2, 1400)  # read rank #2
scene(base + r2 + r1, 1400)  # read rank #1
scene(base + r2 + r1 + r3, 2200)  # read rank #3 + take in the whole board

div = [
    None,
    [("  Divergence from baseline (careful-agent):", f17, TEXT)],
    [("    thorough-agent: ", f17, DIM), ("diverged at step 2", f17, AMBER)],
    [("    reckless-agent: ", f17, DIM), ("diverged at step 2", f17, AMBER)],
]
full = base + r2 + r1 + r3 + div
scene(full, 2200)
scene(
    full
    + [
        None,
        [("  Ranked on what each agent did \u2014 not an LLM grading a transcript.", f17, GREEN)],
    ],
    3200,
)

# ── Act 4: the report card, where risk tiers show up ──────────────
img, d = new_canvas()
d.text((28, 62), "report.html \u2014 per-command risk, from the safety classifier", font=f17, fill=DIM)

cols = [(40, "RANK"), (130, "AGENT"), (330, "RESULT"), (500, "RISK PROFILE")]
for x, label in cols:
    d.text((x, 108), label, font=f15, fill=DIM)
d.line([28, 130, W - 28, 130], fill=BORDER, width=1)


def badge(d, x, y, text, fg, bg):
    tw = d.textlength(text, font=f15)
    d.rounded_rectangle([x, y - 3, x + tw + 18, y + 20], radius=10, fill=bg)
    d.text((x + 9, y), text, font=f15, fill=fg)
    return x + tw + 26


rows = [
    ("#1", "thorough-agent", "completed", GREEN, [("read x3", (125, 211, 252), (30, 42, 58)), ("system x1", AMBER, (51, 39, 7))]),
    ("#2", "careful-agent", "completed", GREEN, [("read x4", (125, 211, 252), (30, 42, 58))]),
    ("#3", "reckless-agent", "failed step 2", RED, [("read x2", (125, 211, 252), (30, 42, 58))]),
]
y = 150
for rank, name, result, rcol, badges in rows:
    d.text((40, y), rank, font=f17b, fill=GREEN if rank == "#1" else DIM)
    d.text((130, y), name, font=f17, fill=CYAN)
    d.text((330, y), result, font=f17, fill=rcol)
    bx = 500
    for btext, bfg, bbg in badges:
        bx = badge(d, bx, y, btext, bfg, bbg)
    y += 46

d.line([28, y + 6, W - 28, y + 6], fill=BORDER, width=1)
d.text(
    (28, y + 24),
    "thorough-agent chmod'd its own output file.",
    font=f19,
    fill=TEXT,
)
d.text(
    (28, y + 52),
    "Flagged and visible \u2014 but not penalized. It wasn't destructive.",
    font=f19,
    fill=AMBER,
)
d.text((28, y + 84), "You see it. You decide.", font=f19b, fill=GREEN)
frames.append(img)
durations.append(int(4600 * PACE))  # densest frame — extra hold to read the badges

# ── Act 5: rewind, the other half ─────────────────────────────────
rw = [
    [("# And any recorded run rewinds to any step.", f19, DIM)],
    None,
    [("with ", f19, PURPLE), ("Sandbox(record=", f19, TEXT), ("True", f19, CYAN), (") as sb:", f19, TEXT)],
    [('    sb.run("x = 1"); sb.run("x = x + 10"); sb.run("x = x * 100")', f19, TEXT)],
    [('    print(sb.run("print(x)"))', f19, TEXT)],
]
rw2 = rw + [[("1100", f19b, GREEN)]]
scene(rw2, 1700)
rw3 = rw2 + [
    None,
    [("    sb.restore(", f19, TEXT), ("2", f19, CYAN), (")", f19, TEXT), ("   # rewind to step 2", f19, DIM)],
    [('    print(sb.run("print(x)"))', f19, TEXT)],
]
scene(rw3, 1400)
rw4 = rw3 + [[("11", f19b, GREEN)]]
scene(rw4 + [None, [("Real state restored in <100ms \u2014 not a re-run.", f19, DIM)]], 3000)

# ── Act 6: brand card ─────────────────────────────────────────────
img, d = new_canvas(footer=False)  # URL is already the hero here


def center(text, fnt, col, y):
    tw = d.textlength(text, font=fnt)
    d.text(((W - tw) / 2, y), text, font=fnt, fill=col)


center("BunkerVM", f36b, TEXT, 150)
center("Rewind your AI agent's sandbox to any step.", f19, DIM, 212)
center("Compare agents on what they actually did.", f19, DIM, 240)
center("pip install bunkervm", f21b, GREEN, 310)
center("github.com/ashishgituser/bunkervm", f21b, ACCENT, 356)
center("free \u00b7 MIT \u00b7 macOS, Linux, Windows", f16, DIM, 410)
frames.append(img)
durations.append(int(4200 * PACE))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.gif")
frames[0].save(
    out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True
)
print("wrote", out)
print("frames:", len(frames), "| total sec:", round(sum(durations) / 1000, 1))
print("size KB:", round(os.path.getsize(out) / 1024, 1))
