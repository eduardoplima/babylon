# Told in Stone (@toldinstone) — scout notes

Studied 2026-09-27. ~650k subscribers, 252 uploads on /videos. Metadata and English
auto-captions only (no video files). Raw data: `raw/_flat_videos.json`,
`raw/<id>.info.json`, `raw/<id>.en.json3`, converted transcripts in `raw/<id>/`.

## Big finding: Told in Stone has no Shorts

`yt-dlp --flat-playlist URL/shorts` returns *"This channel does not have a shorts tab"*
(also with yt-dlp 2026.08.19), and the shorts playlist `UUSH…` "does not exist".
Only 4 of 252 uploads are under 3 minutes, and three of those are trailers.
So there is no Told in Stone data on what works *as a vertical short*. What we can
learn is (a) how the channel's shortest pieces are built and (b) how its cold opens
(the first 30–45 s of the top long videos) hook viewers, which is the part a
35–55 s short is made of. Treat every rule below as "borrowed from long-form openings",
not as proven short-form performance. **Gap:** a follow-up scout run should study a
channel that actually posts Rome/Stoicism shorts.

## Shortest uploads (the closest thing to shorts), by views

| id | views | dur | title | words | wpm |
|---|---:|---:|---|---:|---:|
| V9S1NvkNJmY | 127,218 | 2:44 | Did Size Matter to the Romans? | 350 | 146 |
| 9sNVCUts6jQ | 87,968 | 1:15 | Toldinstone Channel Trailer | 113 | 92 |
| x962tU_ZMgk | 25,090 | 0:54 | Naked Statues, Fat Gladiators, and War Elephants book trailer | 106 | 118 |
| _Dvjl3u6j4M | 15,271 | 1:09 | Insane Emperors, Sunken Cities, and Earthquake Machines | 178 | 158 |
| fz4ZdXpri04 | 1,776,196 | 3:51 | Why Ancient Rome is Buried ("The Short Answer" format) | 545 | 152 |

Median length of the four sub-3-min uploads: **72.5 s**; median pace **132 wpm**
(range 92–158). Median pace across all 14 transcribed videos: **141 wpm**.

## Top long videos by views (of 248 with counts; channel median 206k views, 9:36)

| # | id | views | dur | title |
|---:|---|---:|---:|---|
| 1 | hIO8chsH_7U | 6.6M | 7:27 | What happened to the missing half of the Colosseum? |
| 2 | cE4oKzZs14A | 4.7M | 7:22 | Getting good seats at the Colosseum |
| 3 | oQX9Lh65rAA | 3.7M | 9:20 | How much was lost when the Library of Alexandria burned? |
| 4 | XxnLmD9y_uY | 2.8M | 7:58 | Bad Neighborhoods in Ancient Rome |
| 5 | _vfGjnfN5vc | 2.5M | 7:36 | Roman Houses Still Inhabited Today |
| 6 | BihMQVi5T00 | 2.4M | 11:08 | How did Roman Aqueducts work? |
| 7 | ukv3JhR4K58 | 2.4M | 7:36 | Public Latrines in Ancient Rome |
| 8 | dbvvlFHCNn4 | 2.4M | 8:40 | Why was Roman Concrete Forgotten during the Middle Ages? |
| 9 | qMNx9-AjrXM | 2.3M | 14:15 | The War That Ended the Ancient World |
| 10 | V435Le_63Z8 | 1.9M | 10:04 | How Dangerous was the Front Row of the Colosseum? |
| 11 | rbSFMUcabnU | 1.7M | 13:21 | 4 Roman Treasures Destroyed during World War II |
| 12 | fz4ZdXpri04 | 1.7M | 3:51 | Why Ancient Rome is Buried |
| 13 | mS7RDoiXv_s | 1.6M | 7:56 | Drug Use in Ancient Greece and Rome |
| 14 | SnIS9Ozo7NM | 1.5M | 16:45 | Ancient Conspiracy Theories |
| 15 | k0pddroJqt8 | 1.5M | 14:36 | The Lost Greek Cities of Central Asia |

Captions downloaded for 14 videos (all short-form + #1,3,4,6,9,10,12, plus
mkrhwBl3jms 1.27M, FqPbCcOu-js 548k, tXEslIbMoCI 249k for the time/ruins theme).
#2, #5, #7, #8 hit HTTP 429 on captions and were not retried further.

