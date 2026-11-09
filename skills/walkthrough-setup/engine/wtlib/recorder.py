"""Record a walkthrough spec with Playwright, driving the overlay pointer."""

import json
import math
import shutil
import time
from pathlib import Path
from urllib.parse import urljoin

from .config import WalkthroughError, auth_state_path, expand

POINTER_JS = (Path(__file__).parent / "pointer.js").read_text()

ACTIONS = {
    "goto": ["url"],
    "point": ["target"],
    "hover": ["target"],
    "click": ["target"],
    "type": ["target", "text"],
    "fill": ["target", "text"],
    "press": ["key"],
    "select": ["target", "value"],
    "scroll": [],
    "highlight": ["target"],
    "label": [],
    "drag": ["target", "to"],
    "wait": ["seconds"],
    "wait_for": ["target"],
    "wait_for_url": ["url"],
    "hide_pointer": [],
    "show_pointer": [],
    "eval": ["js"],
}


def validate_spec(spec):
    """Return a list of problems; empty means the spec is runnable."""
    problems = []
    if not spec.get("app"):
        problems.append("missing 'app' (registered app name, or 'none' with an absolute start_url)")
    steps = spec.get("steps")
    if not steps:
        problems.append("missing 'steps'")
        return problems
    seen = set()
    for i, step in enumerate(steps):
        where = f"steps[{i}]"
        step_id = step.get("id")
        if not step_id or not str(step_id).replace("-", "").replace("_", "").isalnum():
            problems.append(f"{where}: 'id' must be a short slug (letters, digits, - or _)")
        elif step_id in seen:
            problems.append(f"{where}: duplicate id '{step_id}'")
        seen.add(step_id)
        for j, action in enumerate(step.get("actions", [])):
            kind = action.get("do")
            if kind not in ACTIONS:
                problems.append(f"{where}.actions[{j}]: unknown action {kind!r}; use one of {sorted(ACTIONS)}")
                continue
            for field in ACTIONS[kind]:
                if field not in action:
                    problems.append(f"{where}.actions[{j}] ({kind}): missing '{field}'")
            if kind == "scroll" and "target" not in action and "by" not in action:
                problems.append(f"{where}.actions[{j}] (scroll): needs 'target' or 'by'")
    return problems


