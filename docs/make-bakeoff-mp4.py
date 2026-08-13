"""Render the bake-off demo to MP4 (H.264) for platforms that take video but
not GIFs — Reddit video posts, X, LinkedIn.

Same pipeline as make-demo-mp4.py: re-runs the GIF script to get its in-memory
frames (full RGB, not the GIF's 256-colour palette) and repeats each frame
round(duration * FPS / 1000) times to turn variable holds into a constant
frame rate.

Output: bakeoff.mp4 — H.264 / yuv420p plus a silent AAC track, since some
platforms reject video with no audio stream at all.
"""

import os
import runpy
import subprocess

import imageio
import imageio_ffmpeg
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 25

ns = runpy.run_path(os.path.join(HERE, "make-bakeoff-gif.py"))
frames, durations = ns["frames"], ns["durations"]
print(f"source: {len(frames)} frames, {sum(durations) / 1000:.1f}s")

w, h = frames[0].size
if w % 2 or h % 2:
    raise SystemExit(f"H.264 yuv420p needs even dimensions, got {w}x{h}")

silent = os.path.join(HERE, "_bakeoff_silent.mp4")
final = os.path.join(HERE, "bakeoff.mp4")

writer = imageio.get_writer(
    silent,
    fps=FPS,
    codec="libx264",
    quality=9,
    macro_block_size=2,  # keep exact 900x560 instead of padding to /16
    pixelformat="yuv420p",
    output_params=["-profile:v", "high", "-level", "4.0"],
)
total = 0
for img, dur in zip(frames, durations):
    arr = np.asarray(img.convert("RGB"))
    for _ in range(max(1, round(dur * FPS / 1000))):
        writer.append_data(arr)
        total += 1
writer.close()
print(f"encoded {total} video frames at {FPS}fps -> {total / FPS:.1f}s")

ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
cmd = [
    ffmpeg, "-y", "-loglevel", "error",
    "-i", silent,
    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
    "-c:v", "copy", "-c:a", "aac", "-shortest",
    "-movflags", "+faststart",
    final,
]
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode != 0:
    print("silent-audio mux failed, keeping video-only file:", res.stderr.strip()[:400])
    os.replace(silent, final)
else:
    os.remove(silent)

size_mb = os.path.getsize(final) / (1024 * 1024)
print(f"wrote {final} ({size_mb:.2f} MB)")