## 1. Opening hooks (exact words, with timing)

Three hook types recur in the best-performing videos:

**a) The visible puzzle — point at something and ask "what happened?"**
- hIO8chsH_7U (6.6M): *"everybody knows the Colosseum and everyone knows that this part of the Colosseum looks a lot better than this part so what happened"* — question lands at 10.0 s, self-intro deferred to 22 s. Most-viewed video on the channel.
- fz4ZdXpri04 (1.78M): *"Today's question is why is ancient Rome buried?"* then immediate concrete proof: a door cut *"10 ft or 3 m above the original"*.

**b) The vivid scene, then the twist.**
- oQX9Lh65rAA (3.7M): the legend of the caliph burning books to heat *"the city's 4,000 bath houses … it took six months to burn them all"* — then at 36.6 s: *"This never actually happened."* Myth-then-debunk.
- XxnLmD9y_uY (2.8M): *"For 500 years Rome was the biggest, richest and most spectacular city on earth. It was also the most dangerous."* Superlative then reversal at 9.2 s.
- BihMQVi5T00 (2.4M): lush description of the Trevi Fountain, turn at 17.8 s: *"impressive though all this is, the most remarkable part lies behind…"*.

**c) Cold-open narrative, dated and specific.**
- V435Le_63Z8 (1.9M): *"[55] BC Pompey the Great staged an elephant hunt in the Circus Maximus. 20 elephants…"*
- mkrhwBl3jms (1.27M): *"In the year 357 emperor Constantius II ordered an obelisk…"* (105 ft, 900,000 lb).
- tXEslIbMoCI (249k): *"In 1903, the pioneering archaeologist Giacomo Boni found a concrete foundation more than 5 m thick…"*
- qMNx9-AjrXM (2.3M): second-person travelogue, *"the wind pushes and the steppe moves before it"* — and the same line closes the video (bookend).

Weak openers correlate with the low-view uploads: the book trailers start *"I'm Garrett Ryan, I'm pleased to announce…"* (_Dvjl3u6j4M, 15k) and the channel trailer starts slowly, first word at 2.3 s, 92 wpm (9sNVCUts6jQ, 88k). The one book trailer that opens with a question — *"why didn't the Greeks or Romans wear pants"* (x962tU_ZMgk, 25k) — still beat the one that opened with the name.

## 2. Word counts and pace

- Long videos: 1,048–1,970 words, 136–151 wpm (e.g. hIO8chsH_7U 1,122 words / 151 wpm; qMNx9-AjrXM 1,970 / 139).
- "Short answer" format: fz4ZdXpri04 545 words in 3:51, 152 wpm.
- Sub-3-min: V9S1NvkNJmY 350 words / 146 wpm; x962tU_ZMgk 106 words in 54 s / 118 wpm.
- Implication: at 130–145 wpm a 35–55 s short holds **~80–125 words**. The channel's
  slow, literary voice (en-GB-RyanNeural −5 %) sits at the low end — aim ~110 words for 50 s.

## 3. Structure

- **Question → concrete evidence → causes in rising order → one-sentence answer.**
  fz4ZdXpri04 (1.78M): question (0–8 s) → the Curia's raised doors (8–60 s) → "So where did all that soil come from?" (61 s) → dust & weeds → floods → trash → "far and away the greatest culprit" rubble → recap at 190.7 s: *"Rome was buried by its own rubble and trash, by river mud, and by a little bit of dust in the wind."*
- **Answer telegraphed in the description as a punchline:** hIO8chsH_7U (6.6M) "The short answer is: earthquakes and popes, in that order." fz4ZdXpri04 (1.78M) "The short answer is: dust, dead plants, and debris." V9S1NvkNJmY (127k) "Yes, but so did how you used it."
- **Final recap line is compressed and a little witty:** hIO8chsH_7U *"we have half a Colosseum because earthquakes and the pope spared it."*
- **Bookends:** qMNx9-AjrXM (2.3M) opens and closes on the same image/sentence.
- Chapters are plain nouns (BihMQVi5T00: "Building an aqueduct", "Bridges, siphons, and tunnels"…).

## 4. Likely visuals (inferred from transcripts/descriptions)

