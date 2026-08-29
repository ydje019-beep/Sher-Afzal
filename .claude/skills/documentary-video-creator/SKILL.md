---
name: documentary-video-creator
description: >
  Create history/documentary-style videos from a topic or script using ONLY real
  archival photos and footage (never AI-generated media). Searches Wikimedia
  Commons, Internet Archive, Library of Congress, NASA and Openverse for
  authentic historical media, generates a neural TTS voiceover (Urdu / Hindi /
  English and more), and edits everything with FFmpeg: Ken Burns motion on
  photos, real footage clips, fade transitions, subtitles, background music and
  attribution credits. Use when the user asks to "make a documentary video",
  "history video", "create video from script with real images", or similar.
---

# Documentary Video Creator

Creates broadcast-style documentary videos from a script using **100% real archival media**.
AI-generated images/videos are strictly forbidden — all media comes from historical archives,
and results are filtered against AI-generator keywords.

## Pipeline Overview

```
Topic/Script → scenes.json → search real media → download+validate → voiceover(TTS) → FFmpeg edit → MP4
```

## Step 0 — One-time setup

```bash
pip install edge-tts gtts 2>/dev/null   # TTS engines (free)
which ffmpeg || sudo apt-get install -y ffmpeg
```

## Step 1 — Write the script and scenes.json

If the user gave a topic only, WRITE the documentary script yourself (you are the writer).
Guidelines for good documentary narration:
- Hook in the first 2 lines; chronological or thematic structure; concrete dates/names.
- 5–10 scenes; each scene narration ~2–4 sentences (≈ 15–30 seconds of speech).
- Language: use the user's language (Urdu script for Urdu, etc.).

Then create `scenes.json`:

```json
[
  {
    "id": 1,
    "narration": "Scene 1 narration text (in the target language)...",
    "search_terms": ["specific english search term", "alternate term", "third term"]
  }
]
```

**search_terms rules (critical for good results):**
- ALWAYS in English regardless of narration language.
- Be specific & archival-friendly: `"Lahore railway station 1900s"`, `"Quaid-e-Azam Jinnah 1947"`,
  `"Mughal miniature painting Akbar"` — not vague terms like `"old city"`.
- Include era/date words: "1940s", "19th century", "vintage", "archival".
- For footage-heavy scenes add newsreel-style terms: `"partition of India newsreel"`.

## Step 2 — Search real media (never AI)

```bash
cd <workdir>
python3 <skill_path>/scripts/search_media.py --scenes scenes.json --out media_plan.json
```

- Sources: Wikimedia Commons, Internet Archive (footage/newsreels), Library of Congress,
  NASA, Openverse. All results pass an AI-keyword blocklist.
- Single query mode for gap-filling:
  `python3 <skill_path>/scripts/search_media.py --query "berlin wall 1961" --type videos --limit 5`
- Review `media_plan.json`; if a scene has < 2 candidates, re-run with broader terms and merge.

## Step 3 — Download & validate

```bash
python3 <skill_path>/scripts/download_media.py --plan media_plan.json --outdir assets --per-scene 3
```

- Validates with ffprobe, rejects HTML errors, corrupt files, images < 400px.
- Writes `assets/manifest.json` (scene → local files + attribution info).
- Check the stderr log: every scene should have ≥1 file. If a scene got 0 files,
  search again with different terms, download, and manually merge into the manifest.
- **Visual QC (recommended):** view 1–2 downloaded files per scene (Read tool on images)
  to confirm relevance; remove irrelevant files from manifest.json.

## Step 4 — Voiceover (TTS)

```bash
python3 <skill_path>/scripts/generate_voiceover.py --scenes scenes.json \
    --voice ur-PK-AsadNeural --outdir voiceover
```

Voice picks: Urdu `ur-PK-AsadNeural`/`ur-PK-UzmaNeural` · Hindi `hi-IN-MadhurNeural` ·
English documentary `en-GB-RyanNeural` or `en-US-GuyNeural`.
List voices: `--list-voices ur`. Slower gravitas: `--rate -10%`.
Outputs: `voiceover/scene_N.mp3`, `voiceover/voiceover.json`, `voiceover/subtitles.srt`.

If the user provides their own narration audio, skip this step and later pass
`--audio their_file.mp3` instead of `--voiceover`.

## Step 5 — Build the video

```bash
python3 <skill_path>/scripts/build_video.py \
    --manifest assets/manifest.json \
    --voiceover voiceover/voiceover.json \
    --subtitles voiceover/subtitles.srt \
    --out documentary.mp4 \
    --resolution 1920x1080 --fps 30 --credits
```

- Photos get Ken Burns motion (rotating zoom/pan styles); real footage gets trimmed with fades.
- Scene visual length auto-matches its narration duration.
- Optional: `--music music.mp3` (auto-ducked to 12%, fades out). Only use openly-licensed
  music (e.g. search Internet Archive audio: `mediatype:audio` + "free music").
- Vertical shorts: `--resolution 1080x1920`. Skip subtitles with omitting `--subtitles`.

## Step 6 — QC & deliver

1. `ffprobe documentary.mp4` — check duration ≈ total narration + credits.
2. Extract 3–4 spot frames and view them:
   `ffmpeg -y -ss 10 -i documentary.mp4 -frames:v 1 check1.jpg`
3. Listen-check start of audio: `ffmpeg -y -t 15 -i documentary.mp4 sample.mp3`.
4. Deliver the MP4 to the user (upload/serve) **with the credits/attribution list**
   (from manifest.json) — required for CC-licensed media.

## Hard Rules

- **NEVER generate media with AI** (no image_generation/video_generation tools) — only real
  archival media from the search script. If nothing is found for a scene, use a related real
  photo (map, painting, monument photo) rather than anything synthetic.
- Respect licenses: keep source/license info from manifest.json; include credits.
- Big downloads capped at 300MB/file; keep total project under ~2GB.
- Long ffmpeg builds: run in background and poll if > 2 min expected.

## Troubleshooting

| Problem | Fix |
|---|---|
| Scene has no media | Broaden search terms, drop dates, try `--source archive` or `--source loc` |
| LoC / Openverse return 403 | Some sandbox IPs are blocked there — Wikimedia + Archive.org still work; proceed with them |
| QC frame extraction | Extract each frame with a SEPARATE ffmpeg command (multi-output single command maps all outputs to the first input) |
| edge-tts network error | Falls back to gTTS automatically; or retry |
| zoompan jittery | Already mitigated (2x pre-upscale); reduce zoom by editing `zmax` |
| Video too long/short | Adjust narration length in scenes.json and regenerate voiceover |
| Archive.org file huge | download_media auto-prefers small mp4 derivatives |