def ease_in_out(t):
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Recorder:
    def __init__(self, page, base_url, video_cfg):
        self.page = page
        self.base_url = base_url
        self.video_cfg = video_cfg
        self.pos = (video_cfg["width"] / 2, video_cfg["height"] / 2)
        self.current_label = None

    # -- helpers -----------------------------------------------------------

    def url(self, path):
        path = expand(path)
        return path if "://" in path else urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))

    def locate(self, target, timeout=15000):
        locator = self.page.locator(expand(target)).first
        locator.wait_for(state="visible", timeout=timeout)
        locator.scroll_into_view_if_needed(timeout=timeout)
        return locator

    def center(self, locator, offset=None):
        box = locator.bounding_box()
        if not box:
            raise WalkthroughError(f"Element has no box: {locator}")
        if offset:
            return box["x"] + offset[0], box["y"] + offset[1]
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def restore_overlay(self):
        try:
            self.page.evaluate(
                "([x, y, label]) => { if (window.__wt) { __wt.set(x, y); __wt.label(label); } }",
                [self.pos[0], self.pos[1], self.current_label],
            )
        except Exception:
            pass

    def settle(self, timeout=8000):
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass

    def glide(self, x, y, speed=1.0):
        x0, y0 = self.pos
        distance = math.hypot(x - x0, y - y0)
        duration = min(max(distance / 1100, 0.35), 1.1) / max(speed, 0.1)
        frames = max(int(duration * 60), 1)
        start = time.monotonic()
        for i in range(1, frames + 1):
            t = ease_in_out(i / frames)
            self.page.mouse.move(x0 + (x - x0) * t, y0 + (y - y0) * t)
            target_time = start + duration * i / frames
            time.sleep(max(target_time - time.monotonic(), 0))
        self.pos = (x, y)
        self.restore_overlay()

    def press_visual(self, down):
        try:
            self.page.evaluate("(d) => window.__wt && __wt.press(d)", down)
        except Exception:
            pass

    # -- actions -----------------------------------------------------------

    def run_action(self, action):
        kind = action["do"]
        speed = action.get("speed", 1.0)

        if kind == "goto":
            self.page.goto(self.url(action["url"]), wait_until="domcontentloaded")
            self.settle()
            self.restore_overlay()

        elif kind in ("point", "hover"):
            self.glide(*self.center(self.locate(action["target"]), action.get("offset")), speed)
            time.sleep(action.get("pause", 0.3))

        elif kind == "click":
            x, y = self.center(self.locate(action["target"]), action.get("offset"))
            self.glide(x, y, speed)
            time.sleep(action.get("pause", 0.15))
            self.press_visual(True)
            self.page.mouse.down()
            time.sleep(0.08)
            self.page.mouse.up()
            self.press_visual(False)
            time.sleep(0.35)
            self.settle(action.get("settle_timeout", 5000))
            self.restore_overlay()

        elif kind == "type":
            locator = self.locate(action["target"])
            self.glide(*self.center(locator), speed)
            self.press_visual(True)
            locator.click()
            self.press_visual(False)
            if action.get("clear"):
                locator.fill("")
            locator.press_sequentially(expand(action["text"]), delay=action.get("delay_ms", 55))
            time.sleep(action.get("pause", 0.2))

        elif kind == "fill":
            locator = self.locate(action["target"])
            self.glide(*self.center(locator), speed)
            locator.fill(expand(action["text"]))

        elif kind == "press":
            self.page.keyboard.press(action["key"])
            time.sleep(action.get("pause", 0.3))
            self.settle(3000)
            self.restore_overlay()

        elif kind == "select":
            locator = self.locate(action["target"])
            self.glide(*self.center(locator), speed)
            locator.select_option(action["value"])
            time.sleep(action.get("pause", 0.3))

        elif kind == "scroll":
            # Eased scroll driven frame by frame, so its speed is predictable and scroll-linked
            # animations on the page play as they would for a reader.
            if "target" in action:
                locator = self.page.locator(expand(action["target"])).first
                locator.wait_for(state="attached", timeout=15000)
                destination = locator.evaluate(
                    """(el, block) => {
                        const r = el.getBoundingClientRect();
                        const y = block === "start" ? r.top - 24
                            : block === "end" ? r.bottom - innerHeight + 24
                            : r.top + r.height / 2 - innerHeight / 2;
                        return scrollY + y;
                    }""",
                    action.get("block", "center"),
                )
            else:
                destination = self.page.evaluate("() => scrollY") + action["by"]
            distance = abs(destination - self.page.evaluate("() => scrollY"))
            duration = action.get("duration", min(max(distance / 900, 0.6), 2.5))
            self.page.evaluate(
                """([to, ms]) => new Promise(done => {
                    const from = scrollY, max = document.documentElement.scrollHeight - innerHeight;
                    const end = Math.min(Math.max(to, 0), max), start = performance.now();
                    const ease = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
                    const step = now => {
                        const t = Math.min((now - start) / ms, 1);
                        scrollTo(0, from + (end - from) * ease(t));
                        t < 1 ? requestAnimationFrame(step) : done();
                    };
                    requestAnimationFrame(step);
                })""",
                [destination, int(duration * 1000)],
            )
            time.sleep(action.get("pause", 0.2))

        elif kind == "highlight":
            locator = self.locate(action["target"])
            box = locator.bounding_box()
            seconds = action.get("seconds", 1.6)
            self.page.evaluate(
                "([r, ms, dim]) => window.__wt && __wt.highlight(r, ms, dim)",
                [box, int(seconds * 1000), action.get("dim", False)],
            )
            if action.get("point", True):
                self.glide(*self.center(locator), speed)
            if action.get("wait", True):
                time.sleep(max(seconds - 0.5, 0))

        elif kind == "label":
            self.current_label = action.get("text")
            self.restore_overlay()
            time.sleep(0.3)

        elif kind == "drag":
            sx, sy = self.center(self.locate(action["target"]))
            ex, ey = self.center(self.locate(action["to"]))
            self.glide(sx, sy, speed)
            self.press_visual(True)
            self.page.mouse.down()
            self.glide(ex, ey, speed * 0.7)
            self.page.mouse.up()
            self.press_visual(False)
            time.sleep(0.3)

        elif kind == "wait":
            time.sleep(action["seconds"])

        elif kind == "wait_for":
            self.locate(action["target"], timeout=int(action.get("timeout", 30) * 1000))

        elif kind == "wait_for_url":
            self.page.wait_for_url(expand(action["url"]), timeout=int(action.get("timeout", 30) * 1000))
            self.settle()
            self.restore_overlay()

        elif kind in ("hide_pointer", "show_pointer"):
            self.page.evaluate("(h) => window.__wt && __wt.hide(h)", kind == "hide_pointer")

        elif kind == "eval":
            self.page.evaluate(action["js"])


def check_logged_in(page, app):
    check = app.get("logged_in_check")
    if not check:
        return True
    try:
        page.locator(check).first.wait_for(state="visible", timeout=10000)
        return True
    except Exception:
        return False


