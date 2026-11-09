"""Narration synthesis: Chatterbox (voice clone), Kokoro, or ElevenLabs."""

import hashlib
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from .config import WalkthroughError, expand
from .render import media_duration


def split_sentences(text, max_chars=280):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


class KokoroVoice:
    def __init__(self, cfg):
        from kokoro import KPipeline

        self.cfg = cfg
        self.pipe = KPipeline(lang_code=cfg.get("lang_code", "a"))


    def render(self, text, out_path):
        import numpy as np
        import soundfile as sf

        parts = []
        for _, _, audio in self.pipe(text, voice=self.cfg.get("voice", "af_heart"), speed=self.cfg.get("speed", 1.0)):
            parts.append(audio.cpu().numpy() if hasattr(audio, "cpu") else np.asarray(audio))
        if not parts:
            raise WalkthroughError(f"Kokoro produced no audio for: {text!r}")
        sf.write(str(out_path), np.concatenate(parts), 24000)


class ChatterboxVoice:
    def __init__(self, cfg):
        import torch

        self.cfg = cfg
        device = cfg.get("device", "auto")
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        if device != "cuda":
            # Chatterbox checkpoints are saved from CUDA; remap them when loading elsewhere.
            original_load = torch.load

            def load_on_device(*args, **kwargs):
                kwargs.setdefault("map_location", torch.device(device))
                return original_load(*args, **kwargs)

            torch.load = load_on_device

        from chatterbox.tts import ChatterboxTTS

        self.reference = Path(expand(cfg.get("reference_audio", ""))).expanduser()
        if not self.reference.exists():
            raise WalkthroughError(f"Chatterbox reference audio not found: {self.reference}")
        self.model = ChatterboxTTS.from_pretrained(device=device)


    def render(self, text, out_path):
        import torch
        import torchaudio

        pieces = []
        silence = torch.zeros(1, int(self.model.sr * 0.18))
        for chunk in split_sentences(text):
            wav = self.model.generate(
                chunk,
                audio_prompt_path=str(self.reference),
                exaggeration=self.cfg.get("exaggeration", 0.5),
                cfg_weight=self.cfg.get("cfg_weight", 0.5),
            )
            pieces += [wav.cpu(), silence]
        torchaudio.save(str(out_path), torch.cat(pieces[:-1], dim=1), self.model.sr)


class ElevenLabsVoice:
    def __init__(self, cfg):
        self.cfg = cfg
        self.key = os.environ.get("ELEVENLABS_API_KEY")
        if not self.key:
            raise WalkthroughError("ELEVENLABS_API_KEY is not set in ~/.walkthrough/.env")
        if not cfg.get("voice_id"):
            raise WalkthroughError("Set tts.elevenlabs.voice_id in ~/.walkthrough/config.json")


    def render(self, text, out_path):
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.cfg['voice_id']}?output_format=mp3_44100_128"
        body = {"text": text, "model_id": self.cfg.get("model_id", "eleven_multilingual_v2")}
        if self.cfg.get("voice_settings"):
            body["voice_settings"] = self.cfg["voice_settings"]
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"xi-api-key": self.key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        )
        mp3 = Path(out_path).with_suffix(".mp3")
        with urllib.request.urlopen(request, timeout=120) as response:
            mp3.write_bytes(response.read())
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), str(out_path)], check=True)
        mp3.unlink()


PROVIDERS = {"kokoro": KokoroVoice, "chatterbox": ChatterboxVoice, "elevenlabs": ElevenLabsVoice}


def make_voice(tts_cfg, provider=None):
    provider = provider or tts_cfg.get("provider", "kokoro")
    if provider not in PROVIDERS:
        raise WalkthroughError(f"Unknown TTS provider '{provider}'. Choose one of {sorted(PROVIDERS)}.")
    return PROVIDERS[provider](tts_cfg.get(provider, {}))


def synthesize_lines(lines, out_dir, tts_cfg, provider=None):
    """Render [(id, text)] to out_dir/<id>.wav, reusing clips whose text and voice are unchanged.

    Returns {id: duration_seconds}.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    provider = provider or tts_cfg.get("provider", "kokoro")
    voice_cfg = tts_cfg.get(provider, {})
    signature = f"{provider}|{json.dumps(voice_cfg, sort_keys=True)}"
    reference = voice_cfg.get("reference_audio") if provider == "chatterbox" else None
    if reference and Path(reference).expanduser().exists():
        signature += f"|{Path(reference).expanduser().stat().st_mtime}"

    voice = None
    durations = {}
    for line_id, text in lines:
        wav = out_dir / f"{line_id}.wav"
        key = hashlib.sha1(f"{signature}|{text}".encode()).hexdigest()
        entry = manifest.get(line_id)
        if entry and entry.get("key") == key and wav.exists():
            durations[line_id] = entry["duration"]
            continue
        if voice is None:
            voice = make_voice(tts_cfg, provider)
        print(f"  narrating {line_id} ({len(text)} chars)")
        voice.render(text, wav)
        durations[line_id] = media_duration(wav)
        manifest[line_id] = {"key": key, "duration": durations[line_id], "text": text}
        manifest_path.write_text(json.dumps(manifest, indent=2))
    return durations
