"""Paths, config and secrets for the walkthrough engine."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin

HOME = Path(os.environ.get("WALKTHROUGH_HOME", "~/.walkthrough")).expanduser()
ENGINE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG = {
    "tts": {
        "provider": "kokoro",
        "kokoro": {"voice": "af_heart", "lang_code": "a", "speed": 1.0},
        "chatterbox": {
            "reference_audio": str(HOME / "voices" / "reference.wav"),
            "exaggeration": 0.5,
            "cfg_weight": 0.5,
            "device": "auto",
        },
        "elevenlabs": {"voice_id": "", "model_id": "eleven_multilingual_v2"},
    },
    "video": {
        "width": 1440,
        "height": 900,
        "pointer_color": "#ff4d4f",
        "default_hold": 0.6,
    },
}


class WalkthroughError(Exception):
    pass


def load_env():
    """Load ~/.walkthrough/.env into os.environ without overriding real env vars."""
    env_file = HOME / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def deep_merge(base, override):
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config():
    path = HOME / "config.json"
    if not path.exists():
        raise WalkthroughError(f"{path} not found. Run the walkthrough-setup skill first.")
    return deep_merge(DEFAULT_CONFIG, json.loads(path.read_text()))


def app_path(name):
    return HOME / "apps" / f"{name}.json"


def auth_state_path(name):
    return HOME / "auth" / f"{name}.json"


def load_app(name):
    path = app_path(name)
    if not path.exists():
        known = sorted(p.stem for p in (HOME / "apps").glob("*.json"))
        raise WalkthroughError(f"App '{name}' is not registered. Known apps: {known or 'none'}. Use `wt app add`.")
    return json.loads(path.read_text())


_VAR = re.compile(r"\$\$|\$\{(\w+)\}|\$(\w+)")


def expand(value):
    """Replace $VAR / ${VAR} with values from the environment (.env included); $$ is a literal $."""
    if not isinstance(value, str):
        return value

    def sub(match):
        if match.group(0) == "$$":
            return "$"
        key = match.group(1) or match.group(2)
        if key not in os.environ:
            raise WalkthroughError(f"${key} is not set. Add it to {HOME / '.env'}.")
        return os.environ[key]

    return _VAR.sub(sub, value)


def resolve_url(base_url, path):
    """An absolute URL as is, or a path joined onto the app's base URL; $VAR expanded."""
    path = expand(path)
    return path if "://" in path else urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.chmod(path, 0o600)