- Deictic narration tied to images: *"this part … than this part"* (hIO8chsH_7U, 6.6M) implies pointing at a photo of the Colosseum's intact vs. ruined sides; *"As this painting of the Colosseum illustrates"* (fz4ZdXpri04, 1.78M) — **a 19th-century painting of overgrown ruins** is used as evidence; *"Detroit's Packard plant, which is shown here"* (same video) — modern ruin as comparison; *"this relief almost certainly commemorates…"* (qMNx9-AjrXM, 2.3M).
- Every hook names a concrete, picturable object (door, obelisk, fountain, elephants, library furnaces), so each sentence has a matching image. Numbers are given in both units ("10 ft or 3 m").
- Cut rhythm can't be measured without video; caption sentences run ~5–8 s, suggesting roughly one image per sentence.

## 5. Title patterns

- Question titles: 61 of 248 videos, median **277k** views vs **188k** for non-question titles; 11 of the top 30 are questions. Best: "What happened to the missing half of the Colosseum?" (6.6M), "How much was lost when the Library of Alexandria burned?" (3.7M).
- Famous landmark + unexpected angle: Colosseum appears in 3 of the top 10 (6.6M, 4.7M, 1.9M).
- Squalid daily life: "Bad Neighborhoods…" (2.8M), "Public Latrines…" (2.4M), "Drug Use…" (1.6M).
- Loss / forgetting: "…Roman Concrete Forgotten…" (2.4M), "Why Ancient Rome is Buried" (1.78M), "4 Roman Treasures Destroyed…" (1.7M).
- Number-led titles: 9 videos, median 383k.
- Titles are short (4–9 words), plain, no caps-lock hype (one exception: "Lost TWICE", 100k).

## 6. Endings / CTAs

- Nearly every video ends: one-line recap → Patreon/book plug → *"thanks for watching"* (oQX9Lh65rAA 3.7M, BihMQVi5T00 2.4M, mkrhwBl3jms 1.27M). For a short, the plug costs seconds; the useful part is the recap line before it.
- fz4ZdXpri04 (1.78M) invites engagement: *"If you have a question about the Greeks and Romans … let me know in the comments."*
- V9S1NvkNJmY (127k) ends on a pun then links a related video.
- The strongest last lines are aphoristic: mkrhwBl3jms (1.27M) *"what those lenses could not show they had no wish to see"*; FqPbCcOu-js (548k) *"the empire would fall and all the ordered symmetries of civilization dissolve to lie in chaos until the world was renewed and history repeated again."*

## 7. Relevant to an Ovid "Tempus edax rerum" / time / ruins short

Told in Stone has no Ovid video, but three pieces cover the same ground:
- **fz4ZdXpri04 — Why Ancient Rome is Buried (1.78M, 3:51).** The best physical proof of "time devours things": plants, dust, floods and fallen buildings raised Rome's ground about "an inch or a couple centimeters every century". Cites *a painting of the Colosseum covered in "rooftop forests"* — exactly the Piranesi/Robert/Cole imagery in our library. Closing line to echo: *"Rome was buried by its own rubble and trash, by river mud, and by a little bit of dust in the wind."*
- **FqPbCcOu-js — What Did the Romans Think the Future Would Be Like? (548k).** Romans expected decline, not progress: Hesiod's ages of man, Seneca's world-ending flood, cyclical history. *"Despite poetic effusions about a new golden age, the Romans expected decline."* Good context line: Ovid's own Metamorphoses opens with the ages of man, and he ends Book 15 with "tempus edax rerum".
- **tXEslIbMoCI — Romans and the Ruins of Older Civilizations (249k, 2026).** Romans lived among ruins older than themselves (archaic tomb under the Forum; Lycian tombs kept inside Roman theatres). Angle: *the Romans already felt what we feel at the Forum*.
- Also mkrhwBl3jms (1.27M): the Romans marvelling at pyramids and obelisks "which nobody in Rome could read" — ruins-within-ruins.
- Themes about loss/ruin/forgetting consistently beat the channel median (206k): 6.6M, 3.7M, 2.4M, 1.78M, 1.7M above.

Suggested hook for that short, following the "visible puzzle" pattern of hIO8chsH_7U and fz4ZdXpri04:
*"Rome's Senate house has three doors, one above the other. Ovid explained why."* → Curia doors / buried Forum (paintings of the overgrown Campo Vaccino) → Ovid, Met. 15.234–236 *"tempus edax rerum, tuque, invidiosa vetustas, omnia destruitis"* → the Colosseum's rooftop forests → one-line takeaway.
