# Review — 001 Tempus edax rerum

Revisor, 2026-09-27. Scratch output is in `frames/` (round 1) and `frames/r2/` (round 2), both gitignored.

## Round 1 (summary) — VERDICT: FAIL
Format, loudness (−15.5 LUFS), black frames, captions, hook, licensing and visual checks all passed. Facts & quotes failed on three points:
1. The video said "Ovid wrote four words", but "Tempus edax rerum" is three words.
2. The Latin "Tempus edax rerum" could not be traced to any file in `content/texts/`.
3. The Marcus Aurelius quote was altered inside quotation marks: it dropped "thyself" and changed "that time also" to "The time".

Nice-to-haves raised in round 1:
- Soften the canvas weave on the opening 1.9× zoom.
- Whisper heard "Tempest" for "Tempus".
- Raise loudness toward −14 LUFS.
- Clean the Commons "QS:" metadata junk out of the source titles.
- Put a number in the hook.
- Delete `render.mp4`.

---

## Round 2

### 1. Format — PASS
`ffprobe`: h264 1080×1920 at 30/1 fps, AAC 44.1 kHz stereo, 57.8 s duration (inside 30–60 s).

### 2. Loudness — PASS
`loudnorm`: integrated **−14.27 LUFS** (window −16 to −12), true peak **−4.20 dBTP** (≤ −1), LRA 3.5 LU. This is now on the ≈ −14 target.

### 3. No black frames — PASS
`blackdetect=d=0.2:pix_th=0.08` returned no black_start events.

### 4. Captions match narration — PASS
The whisper base transcript (`frames/r2/final.json`) matches script.txt sentence for sentence, including "Ovid wrote three words" and "That time also is at hand, he wrote, when [thou] thyself shal[t] be forgotten by all". All 44 cues in final.srt reproduce script.txt verbatim, including "Tempus." / "Edax." / "Rerum." as separate cues. Whisper's only differences are homophones or foreign words: "Vaxino", "Eaton", "now thyself shall".
**Latin intelligibility:** whisper heard **"Tempus." (19.32–19.84) "Edax." (20.90–21.50) "Rirum." (22.70–23.14)**. "Tempus" is now correct and "Rerum" comes through as a near-homophone. It is clearly intelligible, and the captions show the right spelling.

### 5. Hook — PASS
In words.json, "Rome's Forum became a cow pasture." runs 0.10–2.32 s, so it lands under 3 s. It is a visible-puzzle hook with a concrete image (playbook rules 1–2) and no greeting.
Rule 3 (a number or date in the hook) is still not met inside the first sentence. "For centuries" follows at 3.2 s and "Two thousand years ago" at 15 s. The image of cows in the Forum is concrete enough that I don't consider this blocking.
The script is 114 words, under the 125-word cap. The recap line loops back to the opening image.

### 6. Facts & quotes — PASS
- **Latin:** `content/texts/ovid-metamorphoses-liber-xv-latin-wikisource.txt` line 247 reads "tempus edax rerum, tuque, invidiosa vetustas,". It has a manifest entry `wikisource-la-ovid-met-15` (Public domain, ancient text) and is cited in script.md and sources.md. "Three words" is now correct.
- **Ovid in English:** "Time, the consumer of {all} things … the teeth of age, with a slow death" is in `ovid-the-metamorphoses-of-ovid-books-viii-xv-26073.txt` at lines 12393–12396 (Riley), verbatim.
- **Marcus Aurelius:** `marcus-aurelius-meditations-2680.txt` lines 3063–3065 read "that time also is at hand, when thou thyself shalt be forgotten by all." The video matches verbatim and the quote is 14 words (≤ 15).
- The Campo Vaccino history is unchanged and fine.

### 7. Licensing — PASS
All 16 shots (15 unique images) exist on disk and match manifest entries: 14 Public domain, plus the Rijksmuseum Ovid title page as CC0. The music (Satie, Laucke recording) is Public domain.
sources.md credits all 3 texts with file lines, all 15 images in order, the music and the voice. The titles are now clean (no "QS:" junk), and none of the manifest titles for these shots contain it either.

### 8. Visual — PASS
I extracted 12 frames at 1.5, 9, 13.5, 17.5, 21, 25, 30, 38.5, 42, 47, 51 and 56 s (`frames/r2/rev_*.jpg`, `frames/r2/sheet_*.jpg`) plus full-res crops (`frames/r2/full_*.jpg`).
- The captions are legible: bold serif, cream with a dark outline, gold current word. There is no clipping.
- No caption sits over a main figure's face. The closest calls are Goya "Edax." (the caption is over the body, below the face), Poussin "thou thyself shalt" (over the lyre, below Father Time's face) and Hubert Robert "Marcus Aurelius found" (over the plinth).
- There is no pixelation, no crop artefacts and no black bars.
- The opening Lorrain shot at 1.5× still shows some canvas weave in the sky, but less than in round 1, and it reads as painting texture. This is acceptable.

---

VERDICT: PASS

