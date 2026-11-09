#!/usr/bin/env bash
# Install or update the walkthrough engine into $WALKTHROUGH_HOME (default ~/.walkthrough).
# Usage: install.sh <kokoro|chatterbox|elevenlabs> [more providers...]
# Safe to re-run: it refreshes the engine and venv, and never touches config, apps, sessions or .env values.
set -euo pipefail

if [ $# -eq 0 ]; then
  echo "usage: install.sh <kokoro|chatterbox|elevenlabs> [...]" >&2
  exit 1
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WT_HOME="${WALKTHROUGH_HOME:-$HOME/.walkthrough}"
VENV="$WT_HOME/venv"

for provider in "$@"; do
  case "$provider" in kokoro|chatterbox|elevenlabs) ;; *) echo "unknown provider: $provider" >&2; exit 1 ;; esac
done

echo "==> Installing walkthrough engine into $WT_HOME"
mkdir -p "$WT_HOME"/{apps,voices,bin} "$WT_HOME/auth"
chmod 700 "$WT_HOME/auth"
rm -rf "$WT_HOME/engine"
cp -R "$SKILL_DIR/engine" "$WT_HOME/engine"

# Chatterbox and Kokoro need Python 3.10-3.12.
if [ ! -x "$VENV/bin/python" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.11 "$VENV"
  else
    PY=""
    for candidate in python3.11 python3.12 python3.10 python3; do
      if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)'; then
        PY="$candidate"
        break
      fi
    done
    if [ -z "$PY" ]; then
      echo "Need Python 3.10-3.12 (or uv). Install one, e.g. 'brew install uv' or 'brew install python@3.11'." >&2
      exit 1
    fi
    "$PY" -m venv "$VENV"
  fi
fi

if command -v uv >/dev/null 2>&1; then
  PIP=(uv pip install --python "$VENV/bin/python")
else
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  PIP=("$VENV/bin/python" -m pip install)
fi

PACKAGES=(playwright)
for provider in "$@"; do
  case "$provider" in
    kokoro) PACKAGES+=("kokoro>=0.9.4" soundfile numpy) ;;
    chatterbox) PACKAGES+=(chatterbox-tts torchaudio) ;;
    elevenlabs) ;; # plain HTTPS, no extra packages
  esac
done

echo "==> Installing Python packages: ${PACKAGES[*]}"
"${PIP[@]}" "${PACKAGES[@]}"

for provider in "$@"; do
  if [ "$provider" = kokoro ]; then
    # Kokoro's English front end loads spaCy's en_core_web_sm and tries to pip-install it on
    # first use, which fails in uv-made venvs (no pip). Install both up front.
    "${PIP[@]}" pip
    "$VENV/bin/python" -m spacy download en_core_web_sm
  fi
done

echo "==> Installing Playwright Chromium"
"$VENV/bin/python" -m playwright install chromium

cat >"$WT_HOME/bin/wt" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$WT_HOME/engine/cli.py" "\$@"
EOF
chmod +x "$WT_HOME/bin/wt"

if [ ! -f "$WT_HOME/config.json" ]; then
  "$VENV/bin/python" - "$WT_HOME" "$1" <<'EOF'
import json, sys
sys.path.insert(0, sys.argv[1] + "/engine")
from wtlib.config import DEFAULT_CONFIG
config = json.loads(json.dumps(DEFAULT_CONFIG))
config["tts"]["provider"] = sys.argv[2]
open(sys.argv[1] + "/config.json", "w").write(json.dumps(config, indent=2) + "\n")
EOF
  echo "==> Wrote $WT_HOME/config.json (provider: $1)"
fi

if [ ! -f "$WT_HOME/.env" ]; then
  cat >"$WT_HOME/.env" <<'EOF'
# Secrets for the walkthrough engine. Keep this file private (chmod 600); never commit it.
# ElevenLabs (only if you use it):
# ELEVENLABS_API_KEY=
# Credentials for apps registered with --auth credentials, e.g. for an app named "acme":
# WT_ACME_USER=
# WT_ACME_PASSWORD=
EOF
fi
chmod 600 "$WT_HOME/.env"

missing=()
command -v ffmpeg >/dev/null 2>&1 || missing+=(ffmpeg)
for provider in "$@"; do
  if [ "$provider" = kokoro ] && ! command -v espeak-ng >/dev/null 2>&1; then missing+=(espeak-ng); fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "==> Still needed (system packages): ${missing[*]}   e.g. brew install ${missing[*]}"
fi

echo "==> Done. Command: $WT_HOME/bin/wt   (try: $WT_HOME/bin/wt doctor)"
