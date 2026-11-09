"""Mix narration onto the recorded video and write the final mp4, subtitles and poster."""

import json
import re
import shutil
import subprocess
from pathlib import Path


def _srt_time(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def caption_cues(timeline):
    """One cue per sentence, timed proportionally to its share of the step's narration."""
    cues = []
    for step in timeline["steps"]:
        text, duration = step.get("say", "").strip(), step.get("narration", 0)
        if not text or not duration:
            continue
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s]
        total = sum(len(s) for s in sentences)
        t = step["say_at"]
        for sentence in sentences:
            length = duration * len(sentence) / total
            cues.append((t, t + length, sentence))
            t += length
    return cues


def write_srt(timeline, path):
    lines = []
    for i, (start, end, text) in enumerate(caption_cues(timeline), 1):
        lines += [str(i), f"{_srt_time(start)} --> {_srt_time(end)}", text, ""]
    Path(path).write_text("\n".join(lines))


def write_chapters(timeline, path):
    """YouTube-style chapter list from steps that set "chapter"."""
    lines = []
    for step in timeline["steps"]:
        if step.get("chapter"):
            start = 0 if not lines else int(step["start"])
            lines.append(f"{start // 60}:{start % 60:02} {step['chapter']}")
    if lines:
        Path(path).write_text("\n".join(lines) + "\n")


def media_duration(path):
    """Duration in seconds; Playwright's webm often lacks a duration header, so fall back to decoding."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ) if shutil.which("ffprobe") else None
    if probe and probe.returncode == 0:
        try:
            return float(probe.stdout.strip())
        except ValueError:
            pass
    decode = subprocess.run(["ffmpeg", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    times = re.findall(r"time=(\d+):(\d+):([\d.]+)", decode.stderr)
    if not times:
        raise RuntimeError(f"Could not read duration of {path}")
    h, m, sec = times[-1]
    return int(h) * 3600 + int(m) * 60 + float(sec)


def video_offset(out_dir, timeline):
    """Seconds into raw.webm where the first step starts, anchored on when recording stopped."""
    if "closed_at" not in timeline:
        return timeline.get("video_offset", 0.0)
    return max(media_duration(Path(out_dir) / "raw.webm") - timeline["closed_at"], 0.0)


def video_size(path):
    out = subprocess.run(["ffmpeg", "-i", str(path)], capture_output=True, text=True).stderr
    match = re.search(r"Video: .*?(\d{2,5})x(\d{2,5})", out)
    if not match:
        raise RuntimeError(f"Could not read video size of {path}")
    return int(match.group(1)), int(match.group(2))


CAPTION_HTML = """<!doctype html><html><head><style>
  html, body { margin: 0; background: transparent; }
  .wrap { position: fixed; left: 0; right: 0; bottom: %(bottom)dpx; display: flex; justify-content: center; }
  .cap { max-width: 72%%; padding: 0.35em 0.75em; border-radius: 0.45em; text-align: center;
    background: rgba(17, 17, 17, 0.82); color: #fff; font: 500 %(size)dpx/1.35 -apple-system,
    BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif; }
</style></head><body><div class="wrap"><div class="cap"></div></div></body></html>"""


def render_caption_images(cues, size, out_dir):
    """Draw each caption as a transparent, frame-sized PNG with a headless browser.

    ffmpeg builds often lack libass/freetype (Homebrew's does), so text is drawn here and
    composited with the always-available overlay filter instead.
    """
    from playwright.sync_api import sync_playwright

    width, height = size
    out_dir = Path(out_dir)
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    html = CAPTION_HTML % {"size": round(width / 1280 * 26), "bottom": round(height * 0.1)}
    paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html)
        for i, (_, _, text) in enumerate(cues):
            page.locator(".cap").evaluate("(el, t) => el.textContent = t", text)
            path = out_dir / f"{i:03}.png"
            page.screenshot(path=str(path), omit_background=True)
            paths.append(path)
        browser.close()
    return paths


def build_command(out_dir, timeline, music=None, music_volume=0.12, burn_subtitles=False):
    out_dir = Path(out_dir)
    total = timeline["end"]
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{video_offset(out_dir, timeline):.3f}", "-i", str(out_dir / "raw.webm")]
    filters, mix_inputs = [], []
    next_input = 1

    clips = [s for s in timeline["steps"] if s.get("narration")]
    for step in clips:
        n = next_input
        next_input += 1
        cmd += ["-i", str(out_dir / "narration" / f"{step['id']}.wav")]
        delay = int(step["say_at"] * 1000)
        filters.append(f"[{n}:a]aresample=48000,adelay={delay}:all=1[n{n}]")
        mix_inputs.append(f"[n{n}]")

    if music:
        idx = next_input
        next_input += 1
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        fade_start = max(total - 2.0, 0)
        filters.append(
            f"[{idx}:a]aresample=48000,volume={music_volume},atrim=0:{total:.3f},"
            f"afade=t=in:d=1,afade=t=out:st={fade_start:.3f}:d=2[music]"
        )
        mix_inputs.append("[music]")

    cues = caption_cues(timeline)
    if burn_subtitles and cues:
        images = render_caption_images(cues, video_size(out_dir / "raw.webm"), out_dir / "captions")
        label = "base"
        filters.append(f"[0:v]fps=30[{label}]")
        for (start, end, _), image in zip(cues, images):
            cmd += ["-i", str(image)]
            out = f"c{next_input}"
            filters.append(f"[{label}][{next_input}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[{out}]")
            label = out
            next_input += 1
        filters.append(f"[{label}]format=yuv420p[v]")
    else:
        filters.append("[0:v]fps=30,format=yuv420p[v]")

    soft_subs = not burn_subtitles and cues
    if soft_subs:
        sub_input = next_input
        cmd += ["-i", str(out_dir / "walkthrough.srt")]

    if mix_inputs:
        filters.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0:duration=longest[a]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[v]"]
    if mix_inputs:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    if soft_subs:
        # A toggleable caption track; players that support it (QuickTime, VLC, browsers via <track>) show a CC button.
        cmd += ["-map", f"{sub_input}:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
    cmd += [
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-movflags", "+faststart",
        str(out_dir / "walkthrough.mp4"),
    ]
    return cmd


def poster_time(timeline):
    steps = timeline["steps"]
    flagged = [s for s in steps if s.get("poster")]
    step = flagged[0] if flagged else (steps[1] if len(steps) > 1 else steps[0])
    return min(step["start"] + 1.2, step["end"] - 0.1)


def render(out_dir, music=None, music_volume=0.12, burn_subtitles=False, poster_at=None):
    out_dir = Path(out_dir)
    timeline = json.loads((out_dir / "timeline.json").read_text())
    write_srt(timeline, out_dir / "walkthrough.srt")
    write_chapters(timeline, out_dir / "chapters.txt")
    subprocess.run(build_command(out_dir, timeline, music, music_volume, burn_subtitles), check=True)
    at = poster_at if poster_at is not None else poster_time(timeline)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(out_dir / "walkthrough.mp4"),
         "-frames:v", "1", "-q:v", "2", str(out_dir / "poster.jpg")],
        check=True,
    )
    print(f"Wrote {out_dir / 'walkthrough.mp4'} ({timeline['end']:.1f}s), walkthrough.srt and poster.jpg")
