---
name: loop-short
description: Produces a looping, branded vertical short (Instagram Reels / YouTube Shorts / TikTok, 1080x1920) for a Babylon channel. Public-domain paintings animate inside the channel's brand frame, narrated in the channel's cloned voice with karaoke captions, and the last line and image return to the opening so the video loops seamlessly. Use when the user asks for a new short, reel, video, episode or "part N" for a channel in channels/, or wants to remake or reframe one.
---

# Loop short

One video = one folder `channels/<slug>/videos/<NNN-slug>/`. Episode 001-tempus-edax-rerum in
roman-in-stones is the reference: read its `script.txt`, `shots.json` and `short.json` first.
The formats and craft rules are in [REFERENCE.md](REFERENCE.md).

## Workflow

Copy this checklist and tick it off:

```
- [ ] 1. Brief    read channel.md, scout/playbook.md, agents/*.md
- [ ] 2. Library  sources in content/ (librarian fetches what's missing)
- [ ] 3. Script   script.txt: hook, turn and loop line; quotes verbatim
- [ ] 4. Voice    build_short.py <dir> voice → voice.wav, words.json, timeline
- [ ] 5. Shots    shots.json from the timeline; the last shot = the first image
- [ ] 6. Preview  build_short.py <dir> render --preview ...; LOOK at the frames
- [ ] 7. Render   build_short.py <dir> render → final.mp4 + automated checks
- [ ] 8. Credits  sources.md, script.md
- [ ] 9. Review   revisor subagent (agents/revisor.md); fix and re-review until PASS
```

**1–2. Brief and library.** Pick a topic the channel's library can support with a quotable
primary source. Every image and quote must already be in `content/manifest.json` as PD/CC0.
If something is missing, run the librarian (`scripts/fetch_gutenberg.py`, `scripts/fetch_commons.py`).

**3. Script.** 100–125 words, which comes to 50–58 s. Write one paragraph per beat.
- **Hook (0–3 s):** a shock image plus a claim. A foreign-language quote can open the video.
- **Proof:** a concrete place, date or number.
- **Source:** the primary quote, verbatim, naming the author.
- **Turn:** "But…".
- **Loop line:** the last sentence must lead back into the first. See "Loop craft" in REFERENCE.md.
- Put Latin and other foreign lines in their own paragraph as `{it|Tempus edax rerum.}`.

**4. Voice.** `.venv/bin/python scripts/build_short.py <dir> voice`.
It narrates with the channel's `voice/narrator-ref.wav` and prints the word timeline.
First create `short.json` (channel, series, title, handle, music).

**5. Shots.** Plan one painting per sentence and cut on word onsets from the timeline.
- Shots must be contiguous from 0 s.
- The last shot ends about 1.2 s after the speech ends.
- The last shot uses the same image as the first, ending framed close to how the video opens.
- The window is 1:1, so choose `focus` and `zoom` for a square.

**6. Preview.** `.venv/bin/python scripts/build_short.py <dir> render --preview 1 5 9 …`
(one time per shot). Tile the frames and look at them. Check that faces are in frame, the
focal subject is visible, there's no canvas-weave blow-up (keep zoom ≤ 1.6 on small images),
and captions won't cover a face.

**7. Render.** `.venv/bin/python scripts/build_short.py <dir> render`. It builds `frame.png`,
renders the paintings into the window with music and loudness at −14 LUFS, burns in the
captions, then runs `scripts/check_short.py`. Every check must PASS.

**8–9. Credits and review.** Write `sources.md` (texts with file and line, images, music, voice,
fonts) and `script.md` (the timeline table). Then launch the revisor as a subagent with
`agents/revisor.md` and this folder. Fix everything it marks blocking and send it back.
Don't call the video done before `VERDICT: PASS`.

## Done means

`final.mp4` passes `check_short.py`, `review.md` ends in `VERDICT: PASS`, and you have looked
at the frames yourself. Report the path, the duration, the hook, the loop line, and any
placeholders the user still has to confirm (the handle, the title).
