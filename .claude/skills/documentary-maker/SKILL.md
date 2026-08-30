# documentary-maker

**Purpose:** Build a complete, premium "faceless history documentary" video — in the exact style of
*"How America's Millionaires Built a Paradise — Then Walked Away: The Berkshires"* — fully automated:
research → script → AI voiceover → REAL archival images/footage (never AI-generated) → scene-by-scene
Ken Burns editing synced to narration → final rendered MP4.

**HARD RULE #1 — REAL VISUALS ONLY:**
- NEVER use `image_generation` or any AI image/video tool for visual content.
- Visuals MUST come from: Wikimedia Commons, Library of Congress (loc.gov), archive.org,
  NYPL Digital Collections, `image_search` tool results (respecting licensing rules), or
  public-domain archives. Every image must depict the real subject.
- The ONLY synthetic frames allowed: plain typographic title cards (chapter titles, stat cards)
  and simple parchment-style maps rendered by `scripts/make_title_card.py` — these are graphics,
  not fake photographs.

**HARD RULE #2 — STYLE FIDELITY:** Follow `references/style_bible.md` exactly
(structure, script voice, pacing, visual treatment, audio design).

---

## Workflow (execute in this order)

### PHASE 0 — Topic & Duration (MANDATORY — always do this FIRST, every single time)
**Never start production without explicit user confirmation of BOTH topic and duration.**
1. **Present topic options:** Show the user a curated menu of real Western story ideas from
   `references/topic_ideas.md` (USA / UK / Italy / Germany / France etc.). Format each as:
   country flag + title + 2-line hook + the Chekhov's Gun angle. Also highlight a Top-3
   recommendation table. Invite the user to pick a number OR propose their own topic.
2. **Ask duration explicitly** with these options:
   - 8–12 min (recommended first build — tight & powerful)
   - 15–20 min (full chapter structure)
   - 30–36 min (full reference-video scale — longest production time)
3. **WAIT for the user's answers.** Do not assume defaults. Only after the user confirms
   topic + duration, proceed to setup.
4. Create project dir: `project/<topic-slug>/` with subdirs `script/ audio/ images/ cards/ segments/ output/`.
5. Confirm narration language (default English — the reference voice style).

### PHASE 1 — Research (real facts only)
1. Use `web_search` / `crawler` to gather: key people, dates, dollar amounts, places, building names,
   a central irony or mystery (the "Chekhov's Gun" — see style bible), and a then-vs-now contrast.
2. Save findings to `script/research_notes.md` with source URLs. Facts must be verifiable —
   the style depends on precise numbers ("$950,000 house… used for three summers").

### PHASE 2 — Script writing (Claude writes it directly)
1. Write the full narration script following `references/style_bible.md` §Script.
   Structure: Cold-open stat hook → Chapters 1..N (each ends on a cliffhanger) → climax with
   plant-and-payoff → legacy chapter → two-word poetic ending.
2. Word budget: ~140 words per minute of target runtime (slow prestige pace).
3. Save as `script/narration.md` — plain narration text with `## CHAPTER` markers, no camera notes.
4. Then create `script/shotlist.json` (THE MASTER FILE) — an array of scenes:
   ```json
   {"scenes": [
     {"id": 1, "chapter": "hook", "narration": "exact sentence(s) for this scene",
      "visual_query": "Lenox Massachusetts 1899 mansion archival photo",
      "visual_type": "archival_photo | title_card | map | stat_card",
      "card_text": "(only for title/stat cards)",
      "motion": "zoom_in | zoom_out | pan_lr | pan_rl | pan_up | pan_down"}
   ]}
   ```
   One scene ≈ 1–3 sentences ≈ 8–20 seconds. Alternate motion directions. Insert a title_card
   scene at every chapter break and 2–4 stat_cards at big numbers.

### PHASE 3 — Voiceover
1. Generate narration with `audio_generation`:
   - model: `elevenlabs/v3-tts` (preferred) or `fal-ai/elevenlabs/tts/multilingual-v2`
   - requirements: "Deep, somber, authoritative male documentary narrator. Slow, deliberate pace
     with dramatic pauses. Melancholic gravitas, like a prestige history documentary."
   - Generate PER CHAPTER (keeps sync manageable & voice consistent — reuse `previous_audio_params`).
