#!/usr/bin/env python3
"""Build documentary clips with aspect-aware framing.

Portrait/square paintings (the majority of 17th-century archival art) are
letterboxed onto a blurred, zoomed copy of themselves so the whole artwork
(especially faces) stays visible, with a slow Ken Burns push on the subject.
Landscape images fill the frame with a classic Ken Burns pan/zoom.
"""
import json, math, os, subprocess, sys

W, H = 1920, 1080
FPS = 30
OUT = "work/clips"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:], file=sys.stderr)
        raise RuntimeError("ffmpeg failed: " + " ".join(cmd[:8]))


def clip_filter(w, h, dur, style):
    """Return ffmpeg filter chain for one still image."""
    frames = max(int(dur * FPS), 1)
    ar = w / h
    target = W / H

    if ar >= target * 0.97:
        # --- Landscape: fill frame, Ken Burns pan+zoom ---
        # pre-scale so the image is comfortably larger than the frame
        base_w, base_h = W * 2, H * 2
        zmax = 1.18
        if style % 3 == 0:      # zoom in, centre
            z = f"1+({zmax}-1)*on/{frames}"
            x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif style % 3 == 1:    # zoom out, centre
            z = f"{zmax}-({zmax}-1)*on/{frames}"
            x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        else:                   # slow pan left->right at slight zoom
            z = f"1.10+0.05*on/{frames}"
            x = f"(iw-iw/zoom)*on/{frames}"
            y = "ih/2-(ih/zoom/2)"
        return (
            f"scale={base_w}:{base_h}:force_original_aspect_ratio=increase,"
            f"crop={base_w}:{base_h},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
            f"setsar=1"
        )

    # --- Portrait / square: blurred backdrop + full artwork in front ---
    # foreground height with a small margin, gentle vertical Ken Burns push
    fg_h = int(H * 0.94)
    fg_w = int(fg_h * ar)
    if fg_w > int(W * 0.86):
        fg_w = int(W * 0.86)
        fg_h = int(fg_w / ar)
    fg_w -= fg_w % 2
    fg_h -= fg_h % 2

    # zoompan on the foreground: subtle push in/out (keeps faces readable)
    if style % 2 == 0:
        z = f"1+0.07*on/{frames}"
    else:
        z = f"1.07-0.07*on/{frames}"

    return (
        # background: blow up + blur + darken
        f"split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},gblur=sigma=42,eq=brightness=-0.16:saturation=0.7,"
        f"zoompan=z='1.04+0.04*on/{frames}':x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1[bgo];"
        # foreground: full artwork, slow push
        f"[fg]scale={fg_w*2}:{fg_h*2},"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={fg_w}x{fg_h}:fps={FPS},setsar=1[fgo];"
        # composite centred
        f"[bgo][fgo]overlay=(W-w)/2:(H-h)/2:format=auto,setsar=1"
    )


def main():
    os.makedirs(OUT, exist_ok=True)
    man = json.load(open("assets/manifest.json"))
    vo = {s["scene_id"]: s for s in json.load(open("voiceover/voiceover.json"))}

    idx = 0
    listing = []
    for s in man:
        sid = s["scene_id"]
        media = s["media"]
        if not media:
            print(f"[warn] scene {sid} has no media", file=sys.stderr)
            continue
        total = vo[sid]["duration"]
        per = total / len(media)

        for j, mm in enumerate(media):
            dur = per
            # last clip of the scene absorbs rounding remainder
            if j == len(media) - 1:
                dur = total - per * (len(media) - 1)
            dur = max(dur, 1.2)

            out = f"{OUT}/clip_{idx:03d}.mp4"
            listing.append(out)
            if os.path.exists(out) and os.path.getsize(out) > 10000:
                print(f"[skip] {out} exists", flush=True)
                idx += 1
                continue

            vf = clip_filter(mm["width"], mm["height"], dur, idx)
            # fade in/out on every clip for smooth transitions
            fo = max(dur - 0.5, 0)
            vf += f",fade=t=in:st=0:d=0.5,fade=t=out:st={fo:.2f}:d=0.5"

            cmd = ["ffmpeg", "-y", "-v", "error",
                   "-loop", "1", "-t", f"{dur:.3f}", "-i", mm["file"],
                   "-filter_complex", vf,
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                   "-pix_fmt", "yuv420p", "-r", str(FPS),
                   "-t", f"{dur:.3f}", out]
            kind = "portrait" if mm["width"] / mm["height"] < W / H * 0.97 else "landscape"
            print(f"[build] scene {sid} clip {idx} ({dur:.1f}s, {kind})", flush=True)
            run(cmd)
            idx += 1

    with open("work/clips.txt", "w") as f:
        for c in listing:
            f.write(f"file '{os.path.abspath(c)}'\n")
    print(f"\n{len(listing)} clips -> work/clips.txt")


if __name__ == "__main__":
    main()
