# Babylon

Babylon produces videos for faceless ("dark") YouTube channels. It scans social
media for viral content in a niche, digests high-level source material, and
turns it into finished videos using a multi-agent pipeline.

## Channels and agents

Every channel lives in `channels/<slug>/` and owns four agents:

| Agent | Job | Writes to |
|---|---|---|
| **librarian** | Curates the channel's source library: public-domain books, art, music. | `content/` |
| **scout** | Searches for viral videos in the niche and learns what makes them work. | `scout/` |
| **director** | Writes the script, picks images, records narration, renders the video. | `videos/<NNN-slug>/` |
| **revisor** | Validates quality; approves or sends the video back to the director. | `videos/<NNN-slug>/review.md` |

Pipeline: `librarian + scout → director → revisor → (director again if FAIL)`.

Each agent is a markdown brief at `channels/<slug>/agents/<role>.md`. To run an
agent, read its brief and launch a subagent with the brief, the channel slug and
the task. Agent briefs are per channel so channels can diverge.

## Layout

```
CLAUDE.md
scripts/                     shared tooling (python, run with .venv/bin/python)
channels/<slug>/
  channel.md                 niche, tone, voice, visual style
  assets/                    brand kit (kit/), fonts/
  voice/                     narrator reference clip for voice cloning
  agents/                    librarian.md scout.md director.md revisor.md
  content/
    manifest.json            every downloaded asset: title, author, url, license, path, tags
    INDEX.md                 human-readable catalogue
    texts/  art/  music/
  scout/                     research notes + playbook.md
  videos/<NNN-slug>/         script.md shots.json voice.mp3 words.json final.mp4 review.md sources.md
```

Channels:
- `roman-in-stones` — **Romans in Stone**: life and history of ancient Rome.

## Making a video

Use the `loop-short` skill (`.claude/skills/loop-short/`). It produces a looping, branded
vertical short from topic to reviewed `final.mp4`. The pipeline is `scripts/build_short.py <dir> voice|render`,
and `scripts/check_short.py <dir>` runs the automated checks.

## Publishing

`publisher/` is a separate uv project (Python 3.12) that publishes finished videos and collects metrics:
`cd publisher && uv run publisher --help`. See `publisher/README.md`. Its platform limits and
API research live in `publisher/config/platforms.yaml` and `publisher/docs/platforms/`. Never write
platform API calls from memory: check the official docs and mark anything unconfirmed `TODO(verificar)`.

## Rules

- **Only public-domain or openly licensed material** (PD, CC0, CC-BY with credit).
  Every asset goes in `content/manifest.json` with its source URL and license.
  If the license can't be verified, don't use it.
- **Never re-upload another creator's footage.** Viral channels are studied for
  structure and style only (metadata and captions, not video files).
- Keep downloads modest; the disk is small. No 4K video downloads for research.
- Each video folder must contain `sources.md` crediting every text and image used.
- The existing root `videos/` folder is unrelated scratch work — leave it alone.

## Tooling

- Python: `.venv/bin/python` (deps in `requirements.txt`: moviepy, pillow, opencv-python,
  numpy, edge-tts, requests). The TTS environment `.venvs/chatterbox` is Python 3.12 with
  `requirements-tts.txt`. Also on PATH: ffmpeg, yt-dlp, whisper.
- `scripts/fetch_gutenberg.py` — search gutenberg.org and download plain-text books + manifest entries.
- `scripts/fetch_commons.py` — download PD/CC0 images from Wikimedia Commons + manifest entries.
- `scripts/tts_chatterbox.py` — narration in a channel's cloned voice (Chatterbox, local) with
  word timings; `{it|...}` paragraphs are spoken with Italian phonetics (for Latin). Runs in
  `.venvs/chatterbox/` (Python 3.12); `.venvs/` also holds the TTS models kept for comparison.
- `scripts/tts.py` — edge-tts narration (fallback), with `{voice|...}` segments for other voices.
- `scripts/shorts_frame.py` — builds a video's branded 9:16 frame from a channel's `assets/kit/`.
- `scripts/render_short.py` — Ken Burns render of paintings from `shots.json` + narration,
  optionally inside a frame's video window (`--frame`).
- `scripts/add_subs.py` — burn captions from word timings.
- `scripts/yt_captions.py` — convert YouTube json3 captions into word timings/transcript.

## Video spec (shorts)

1080×1920, 30 fps, 30–60 s, H.264 + AAC, loudness ≈ −14 LUFS, burned captions,
narration plus a quiet music bed (optional). Hook must land in the first 3 s.