2. Download each chapter MP3 to `audio/chapter_XX.mp3`.
3. Run `audio_transcribe` (whisper-1) on the FINAL narration audio to get segment timestamps,
   OR use per-scene audio files (simpler): generate ONE audio file PER SCENE from shotlist —
   then each scene's duration = its audio duration + 0.8s breathing room. **Per-scene is the
   recommended path** for perfect frame-by-frame sync.
4. Background music: `audio_generation` with `CassetteAI/music-generator` or `elevenlabs/music` —
   somber minor-key strings for main body; warmer piano for the legacy chapter. Save to
   `audio/music_main.mp3`, `audio/music_end.mp3`. (Music beds are generated audio, which is allowed —
   the "no AI" rule applies to VISUALS.)

### PHASE 4 — Real visual acquisition (NO AI IMAGES — HARD RULE)
For each shotlist scene with `visual_type: archival_photo`:
1. FIRST: run `scripts/fetch_real_images.py "<visual_query>" <scene_id> <out_dir>` — it searches
   Wikimedia Commons API (public domain / CC), downloads the best real photo, and writes
   attribution to `images/CREDITS.md`.
2. IF Wikimedia yields nothing good: use the `image_search` tool (it has CC filtering); download
   with curl. NEVER fall back to `image_generation`.
3. IF still nothing: broaden the query (era-level instead of building-level: "Gilded Age mansion
   1890s") — a real period-accurate photo of a similar subject beats no photo; note it in CREDITS.
4. VERIFY visually: view downloaded images (Read tool) — reject logos, maps-as-photos, modern
   watermarked stock (Getty/Shutterstock/Alamy = reject), or images that don't match the scene.
5. Normalize: `scripts/prepare_image.py <img> <out>` → 1280x720-safe, treated
   (B&W/sepia for historical scenes, color kept for "today" scenes per style bible).

For `title_card` / `stat_card` / `map` scenes: `scripts/make_title_card.py` (see its --help).

### PHASE 5 — Assembly (frame-by-frame edit)
1. Build `script/timeline.json`: for each scene → image path, audio path, duration
   (= scene audio duration + 0.8s), motion type.
   `scripts/build_timeline.py` does this automatically from shotlist + audio/ + images/.
2. Render each scene with Ken Burns motion + render crossfades + mux narration:
   `scripts/render_video.py --timeline script/timeline.json --music audio/music_main.mp3 --out output/documentary.mp4`
   - 1080p (1920x1080) 30fps, H.264, zoompan Ken Burns, 1s crossfades (NO hard cuts),
     narration at full level, music bed at -22dB under voice, fade to black at end.
3. QC: extract 6–8 spot frames, view them, and `analyze_media_content` on the output for a
   final check (sync, readability of cards, no broken images).

### PHASE 6 — Delivery
1. Upload final MP4 with `UploadFileWrapper`, give user the link.
2. Include `images/CREDITS.md` (image attributions) in delivery.
3. Commit everything (except huge binaries — commit scripts/configs/script files) to git.

---

## Scripts in this skill
| Script | Role |
|---|---|
| `scripts/fetch_real_images.py` | Search+download REAL public-domain photos from Wikimedia Commons (with credits) |
| `scripts/prepare_image.py` | Normalize/treat an image: resize, letterbox-safe, sepia/B&W/vignette per style |
| `scripts/make_title_card.py` | Chapter title cards, stat cards, simple parchment maps (typographic only) |
| `scripts/build_timeline.py` | Merge shotlist + per-scene audio durations + images → timeline.json |
| `scripts/render_video.py` | Ken Burns zoompan per scene, crossfade chain, narration+music mux → final MP4 |

## References
- `references/style_bible.md` — the complete deconstruction of the reference video: structure,
  script formulas with real examples, visual treatment specs, audio specs. READ BEFORE WRITING.
- `references/topic_ideas.md` — curated bank of real Western story ideas (with Chekhov's Gun
  angles) to present to the user in PHASE 0. Refresh/extend it with web_search when needed.
- `references/qc_checklist.md` — mandatory pre-delivery quality checks.
