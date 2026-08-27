#!/usr/bin/env python3
"""
generate_voiceover.py — Generate documentary voiceover from a script using free TTS.

Engine priority:
  1. edge-tts (Microsoft neural voices; best quality; Urdu/Hindi/English supported)
  2. gTTS (Google Translate TTS; fallback)

Also generates per-scene audio + an SRT subtitle file with estimated timings.

Setup (once):  pip install edge-tts gtts

Usage:
  # single narration file
  python3 generate_voiceover.py --text "script text..." --voice ur-PK-AsadNeural --out vo.mp3

  # per-scene from scenes.json  [{"id":1,"narration":"..."}, ...]
  python3 generate_voiceover.py --scenes scenes.json --voice en-US-GuyNeural --outdir voiceover

Recommended documentary voices:
  Urdu:    ur-PK-AsadNeural (male), ur-PK-UzmaNeural (female)
  Hindi:   hi-IN-MadhurNeural (male), hi-IN-SwaraNeural (female)
  English: en-US-GuyNeural, en-GB-RyanNeural (BBC style), en-US-JennyNeural
  List all: python3 generate_voiceover.py --list-voices ur
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys


def audio_duration(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def tts_edge(text, voice, out, rate="-5%"):
    import edge_tts

    async def run():
        c = edge_tts.Communicate(text, voice, rate=rate)
        await c.save(out)

    asyncio.run(run())
    return os.path.exists(out) and os.path.getsize(out) > 1000


def tts_gtts(text, lang, out):
    from gtts import gTTS
    gTTS(text=text, lang=lang, slow=False).save(out)
    return os.path.exists(out) and os.path.getsize(out) > 1000


def synth(text, voice, out, rate="-5%"):
    """Try edge-tts, fall back to gTTS."""
    try:
        if tts_edge(text, voice, out, rate):
            return "edge-tts"
    except Exception as e:
        print(f"[warn] edge-tts failed: {e}", file=sys.stderr)
    lang = voice.split("-")[0] if "-" in voice else "en"
    try:
        if tts_gtts(text, lang, out):
            return "gtts"
    except Exception as e:
        print(f"[error] gTTS also failed: {e}", file=sys.stderr)
    return None


def fmt_ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(entries, path):
    """entries: [{'start':s,'end':e,'text':t}]"""
    with open(path, "w", encoding="utf-8") as f:
        for i, e in enumerate(entries, 1):
            f.write(f"{i}\n{fmt_ts(e['start'])} --> {fmt_ts(e['end'])}\n{e['text'].strip()}\n\n")


def split_for_subs(text, max_chars=80):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--scenes", help="scenes.json with per-scene narration")
    ap.add_argument("--voice", default="en-US-GuyNeural")
    ap.add_argument("--rate", default="-5%", help="speech rate adjust (edge-tts), e.g. -10%%")
    ap.add_argument("--out", default="voiceover.mp3")
    ap.add_argument("--outdir", default="voiceover")
    ap.add_argument("--list-voices", metavar="LANGPREFIX")
    args = ap.parse_args()

    if args.list_voices:
        import edge_tts
        voices = asyncio.run(edge_tts.list_voices())
        for v in voices:
            if v["ShortName"].lower().startswith(args.list_voices.lower()):
                print(f"{v['ShortName']:32s} {v['Gender']:8s} {v.get('FriendlyName','')}")
        return

    if args.scenes:
        scenes = json.load(open(args.scenes))
        os.makedirs(args.outdir, exist_ok=True)
        result, t = [], 0.0
        srt_entries = []
        for sc in scenes:
            sid, narr = sc.get("id"), (sc.get("narration") or "").strip()
            if not narr:
                continue
            out = os.path.join(args.outdir, f"scene_{sid}.mp3")
            eng = synth(narr, args.voice, out, args.rate)
            if not eng:
                sys.exit(f"[fatal] TTS failed for scene {sid}")
            dur = audio_duration(out)
            # subtitle lines proportional to length
            lines = split_for_subs(narr)
            total_chars = sum(len(l) for l in lines) or 1
            lt = t
            for l in lines:
                ld = dur * len(l) / total_chars
                srt_entries.append({"start": lt, "end": lt + ld, "text": l})
                lt += ld
            result.append({"scene_id": sid, "audio": out, "duration": round(dur, 3),
                           "start": round(t, 3), "engine": eng})
            t += dur
            print(f"[ok] scene {sid}: {out} ({dur:.1f}s via {eng})", file=sys.stderr)
        meta = os.path.join(args.outdir, "voiceover.json")
        json.dump(result, open(meta, "w"), indent=2, ensure_ascii=False)
        write_srt(srt_entries, os.path.join(args.outdir, "subtitles.srt"))
        print(meta)
        return

    text = args.text or (open(args.text_file, encoding="utf-8").read() if args.text_file else None)
    if not text:
        ap.error("--text, --text-file, or --scenes required")
    eng = synth(text, args.voice, args.out, args.rate)
    if not eng:
        sys.exit("[fatal] all TTS engines failed")
    dur = audio_duration(args.out)
    lines = split_for_subs(text)
    total = sum(len(l) for l in lines) or 1
    t, entries = 0.0, []
    for l in lines:
        ld = dur * len(l) / total
        entries.append({"start": t, "end": t + ld, "text": l})
        t += ld
    write_srt(entries, os.path.splitext(args.out)[0] + ".srt")
    print(json.dumps({"audio": args.out, "duration": dur, "engine": eng}, indent=2))


if __name__ == "__main__":
    main()