## Fixes for the director (blocking)
None.

## Nice to have (non-blocking)
- Rule 3: a number in the first sentence (e.g. "For three hundred years, Rome's Forum was a cow pasture.") could strengthen the hook. The current hook is acceptable.
- At 1.5 s, the "a cow pasture." caption brushes the head of a tiny foreground figure at bottom left. Nudging the start focus up slightly would clear it.
- Delete `render.mp4` (98 MB intermediate) once the render is final; the disk is small. It is already gitignored.

---

## Round 3 — rebuild (new script, Chatterbox voice, brand frame)

Scratch output is in `frames/r3/` (gitignored).

### 1. Format — PASS
`ffprobe`: h264 1080×1920 at 30/1 fps, AAC 44.1 kHz stereo, 57.3 s duration (inside 30–60 s).

### 2. Loudness — PASS (f)
`loudnorm`: integrated **−14.64 LUFS** (window −16 to −12), true peak **−3.86 dBTP** (≤ −1), LRA 3.8 LU. The coordinator's −14.6 figure is confirmed.

### 3. No black frames — PASS
`blackdetect=d=0.2:pix_th=0.08` returned no events.

### 4. Captions match narration — PASS
The whisper small (en) transcript of final.mp4 (`frames/r3/final.json`) matches script.txt sentence for sentence. Its only differences are "Tempels", "shall" (for shalt), "Campovaccino" and "cowfield". All 49 cues in final.srt reproduce script.txt verbatim.

**(a) Latin at 0–2.3 s** (`frames/r3/latin.wav`, first 3 s):

| Whisper model and language | Heard |
|---|---|
| base, `--language la` | "Tempus edex rareum" |
| small, `--language la` | "Tempus edex rerum" |
| base, `--language it` | "Tempus ed ex rarum" |
| small, `--language en` (full video) | "Tempus edex rerum. Every empire ends the same way, eaten." |

It is intelligible as Latin: "Tempus" and "rerum" come through, and "edax" drifts to "edex" (the Italian open vowel). The caption "Tempus edax / rerum." shows the correct spelling.

### (b) Word timings vs audio — FAIL
I checked in two independent ways:
- **Whisper small word timestamps against words.json.** 112 of 121 words matched by text, with median offset −0.01 s and mean −0.02 s. Most words are tight, for example "was" 8.58/8.58, "words" 18.49/18.48, "teeth" 29.73/29.74, "Eaten" 36.42/36.42, "peace" 40.83/40.84, "thou" 44.73/44.74 and "hungry." 55.21/55.22.
- **`silencedetect` (−35 dB, 0.15 s) on voice.wav.** I used this to find real speech onsets after pauses.

Words that come right after a pause are given a start time equal to the previous word's end, so they light up gold during the silence:

| Word | words.json start | Actual onset (whisper / silence end) | Early by |
|---|---|---|---|
| **"And"** (final line) | 53.97 | 54.62 / 54.68 | **≈ 0.65–0.7 s** |
| "Time" (Time ate the Forum) | 52.15 | 52.54 / 52.45–52.63 | ≈ 0.4 s |
| "Rome's" | 7.38 | 7.72 / 7.83 | ≈ 0.35–0.45 s |
| "Every" | 2.83 | 2.84 / 3.11 | ≤ 0.28 s (borderline) |

The frame grab at 54.3 s (`frames/r3/rev_54.3.jpg`) confirms this: the caption "**And** it is" is shown with "And" in gold during the silence, 0.3 s before the word is spoken. The misfire lands on the payoff line, so it is visible, and I'm treating it as a blocker as the brief asks.

### 5. Hook — PASS (c)
The first English word "Every" lands at 2.83 s (words.json) / 2.84 s (whisper); "Eaten." ends at 6.57 s.
From frame 0, the viewer gets Goya's *Saturn* (a shock image), the spoken Latin with the caption "Tempus edax", and the on-frame title "EVERY EMPIRE GETS EATEN". The claim is therefore on screen within the first 3 s even though the English narration starts at 2.8 s. This is within the playbook's intent: rule 1 (a concrete thing and a claim in ≤ 3 s, no greeting), the rule 2 "superlative/universal claim" shape and rule 7 (Latin ≤ 4 words on screen).
Rule 3 (a number or date) is still not met in the hook. This remains non-blocking, as in round 2.
The script is 121 words (cap 125). The loop is good: it ends on Goya with "still hungry", then cuts back to Goya and "Tempus edax rerum".

### 6. Facts & quotes — PASS (d)
- **The quotes are unchanged and verified:**
  - The Latin is at line 247 of `ovid-metamorphoses-liber-xv-latin-wikisource.txt`.
  - The Riley translation is at lines 12393–12396.
  - Casaubon's Marcus Aurelius is at lines 3063–3065, verbatim and 14 words.
  - "Those three Latin words" is correct.
