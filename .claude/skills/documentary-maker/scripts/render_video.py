#!/usr/bin/env python3
"""
render_video.py — Final documentary renderer.
Per scene: Ken Burns zoompan on the still + that scene's narration audio.
Then: chain scenes with 1.0s video crossfades (NO hard cuts), overlay music bed
at low level, fade in/out, output 1920x1080 30fps H.264.

Usage:
  python3 render_video.py --timeline script/timeline.json \
      [--music audio/music_main.mp3] [--out output/documentary.mp4] \
      [--workdir segments] [--xfade 1.0] [--music-db -22]
"""
import argparse, json, os, subprocess, sys

FPS = 30
W, H = 1920, 1080


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:], file=sys.stderr)
        sys.exit(f"FFMPEG FAILED: {' '.join(cmd[:8])}...")
    return r


def kenburns_filter(motion, dur_s):
    frames = int(dur_s * FPS)
    z_max = 1.12
    zoom_step = (z_max - 1.0) / max(frames, 1)
    if motion == "zoom_in":
        z = f"min(zoom+{zoom_step:.6f},{z_max})"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "zoom_out":
        z = f"max({z_max}-{zoom_step:.6f}*on,1.0)"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "pan_lr":
        z = "1.10"
        x, y = f"(iw-iw/zoom)*on/{max(frames,1)}", "ih/2-(ih/zoom/2)"
    elif motion == "pan_rl":
        z = "1.10"
        x, y = f"(iw-iw/zoom)*(1-on/{max(frames,1)})", "ih/2-(ih/zoom/2)"
    elif motion == "pan_up":
        z = "1.10"
        x, y = "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-on/{max(frames,1)})"
    else:  # pan_down / fallback
        z = "1.10"
        x, y = "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*on/{max(frames,1)}"
    # upscale first so zoompan is smooth (reduces jitter)
    return (f"scale=3840:2160:flags=lanczos,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
            f"format=yuv420p")


def render_scene(sc, workdir, xfade):
    out = os.path.join(workdir, f"seg_{sc['id']:03d}.mp4")
    dur = sc["duration"] + xfade  # extra tail consumed by crossfade overlap
    vf = kenburns_filter(sc["motion"], dur)
    # narration padded with silence tail so audio never truncates
    run(["ffmpeg", "-y", "-v", "error",
         "-loop", "1", "-t", f"{dur:.3f}", "-i", sc["image"],
         "-i", sc["audio"],
         "-filter_complex",
         f"[0:v]{vf}[v];[1:a]apad=pad_dur={xfade+1.5:.2f},atrim=0:{dur:.3f},"
         f"aformat=sample_rates=44100:channel_layouts=stereo[a]",
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.3f}", out])
    return out, dur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--music", default=None)
    ap.add_argument("--out", default="output/documentary.mp4")
    ap.add_argument("--workdir", default="segments")
    ap.add_argument("--xfade", type=float, default=1.0)
    ap.add_argument("--music-db", type=float, default=-22.0)
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    scenes = json.load(open(a.timeline))["scenes"]
    segs = []
    for sc in scenes:
        seg, dur = render_scene(sc, a.workdir, a.xfade)
        segs.append((seg, dur))
        print(f"rendered scene {sc['id']:03d} ({dur:.1f}s) [{sc['motion']}]")

    # ---- crossfade chain (video xfade + audio acrossfade) ----
    inputs = []
    for s, _ in segs:
        inputs += ["-i", s]
    fc, vprev, aprev = [], "0:v", "0:a"
    offset = 0.0
    for i in range(1, len(segs)):
        offset += segs[i-1][1] - a.xfade
        vo, ao = f"v{i}", f"a{i}"
        fc.append(f"[{vprev}][{i}:v]xfade=transition=fade:duration={a.xfade}:offset={offset:.3f}[{vo}]")
        fc.append(f"[{aprev}][{i}:a]acrossfade=d={a.xfade}[{ao}]")
        vprev, aprev = vo, ao
    total = offset + segs[-1][1]

    # fades at head/tail
    fc.append(f"[{vprev}]fade=t=in:st=0:d=1,fade=t=out:st={total-2:.2f}:d=2[vfinal]")

    if a.music:
        inputs += ["-stream_loop", "-1", "-i", a.music]
        mi = len(segs)
        fc.append(f"[{mi}:a]volume={a.music_db}dB,atrim=0:{total:.3f},"
                  f"afade=t=in:st=0:d=3,afade=t=out:st={total-4:.2f}:d=4[mus]")
        fc.append(f"[{aprev}][mus]amix=inputs=2:duration=first:normalize=0[afinal]")
        amap = "[afinal]"
    else:
        amap = f"[{aprev}]"

    run(["ffmpeg", "-y", "-v", "error", *inputs,
         "-filter_complex", ";".join(fc),
         "-map", "[vfinal]", "-map", amap,
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
         "-t", f"{total:.3f}", a.out])
    sz = os.path.getsize(a.out) / 1e6
    print(f"DONE {a.out}: {total:.1f}s ({total/60:.1f} min), {sz:.1f} MB")


if __name__ == "__main__":
    main()
