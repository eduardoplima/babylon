# Loop short: reference

## Folder

```
channels/<slug>/videos/<NNN-slug>/
  short.json    frame text + music            (you write)
  script.txt    narration                     (you write)
  voice.wav     narration audio               (voice step)
  words.json    word timings for captions     (voice step)
  shots.json    painting timeline             (you write, from the timeline)
  frame.png     branded frame                 (render step)
  final.mp4     the video                     (render step)
  final.srt     captions as text              (render step)
  sources.md    credits                       (you write)
  script.md     timeline table + citations    (you write)
  review.md     revisor verdict               (revisor)
```

## short.json

```json
{
 "channel": "roman-in-stones",
 "series": "PART 1 · TEMPUS EDAX RERUM",
 "title": "EVERY EMPIRE GETS EATEN",
 "handle": "@romansinstone",
 "music": "music/satie-gymnopedie-no-1-performed-by-michael-laucke.flac",
 "music_db": -20
}
```

- `series`: the small gold line above the title, e.g. "PART N · <theme>".
- `title`: 2–5 words in caps. It wraps into two balanced lines.
- `music`: a path relative to `content/` (PD/CC0 only). `music_start` skips into the track.
- Optional keys: `follow` (bottom line), `voice_ref`, `seed` (change it to get a different take).

## script.txt

- One paragraph per beat, separated by a blank line; each paragraph becomes one TTS call.
- `{it|Tempus edax rerum.}` is spoken with Italian phonetics in the same voice. Use it for
  Latin; Italian reads Latin spelling almost exactly like classical Latin. Other languages
  work too (`{fr|…}`, `{de|…}`, `{el|…}` for Modern Greek).
- `{it pause=0.5|Tempus edax rerum.}` spaces the words out. Leave it off in the hook.
- Straight quotes are fine: they are dropped from the speech and from the captions.

## shots.json

```json
[{"image": "../../content/art/<file>.jpg", "start": 0.0, "end": 2.7,
  "zoom": [1.15, 1.45], "focus": [[0.45, 0.32], [0.42, 0.28]], "beat": "Tempus edax rerum."}]
```

- `focus`: the point of the painting (x, y from 0 to 1) at the window centre, at the start and
  end of the shot. It is clamped so the crop never leaves the image.
- `zoom`: 1.0 means the painting just covers the 1080×1080 window. Keep it ≤ 1.6 on images
  under 3000 px, or the canvas weave shows.
- Cut about 0.1 s before the onset of the first word of each beat. Crossfades are 0.4 s.
- Portrait paintings (the Goya and Rubens *Saturns*) show only about 55 % of their height in a
  square window, so aim `focus` y at the face (~0.3), not at 0.5.

## Loop craft

A loop works when the final second flows into second zero with no reset:

1. **Same image, same framing.** The last shot uses the first shot's painting. Have it push in
   toward the framing the opening starts from.
2. **The last line feeds the first.** "…And it is still hungry." → "*Tempus edax rerum.*" Aim
   for a line that asks for or answers the opening: a pronoun that points back ("it"), an
   unfinished thought, or the translation of the opening quote.
3. **No outro.** No "subscribe", no fade to black, no silence longer than about 1.5 s. The
   music fades out under the tail; a hard cut back to the start is fine.
4. **The hook works on replay.** A viewer who has just heard the ending should get it on
   second hearing ("Oh — *that's* what eats empires.").

## Captions

Serif Georgia Bold, cream `#F3E9D2`, the current word in gold `#E0B04A`, up to 3 words,
centred at 71.5 % of the height (inside the lower window). Captions break at `.?!` and at
pauses. `words.json` onsets are snapped to where each word is actually spoken; if the
highlight still runs early after a pause, re-run
`.venvs/chatterbox/bin/python scripts/tts_chatterbox.py script.txt voice.wav words.json --ref X --snap-only`.

## Lessons from episode 001 (the revisor caught these)

- **Count what you claim.** "Ovid wrote four words" (it's three). Numbers in the script get checked.
- **Quotes are verbatim** from a file in `content/texts/`, with its line numbers in `script.md`.
  Paraphrase goes outside quotation marks.
- **The original-language line needs a source file too.** We added the Latin *Metamorphoses* from Wikisource.
- **English TTS mangles Latin** ("Tempus" became "Tempest"). Always use `{it|…}`.
- **Whisper absorbs pauses into the next word.** That's why onset snapping exists; check the
  karaoke timing after pauses in the preview.
- **Commons titles** carry Wikidata junk; `fetch_commons.py` cleans them, but check `sources.md`.

## Tools

| Step | Command |
|---|---|
| Narration | `.venvs/chatterbox/bin/python scripts/tts_chatterbox.py` (called by build_short) |
| Frame only | `.venv/bin/python scripts/shorts_frame.py --channel <slug> out.png --series … --title …` |
| Render only | `.venv/bin/python scripts/render_short.py shots.json voice.wav render.mp4 --frame frame.png` |
| Checks | `.venv/bin/python scripts/check_short.py <dir>` |
| Library | `scripts/fetch_gutenberg.py`, `scripts/fetch_commons.py` (`--search` first) |

Setup, if missing: `.venv` from `requirements.txt`, and `.venvs/chatterbox` (Python 3.12) with
`chatterbox-tts soundfile openai-whisper "setuptools<80"`.