- **"By the Renaissance, cows grazed on it."** This is historically sound. After the early Middle Ages the Forum silted up and was used as pasture and later a cattle market. By the 16th century (the High and Late Renaissance) it was a known grazing ground. Saying "by" the Renaissance is a safe framing.
- **"Locals called it Campo Vaccino."** This is sound. The name is standard from about the 16th to the 19th century, and it appears in the titles of two works in this very video: Piranesi's *Veduta di Campo Vaccino* and Turner's *Modern Rome – Campo Vaccino*.
- Neither historical claim is backed by a file in `content/texts/`; the only Gibbon hit is cattle in the Forum of Peace under Theodoric, a different context. These are paraphrased historical facts rather than quotes, so this is not blocking. It is listed under Nice to have.
- "The heart of the world" is rhetorical. "Ovid, two thousand years ago" is correct (*Metamorphoses* c. 8 CE).

### 7. Licensing — PASS
- All 18 shots (16 unique images) exist on disk and are in the manifest: 15 Public domain, plus the Rijksmuseum title page as CC0. The new Turner *Agrippina* entry is `commons-joseph-mallord-william-turner-ancient-rome-agrippina-…`, Public domain, from Commons.
- sources.md lists all 16 images in order of appearance, the 3 texts with file lines, the music and the voice. The voice is Chatterbox (MIT), with a reference voice that is synthetic from Qwen3-TTS (Apache-2.0), not a real person.
- The fonts are Cinzel and Barlow under the SIL OFL; `assets/fonts/OFL-*.txt` are present. The frame comes from the channel's own brand kit.

### 8. Visual — PASS (e)
I extracted 14 frames at 1, 4.5, 11.5, 14, 18.5, 21.5, 24.5, 25.8, 30, 40, 44.5, 50, 54.3 and 56 s (`frames/r3/rev_*.jpg`, `frames/r3/sheet_*.jpg`), plus a full-res `frames/r3/full_1.0.jpg`.
- **Frame:** these elements render cleanly and stay static in every frame:
  - the "ROMANS·IN·STONE" lockup with the arch mark
  - the series line "PART 1 · TEMPUS EDAX RERUM"
  - the title "EVERY EMPIRE / GETS EATEN" (Cinzel, cream)
  - the gold meander borders at the top and bottom of the window
  - "@romansinstone" and "FOLLOW FOR MORE OF ANCIENT ROME"

  There is no aliasing or clipping. Nothing in the frame overlaps the captions, which sit at about y 1330–1420, inside the window (y 440–1520) and above the lower border.
- **Captions:** they are legible (bold serif, cream, dark outline, gold current word), and none covers a key face.
  - Goya at 1 s: the caption sits over the body and hands, and the face is clear.
  - Rubens at 4.5 s: it is below both faces.
  - Delacroix at 18.5 s: it is below the reclining Ovid.
  - Poussin at 24.5 s: it is below Father Time's face.
  - Hubert Robert at 40 s: it is over the plinth.
- **Square crops at 1:1:** there is no pixelation, no black edges and no crop artefacts.
- **Handle placeholder:** "@romansinstone" is a placeholder the user has not confirmed. It must be confirmed or replaced before publishing. Not failed, per the coordinator.

---

VERDICT: FAIL

## Fixes for the director (blocking)
1. **Fix the karaoke timing for words that follow a pause.** In words.json, a word after a gap starts at the previous word's end instead of at its own speech onset. Snap each such start to the real onset (the whisper word start, or the end of silence in `silencedetect` on voice.wav). At minimum:
   - **"And" 53.97 → ≈ 54.62**
   - **"Time" 52.15 → ≈ 52.50**
   - **"Rome's" 7.38 → ≈ 7.75**

   Check "Every" (2.83 vs a 3.11 silence end) as well. Then regenerate final.srt and the burned captions. The voice and the picture edit do not need to change.

## Nice to have (non-blocking)
- **Handle:** confirm "@romansinstone" with the user before publishing (it is a placeholder).
- **Closing Goya shot at 54.0 s:** it opens with Saturn's face cropped off the top of the window (only the mouth is visible at 54.3 s) and only reveals the face by about 56 s. Starting the focus higher, around y 0.32, would show the face on "And it is" and strengthen the loop.
- **Lorrain shot (10.0–12.8 s):** it starts at 1.8× again, and the canvas weave is visible in the sky at 11.5 s. Round 2 had brought this down to 1.5×.
- **Campo Vaccino source:** consider having the librarian add a PD text that documents the Campo Vaccino / cattle-pasture history (e.g. a 19th-c. Rome guidebook such as Murray's or Hare's *Walks in Rome*), so the historical claims are traceable like the quotes.
- **Hook:** the hook still has no number (rule 3). It is acceptable given the on-frame title.
- **Latin vowel:** whisper hears "edax" as "edex". An open "a" could be emphasised if the Latin is regenerated. The caption already covers it.
- **Cleanup:** `render.mp4` (56 MB) and `voice-tests/` sit in the video folder. Remove them when final, or confirm the non-audio files in `voice-tests/` are meant to be committed.