def record(spec, app, out_dir, durations, video_cfg, headed=False, login_fn=None):
    """Run the spec and write raw.webm + timeline.json into out_dir."""
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    tmp_video = out_dir / ".video"
    shutil.rmtree(tmp_video, ignore_errors=True)
    video_cfg = {**video_cfg, **spec.get("video", {})}
    width, height = video_cfg["width"], video_cfg["height"]
    default_hold = spec.get("default_hold", video_cfg.get("default_hold", 0.6))

    base_url = app.get("base_url", "") if app else ""
    storage_state = None
    if app and app.get("auth", "none") != "none":
        state_path = auth_state_path(app["name"])
        if not state_path.exists():
            if app["auth"] == "credentials" and login_fn:
                login_fn(app)
            else:
                raise WalkthroughError(f"No saved session for '{app['name']}'. Run `wt login {app['name']}` first.")
        storage_state = str(state_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, channel=app.get("browser_channel") if app else None)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            storage_state=storage_state,
            record_video_dir=str(tmp_video),
            # Playwright doesn't upscale screencast frames, so the video is always viewport-sized.
            record_video_size={"width": width, "height": height},
            color_scheme=spec.get("color_scheme", "light"),
        )
        context.add_init_script(POINTER_JS.replace("__WT_COLOR__", video_cfg.get("pointer_color", "#ff4d4f")))
        page = context.new_page()
        page_created = time.monotonic()
        rec = Recorder(page, base_url, video_cfg)

        start_url = spec.get("start_url", "/")
        page.goto(rec.url(start_url), wait_until="domcontentloaded")
        rec.settle()
        if app and not check_logged_in(page, app):
            context.close()
            browser.close()
            raise WalkthroughError(
                f"Session for '{app['name']}' looks expired (logged_in_check not visible). Run `wt login {app['name']}`."
            )
        for action in spec.get("setup", []):
            rec.run_action(action)
        page.mouse.move(*rec.pos)
        rec.restore_overlay()
        time.sleep(spec.get("lead_in", 0.6))

        origin = time.monotonic()
        # Playwright starts writing frames some time after the page exists, so the real
        # offset is computed at render time from the video length and closed_at.
        timeline = {"video_offset_estimate": origin - page_created, "steps": []}
        try:
            for step in spec["steps"]:
                start = time.monotonic() - origin
                print(f"  step {step['id']} @ {start:5.1f}s")
                if "label" in step:
                    rec.current_label = step["label"]
                    rec.restore_overlay()
                time.sleep(step.get("delay", 0))
                for n, action in enumerate(step.get("actions", [])):
                    try:
                        rec.run_action(action)
                    except WalkthroughError:
                        raise
                    except Exception as e:
                        detail = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
                        what = action.get("target") or action.get("url") or action.get("key") or ""
                        raise WalkthroughError(
                            f"step '{step['id']}' action {n} ({action['do']} {what}) failed: {detail}\n"
                            f"Page at failure: {out_dir / 'failure.png'}"
                        ) from e
                narration = durations.get(step["id"], 0.0)
                say_offset = step.get("say_offset", 0.0)
                floor = say_offset + narration + step.get("hold", default_hold)
                remaining = floor - (time.monotonic() - origin - start)
                if remaining > 0:
                    time.sleep(remaining)
                timeline["steps"].append({
                    "id": step["id"],
                    "start": start,
                    "say_at": start + say_offset,
                    "narration": narration,
                    "say": step.get("say", ""),
                    "poster": step.get("poster", False),
                    "chapter": step.get("chapter"),
                    "end": time.monotonic() - origin,
                })
            time.sleep(spec.get("tail", 1.0))
            timeline["end"] = time.monotonic() - origin
        except Exception:
            page.screenshot(path=str(out_dir / "failure.png"))
            raise
        finally:
            video = page.video
            timeline["closed_at"] = time.monotonic() - origin
            context.close()
            browser.close()
            if video:
                raw = out_dir / "raw.webm"
                shutil.move(video.path(), raw)
            shutil.rmtree(tmp_video, ignore_errors=True)

    (out_dir / "timeline.json").write_text(json.dumps(timeline, indent=2))
    return timeline


def inspect(app, url, out_dir, video_cfg, full_page=False):
    """Print the page's accessibility tree and save a screenshot, for choosing selectors."""
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    storage_state = None
    if app and app.get("auth", "none") != "none" and auth_state_path(app["name"]).exists():
        storage_state = str(auth_state_path(app["name"]))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=app.get("browser_channel") if app else None)
        context = browser.new_context(
            viewport={"width": video_cfg["width"], "height": video_cfg["height"]}, storage_state=storage_state
        )
        page = context.new_page()
        rec = Recorder(page, app.get("base_url", "") if app else "", video_cfg)
        page.goto(rec.url(url), wait_until="domcontentloaded")
        rec.settle()
        shot = out_dir / "inspect.png"
        page.screenshot(path=str(shot), full_page=full_page)
        print(f"URL: {page.url}\nTitle: {page.title()}\nScreenshot: {shot}\n")
        print(page.locator("body").aria_snapshot())
        browser.close()
