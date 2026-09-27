# Romans in Stone

**Niche:** the life, history and mind of the ancient Romans — emperors and
slaves, poets and soldiers, what they believed about time, death, love and power.

**Style reference:** Told in Stone (https://www.youtube.com/@toldinstone) —
studied for structure only, see `scout/`.

**Audience:** English-speaking history and philosophy fans, 18–45, who watch
Stoicism / ancient-history shorts.

**Tone:** quiet, literary, slightly melancholy. Let the Romans speak in their
own words (quote the sources), then give one sharp modern takeaway. No hype
words, no "you won't believe".

**Voice:** Chatterbox (MIT), run locally, cloning `voice/narrator-ref.wav`: a deep,
calm British narrator. The reference was designed with Qwen3-TTS VoiceDesign, so it is
synthetic and not anyone's real voice. Use this one file for every video so the
narrator stays the same. Latin and other foreign lines use Italian phonetics:
`{it|Tempus edax rerum.}` in the script.

**Visuals:** classical oil paintings and engravings of Rome (Cole, Robert,
Panini, Piranesi, Alma-Tadema, Gérôme, Couture). Slow Ken Burns zoom/pan,
warm grade, dark vignette, crossfades. Serif captions (Georgia Bold), cream
text with dark outline, current word in gold.

**Frame:** every short goes inside the brand kit's Shorts frame
(`assets/kit/shorts-9x16-blank.png`), built per video with `scripts/shorts_frame.py`:
- a series line (e.g. `PART 1 · TEMPUS EDAX RERUM`);
- a title of two balanced lines at most;
- the handle and a follow line at the bottom.

The paintings animate in the 1080×1080 window; captions sit in its lower part.

**Formats:** vertical shorts (35–60 s) first; long-form later.
