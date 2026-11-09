# Narration voices

All settings live under `tts` in `~/.walkthrough/config.json`. `tts.provider` picks the
active one. Narration clips are cached per line, so switching voice re-generates
everything once.

## Kokoro (default)

[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M): a small open-weight model that
runs locally on CPU. It needs `espeak-ng` installed on the system.

```json
"kokoro": { "voice": "af_heart", "lang_code": "a", "speed": 1.0 }
```

- `lang_code`: `a` American English, `b` British English (others exist; see the model card).
- Good voices: `af_heart` (warm, female), `af_bella`, `am_michael` (male), `am_fenrir`,
  `bf_emma` (British, female), `bm_george` (British, male). The voice prefix must match
  `lang_code` (`a*` voices with `a`, `b*` with `b`).
- `speed`: 0.9–1.1 is the natural range. Slightly slower suits tutorials.

The model (~330 MB) downloads from Hugging Face on first use.

## Chatterbox (voice clone)

[Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI clones a voice
from a short reference clip. It runs on CUDA, Apple Silicon (`mps`) or CPU (slow: about
real time or worse). The first run downloads ~2 GB of weights.

```json
"chatterbox": {
  "reference_audio": "~/.walkthrough/voices/reference.wav",
  "exaggeration": 0.5,
  "cfg_weight": 0.5,
  "device": "auto"
}
```

**Recording the reference.** 10–20 seconds of the user speaking naturally, in the tone
they want for walkthroughs, in a quiet room, with no music and no long pauses. On macOS
without extra tools:

```bash
ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -A5 "audio devices"
ffmpeg -f avfoundation -i ":0" -t 20 -ac 1 -ar 24000 ~/.walkthrough/voices/reference.wav
```

(`:0` is the first microphone in the list.) Give them a paragraph to read aloud, e.g. a
couple of sentences describing their product. An existing clean clip works too: convert
it with `ffmpeg -i in.m4a -ac 1 -ar 24000 ~/.walkthrough/voices/reference.wav`.

**Tuning.** `exaggeration` 0.3–0.7 controls expressiveness (higher is more animated).
`cfg_weight` 0.3–0.5; lower it when the reference speaker talks fast, to get a calmer pace.
Long lines are split into sentences and joined with short pauses.

Only clone a voice the user has the right to use: their own, or one with consent.

## ElevenLabs (paid)

Uses the ElevenLabs HTTP API; no extra packages.

```json
"elevenlabs": {
  "voice_id": "<voice id>",
  "model_id": "eleven_multilingual_v2",
  "voice_settings": { "stability": 0.5, "similarity_boost": 0.75 }
}
```

- The user adds `ELEVENLABS_API_KEY=...` to `~/.walkthrough/.env` themselves (from the
  ElevenLabs dashboard, under profile → API keys).
- `voice_id`: from the ElevenLabs Voices page ("Copy voice ID"). That can be a stock voice
  or their own Instant/Professional Voice Clone.
- `voice_settings` is optional.
- Usage is billed per character; a 2-minute walkthrough is ~1,800 characters.
  Narration is cached per line, so re-recording doesn't re-bill unchanged lines.
