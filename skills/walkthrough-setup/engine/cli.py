"""wt: record narrated, pointer-driven walkthrough videos of a real web app."""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wtlib import config as cfgmod  # noqa: E402
from wtlib.config import HOME, WalkthroughError  # noqa: E402


def load_spec(path):
    spec = json.loads(Path(path).read_text())
    from wtlib.recorder import validate_spec

    problems = validate_spec(spec)
    if problems:
        raise WalkthroughError("Spec problems:\n  - " + "\n  - ".join(problems))
    return spec


def spec_app(spec):
    return None if spec["app"] == "none" else cfgmod.load_app(spec["app"])


def default_out(spec_path):
    return Path(spec_path).resolve().parent


def narration_lines(spec):
    return [(s["id"], s["say"].strip()) for s in spec["steps"] if s.get("say", "").strip()]


# -- commands ----------------------------------------------------------------


def cmd_doctor(args):
    ok = True

    def report(good, label, hint=""):
        nonlocal ok
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + (f"  -> {hint}" if hint and not good else ""))

    print(f"walkthrough home: {HOME}")
    report(shutil.which("ffmpeg") is not None, "ffmpeg on PATH", "brew install ffmpeg")
    report(shutil.which("ffprobe") is not None, "ffprobe on PATH", "brew install ffmpeg")
    try:
        import playwright  # noqa: F401

        report(True, "playwright installed")
    except ImportError:
        report(False, "playwright installed", "re-run install.sh")
    try:
        cfg = cfgmod.load_config()
        report(True, "config.json")
        provider = cfg["tts"]["provider"]
        modules = {"kokoro": "kokoro", "chatterbox": "chatterbox", "elevenlabs": None}
        module = modules.get(provider)
        if module:
            try:
                __import__(module)
                report(True, f"TTS provider '{provider}' importable")
            except Exception as e:  # noqa: BLE001
                report(False, f"TTS provider '{provider}' importable", f"{e}; re-run install.sh {provider}")
        if provider == "chatterbox":
            ref = Path(cfg["tts"]["chatterbox"]["reference_audio"]).expanduser()
            report(ref.exists(), f"voice reference {ref}", "record 10-20s of clean speech to this path")
        if provider == "elevenlabs":
            cfgmod.load_env()
            import os

            report(bool(os.environ.get("ELEVENLABS_API_KEY")), "ELEVENLABS_API_KEY in .env", f"add it to {HOME / '.env'}")
            report(bool(cfg["tts"]["elevenlabs"].get("voice_id")), "elevenlabs voice_id set", "edit config.json")
        if provider == "kokoro":
            report(shutil.which("espeak-ng") is not None, "espeak-ng on PATH", "brew install espeak-ng")
    except WalkthroughError as e:
        report(False, "config.json", str(e))
    apps = sorted((HOME / "apps").glob("*.json"))
    for path in apps:
        app = json.loads(path.read_text())
        if app.get("auth", "none") == "none":
            print(f"  ok   app '{app['name']}' (no auth)")
            continue
        state = cfgmod.auth_state_path(app["name"])
        if state.exists():
            age = (time.time() - state.stat().st_mtime) / 86400
            print(f"  ok   app '{app['name']}' session saved {age:.1f} days ago")
        else:
            report(False, f"app '{app['name']}' session", f"wt login {app['name']}")
    if not apps:
        print("  --   no apps registered yet (wt app add)")
    return 0 if ok else 1


