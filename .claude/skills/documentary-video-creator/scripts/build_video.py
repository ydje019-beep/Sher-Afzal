#!/usr/bin/env python3
"""
build_video.py — Assemble a documentary video with FFmpeg.

Takes:  assets/manifest.json (from download_media.py)
        voiceover/voiceover.json + subtitles.srt (from generate_voiceover.py)
Makes:  1080p (or 4K/vertical) MP4 with:
        - Ken Burns (slow zoom/pan) on photos
        - real archival video clips trimmed to fit
        - fade transitions between clips
        - voiceover + optional background music (ducked)
        - burned-in subtitles (optional)
        - end credits with media attribution (optional)

Usage:
  python3 build_video.py \
      --manifest assets/manifest.json \
      --voiceover voiceover/voiceover.json \
      --subtitles voiceover/subtitles.srt \
      --music music.mp3 \
      --out documentary.mp4 \
      --resolution 1920x1080 --fps 30

  # vertical shorts:  --resolution 1080x1920
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

FADE = 0.5  # seconds fade in/out per clip


def run(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=quiet, text=True)
    if r.returncode != 0:
        print("[ffmpeg-error]", " ".join(cmd)[:400], file=sys.stderr)
        if quiet:
            print((r.stderr or "")[-2000:], file=sys.stderr)
        raise RuntimeError("ffmpeg failed")
    return r


def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


KB_MOVES = [
    "zoom-in-center", "zoom-out-center", "pan-left", "pan-right", "zoom-in-tl", "zoom-in-br",
]


def kenburns_clip(img, dur, w, h, fps, move, out):
    """Ken Burns from a still image. Upscale first to avoid zoompan jitter."""
    frames = max(int(dur * fps), fps)
    zmax = 1.18
    zstep = f"min(zoom+{(zmax-1)/frames:.6f},{zmax})"
    if move == "zoom-in-center":
        z, x, y = zstep, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif move == "zoom-out-center":
        z = f"max({zmax}-{(zmax-1)/frames:.6f}*on,1.0)"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif move == "pan-left":
        z, x, y = "1.15", f"(iw-iw/zoom)*(1-on/{frames})", "ih/2-(ih/zoom/2)"
    elif move == "pan-right":
        z, x, y = "1.15", f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)"
    elif move == "zoom-in-tl":
        z, x, y = zstep, "0", "0"
    else:  # zoom-in-br
        z, x, y = zstep, "iw-iw/zoom", "ih-ih/zoom"
    vf = (
        f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,"
        f"crop={w*2}:{h*2},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
        f"fade=t=in:st=0:d={FADE},fade=t=out:st={max(dur-FADE,0):.3f}:d={FADE},"
        f"format=yuv420p"
    )
    run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", f"{dur:.3f}",
         "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-an", out])


def video_clip(src, dur, w, h, fps, out):
    """Trim real archival footage to dur, letterbox/crop to frame, mute."""
    src_dur = probe_duration(src)
    start = max((src_dur - dur) * 0.25, 0) if src_dur > dur else 0
    t = min(dur, src_dur) if src_dur > 0.5 else dur
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"fps={fps},fade=t=in:st=0:d={FADE},fade=t=out:st={max(t-FADE,0):.3f}:d={FADE},"
        f"format=yuv420p"
    )
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", src, "-t", f"{t:.3f}",
           "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-an", out]
    run(cmd)
    # if archival clip shorter than needed, pad by holding last frame
    actual = probe_duration(out)
    if actual + 0.25 < dur:
        padded = out + ".pad.mp4"
        run(["ffmpeg", "-y", "-i", out, "-vf",
             f"tpad=stop_mode=clone:stop_duration={dur-actual:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", padded])
        shutil.move(padded, out)


def build_credits(manifest, w, h, fps, dur, out, tmpdir):
    """Simple attribution credits card."""
    lines = ["MEDIA CREDITS", ""]
    seen = set()
    for scene in manifest:
        for m in scene.get("media", []):
            src = m.get("source", "").replace("_", " ").title()
            t = (m.get("title") or "")[:60]
            key = (src, t)
            if key not in seen:
                seen.add(key)
                lines.append(f"{t} — {src}")
    txt = os.path.join(tmpdir, "credits.txt")
    open(txt, "w", encoding="utf-8").write("\n".join(lines[:30]))
    vf = (f"drawtext=textfile='{txt}':fontcolor=white:fontsize={int(h*0.028)}:"
          f"x=(w-text_w)/2:y=h-40*t:line_spacing={int(h*0.016)},format=yuv420p")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}",
         "-t", f"{dur:.3f}", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-an", out])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--voiceover", help="voiceover.json (per-scene) from generate_voiceover.py")
    ap.add_argument("--audio", help="single narration audio file (alternative to --voiceover)")
    ap.add_argument("--subtitles", help="SRT file to burn in")
    ap.add_argument("--music", help="background music file (will be ducked)")
    ap.add_argument("--music-volume", type=float, default=0.12)
    ap.add_argument("--out", default="documentary.mp4")
    ap.add_argument("--resolution", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--min-clip", type=float, default=3.0)
    ap.add_argument("--credits", action="store_true", help="append attribution credits")
    args = ap.parse_args()

    w, h = (int(x) for x in args.resolution.lower().split("x"))
    manifest = json.load(open(args.manifest))

    vo = {}
    if args.voiceover:
        for v in json.load(open(args.voiceover)):
            vo[v["scene_id"]] = v

    tmpdir = tempfile.mkdtemp(prefix="docvid_")
    clips, move_i = [], 0

    for scene in manifest:
        sid = scene.get("scene_id")
        media = [m for m in scene.get("media", []) if os.path.exists(m.get("file", ""))]
        if not media:
            print(f"[warn] scene {sid}: no media, skipping", file=sys.stderr)
            continue
        sdur = vo.get(sid, {}).get("duration") or max(args.min_clip * len(media), 6.0)
        per = max(sdur / len(media), args.min_clip)
        # last clip absorbs remainder so scene matches narration length
        durs = [per] * len(media)
        durs[-1] = max(sdur - per * (len(media) - 1), args.min_clip)
        for m, d in zip(media, durs):
            out = os.path.join(tmpdir, f"clip_{len(clips):03d}.mp4")
            try:
                if m.get("kind") == "video":
                    video_clip(m["file"], d, w, h, args.fps, out)
                else:
                    kenburns_clip(m["file"], d, w, h, args.fps,
                                  KB_MOVES[move_i % len(KB_MOVES)], out)
                    move_i += 1
                clips.append(out)
                print(f"[ok] scene {sid} clip {len(clips)} ({d:.1f}s, {m.get('kind')})",
                      file=sys.stderr)
            except Exception as e:
                print(f"[warn] clip failed for {m['file']}: {e}", file=sys.stderr)

    if not clips:
        sys.exit("[fatal] no clips built")

    if args.credits:
        cr = os.path.join(tmpdir, "credits.mp4")
        build_credits(manifest, w, h, args.fps, 6.0, cr, tmpdir)
        clips.append(cr)

    # concat
    lst = os.path.join(tmpdir, "list.txt")
    open(lst, "w").write("\n".join(f"file '{c}'" for c in clips))
    silent = os.path.join(tmpdir, "video_noaudio.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", silent])
    vdur = probe_duration(silent)

    # ---- audio track ----
    inputs, filters = [], []
    if args.voiceover:
        vo_list = sorted(vo.values(), key=lambda v: v.get("start", 0))
        concat_in = []
        for i, v in enumerate(vo_list):
            inputs += ["-i", v["audio"]]
            concat_in.append(f"[{i+1}:a]")
        filters.append("".join(concat_in) + f"concat=n={len(vo_list)}:v=0:a=1,apad[vo]")
        n_next = len(vo_list) + 1
    elif args.audio:
        inputs += ["-i", args.audio]
        filters.append("[1:a]apad[vo]")
        n_next = 2
    else:
        n_next = 1

    if args.music:
        inputs += ["-stream_loop", "-1", "-i", args.music]
        if n_next > 1:
            filters.append(
                f"[{n_next}:a]volume={args.music_volume},afade=t=out:st={max(vdur-3,0):.2f}:d=3[bg];"
                f"[vo][bg]amix=inputs=2:duration=shortest:dropout_transition=3,"
                f"atrim=0:{vdur:.2f}[aout]"
            )
        else:
            filters.append(
                f"[{n_next}:a]volume={args.music_volume},afade=t=out:st={max(vdur-3,0):.2f}:d=3,"
                f"atrim=0:{vdur:.2f}[aout]")
    elif n_next > 1:
        filters.append(f"[vo]atrim=0:{vdur:.2f}[aout]")

    # subtitles burn-in
    vf = None
    if args.subtitles and os.path.exists(args.subtitles):
        srt = args.subtitles.replace(":", r"\:").replace("'", r"\'")
        vf = (f"subtitles='{srt}':force_style="
              f"'FontSize={max(int(h*0.023),16)},PrimaryColour=&H00FFFFFF,"
              f"OutlineColour=&H80000000,Outline=2,MarginV={int(h*0.04)}'")

    cmd = ["ffmpeg", "-y", "-i", silent] + inputs
    fc = ";".join(filters) if filters else None
    if fc:
        cmd += ["-filter_complex", fc]
    if vf:
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "19"]
    else:
        cmd += ["-c:v", "copy"]
    if filters:
        cmd += ["-map", "0:v", "-map", "[aout]" if args.music or n_next > 1 else "0:a?"]
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-shortest", "-movflags", "+faststart", args.out]
    run(cmd)

    shutil.rmtree(tmpdir, ignore_errors=True)
    final = probe_duration(args.out)
    print(json.dumps({"output": args.out, "duration": round(final, 2),
                      "clips": len(clips), "resolution": args.resolution}))


if __name__ == "__main__":
    main()
