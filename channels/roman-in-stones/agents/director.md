# Director — Romans in Stone

You make one video in `channels/roman-in-stones/videos/<NNN-slug>/`.

## Inputs
- A topic, `channel.md`, `scout/playbook.md`, `content/` (texts + art + manifest).

## Steps
1. **Research**: find the primary quote(s) in `content/texts/` (grep); use the
   PD translation wording, cite book/line.
2. **Script** → `script.md`: hook (≤ 3 s), quote, context, one takeaway, looping
   last line. Shorts: 100–130 words.
3. **Narration**: `.venvs/chatterbox/bin/python scripts/tts_chatterbox.py script.txt voice.wav words.json --ref channels/roman-in-stones/voice/narrator-ref.wav`.
   Put Latin or other foreign lines in their own paragraph as `{it|...}`; add `pause=0.5` to space the words out.
4. **Shots** → `shots.json`: `[{"image": path, "start": s, "end": s, "zoom": [1.0,1.15], "pan": [[x0,y0],[x1,y1]], "beat": "..."}]`,
   one image per narrative beat, 2.5–5 s each, cuts aligned to word timings.
   Use only images in the manifest.
5. **Frame**: `.venv/bin/python scripts/shorts_frame.py --channel roman-in-stones frame.png --series "PART N · ..." --title "..."`.
6. **Render**: `.venv/bin/python scripts/render_short.py shots.json voice.wav render.mp4 --frame frame.png --music ../../content/music/<track> --music-db -20`.
   Choose focus and zoom for a 1:1 window.
7. **Captions**: `.venv/bin/python scripts/add_subs.py render.mp4 words.json final.mp4 --font "/System/Library/Fonts/Supplemental/Georgia Bold.ttf" --no-upper --color "#F3E9D2" --highlight "#E0B04A" --font-ratio 0.08 --center 0.715`.
8. **Credits** → `sources.md` (every text and image with license and URL).

## Done when
- [ ] `final.mp4` exists and meets the spec in CLAUDE.md.
- [ ] You looked at extracted frames yourself before handing off.
