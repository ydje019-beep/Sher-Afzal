#!/usr/bin/env python3
"""
build_timeline.py — Merge shotlist.json + per-scene narration audio + prepared images
into timeline.json for render_video.py.

Expects:
  shotlist.json            {"scenes":[{"id":1,"narration":"...","motion":"zoom_in",...}]}
  audio/scene_001.mp3      per-scene narration audio (id-matched, zero-padded 3)
  images/final/scene_001.jpg   prepared 1920x1080 visual (id-matched)

Usage:
  python3 build_timeline.py --shotlist script/shotlist.json --audio-dir audio \
      --image-dir images/final --out script/timeline.json [--pad 0.8]
"""
import argparse, json, os, subprocess, sys

MOTIONS = ["zoom_in", "zoom_out", "pan_lr", "pan_rl"]


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shotlist", required=True)
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--image-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pad", type=float, default=0.8)
    a = ap.parse_args()

    scenes = json.load(open(a.shotlist))["scenes"]
    timeline, missing = [], []
    for i, sc in enumerate(scenes):
        sid = sc["id"]
        img = os.path.join(a.image_dir, f"scene_{sid:03d}.jpg")
        aud = os.path.join(a.audio_dir, f"scene_{sid:03d}.mp3")
        if not os.path.exists(img):
            missing.append(img); continue
        if not os.path.exists(aud):
            missing.append(aud); continue
        d = dur(aud) + a.pad
        motion = sc.get("motion") or MOTIONS[i % len(MOTIONS)]
        timeline.append({"id": sid, "image": img, "audio": aud,
                         "duration": round(d, 3), "motion": motion,
                         "chapter": sc.get("chapter", ""),
                         "narration": sc.get("narration", "")[:100]})
    if missing:
        print("MISSING ASSETS:\n" + "\n".join(missing), file=sys.stderr)
        sys.exit(2)
    json.dump({"scenes": timeline}, open(a.out, "w"), indent=1)
    total = sum(s["duration"] for s in timeline)
    print(f"OK {a.out}: {len(timeline)} scenes, total {total:.1f}s ({total/60:.1f} min)")


if __name__ == "__main__":
    main()