def cmd_app_add(args):
    path = cfgmod.app_path(args.name)
    app = json.loads(path.read_text()) if path.exists() else {}
    app.update({"name": args.name, "base_url": args.url, "auth": args.auth})
    if args.login_url:
        app["login_url"] = args.login_url
    if args.logged_in_check:
        app["logged_in_check"] = args.logged_in_check
    if args.channel:
        app["browser_channel"] = args.channel
    if args.auth == "credentials" and "login_steps" not in app:
        prefix = "WT_" + args.name.upper().replace("-", "_")
        app["login_steps"] = [
            {"do": "fill", "target": "input[type=email], input[name=email], input[name=username]", "value": f"${prefix}_USER"},
            {"do": "fill", "target": "input[type=password]", "value": f"${prefix}_PASSWORD"},
            {"do": "click", "target": "button[type=submit]"},
        ]
        print(f"Added template login_steps using ${prefix}_USER / ${prefix}_PASSWORD; check the selectors in {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(app, indent=2) + "\n")
    print(f"Saved {path}")


def cmd_app_list(args):
    for path in sorted((HOME / "apps").glob("*.json")):
        app = json.loads(path.read_text())
        print(f"{app['name']:20} {app.get('auth', 'none'):14} {app.get('base_url', '')}")


def cmd_login(args):
    from wtlib.login import login

    cfgmod.load_env()
    login(cfgmod.load_app(args.app), channel=args.channel, headed=args.headed)


def cmd_say(args):
    from wtlib.tts import make_voice

    cfgmod.load_env()
    cfg = cfgmod.load_config()
    out = Path(args.out)
    make_voice(cfg["tts"], args.provider).render(args.text, out)
    print(f"Wrote {out}")


def cmd_inspect(args):
    from wtlib.recorder import inspect

    cfgmod.load_env()
    app = None if args.app == "none" else cfgmod.load_app(args.app)
    inspect(app, args.url, args.out, cfgmod.load_config()["video"], full_page=args.full_page)


def cmd_validate(args):
    load_spec(args.spec)
    print("Spec OK")


def cmd_tts(args):
    from wtlib.tts import synthesize_lines

    cfgmod.load_env()
    spec = load_spec(args.spec)
    out = Path(args.out) if args.out else default_out(args.spec)
    durations = synthesize_lines(narration_lines(spec), out / "narration", cfgmod.load_config()["tts"], args.provider)
    total = sum(durations.values())
    print(f"Narration: {len(durations)} clips, {total:.1f}s total")
    return durations


def cmd_record(args, durations=None):
    from wtlib.login import login
    from wtlib.recorder import record

    cfgmod.load_env()
    spec = load_spec(args.spec)
    out = Path(args.out) if args.out else default_out(args.spec)
    if durations is None:
        manifest = out / "narration" / "manifest.json"
        durations = {k: v["duration"] for k, v in json.loads(manifest.read_text()).items()} if manifest.exists() else {}
    timeline = record(spec, spec_app(spec), out, durations, cfgmod.load_config()["video"], headed=args.headed, login_fn=login)
    print(f"Recorded {timeline['end']:.1f}s to {out / 'raw.webm'}")


def cmd_render(args):
    from wtlib.render import render

    render(args.out, music=args.music, music_volume=args.music_volume, burn_subtitles=args.burn_subtitles, poster_at=args.poster_at)


def cmd_run(args):
    out = Path(args.out) if args.out else default_out(args.spec)
    args.out = str(out)
    durations = cmd_tts(args) if not args.no_voice else {}
    cmd_record(args, durations)
    cmd_render(args)


def main():
    parser = argparse.ArgumentParser(prog="wt", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check the installation").set_defaults(func=cmd_doctor)

    app = sub.add_parser("app", help="manage apps to record").add_subparsers(dest="app_command", required=True)
    add = app.add_parser("add", help="register or update an app")
    add.add_argument("name")
    add.add_argument("--url", required=True, help="base URL, e.g. https://staging.example.com")
    add.add_argument("--auth", choices=["storage-state", "credentials", "none"], default="storage-state")
    add.add_argument("--login-url", help="path or URL of the login page")
    add.add_argument("--logged-in-check", help="selector that is only visible when logged in")
    add.add_argument("--channel", help="browser channel, e.g. 'chrome' to use installed Google Chrome")
    add.set_defaults(func=cmd_app_add)
    app.add_parser("list").set_defaults(func=cmd_app_list)

    login = sub.add_parser("login", help="capture a logged-in session for an app")
    login.add_argument("app")
    login.add_argument("--channel")
    login.add_argument("--headed", action="store_true", help="show the browser for credential logins")
    login.set_defaults(func=cmd_login)

    say = sub.add_parser("say", help="synthesize one line (voice test)")
    say.add_argument("text")
    say.add_argument("--out", default="voice-test.wav")
    say.add_argument("--provider")
    say.set_defaults(func=cmd_say)

    insp = sub.add_parser("inspect", help="print a page's accessibility tree and screenshot it")
    insp.add_argument("app", help="registered app name, or 'none'")
    insp.add_argument("url", help="path relative to the app's base URL, or absolute URL")
    insp.add_argument("--out", default=".", help="where to save inspect.png")
    insp.add_argument("--full-page", action="store_true")
    insp.set_defaults(func=cmd_inspect)

    validate = sub.add_parser("validate", help="check a spec without running it")
    validate.add_argument("spec")
    validate.set_defaults(func=cmd_validate)

    def common(p, recording=False, rendering=False):
        p.add_argument("spec", help="walkthrough spec JSON")
        p.add_argument("--out", help="output directory (default: the spec's directory)")
        if recording:
            p.add_argument("--headed", action="store_true", help="show the browser while recording")
        if rendering:
            p.add_argument("--music", help="optional background music file")
            p.add_argument("--music-volume", type=float, default=0.12)
            p.add_argument("--burn-subtitles", action="store_true")
            p.add_argument("--poster-at", type=float, help="poster frame time in seconds")

    tts = sub.add_parser("tts", help="generate narration clips")
    common(tts)
    tts.add_argument("--provider")
    tts.set_defaults(func=cmd_tts)

    rec = sub.add_parser("record", help="record the browser (uses existing narration timings)")
    common(rec, recording=True)
    rec.set_defaults(func=cmd_record)

    ren = sub.add_parser("render", help="mix narration and write walkthrough.mp4")
    ren.add_argument("--out", required=True)
    ren.add_argument("--music")
    ren.add_argument("--music-volume", type=float, default=0.12)
    ren.add_argument("--burn-subtitles", action="store_true")
    ren.add_argument("--poster-at", type=float)
    ren.set_defaults(func=cmd_render)

    run = sub.add_parser("run", help="tts + record + render")
    common(run, recording=True, rendering=True)
    run.add_argument("--provider")
    run.add_argument("--no-voice", action="store_true")
    run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    try:
        result = args.func(args)
        return result if isinstance(result, int) else 0
    except WalkthroughError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as e:
        print(f"error: command failed: {' '.join(map(str, e.cmd))}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
