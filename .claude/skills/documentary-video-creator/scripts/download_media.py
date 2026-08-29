#!/usr/bin/env python3
"""
download_media.py — Download & validate media selected from search_media.py results.

Features:
  - Handles direct URLs, archive.org identifiers (resolves best mp4/jpg),
    and NASA asset endpoints (resolves manifest).
  - Validates downloads with ffprobe (rejects corrupt/HTML error pages).
  - Rejects tiny images (< 400px wide) unsuitable for HD video.
  - Writes a manifest.json mapping scene -> local files (with attribution).

Usage:
  # download a media plan (from search_media.py --scenes)
  python3 download_media.py --plan media_plan.json --outdir assets --per-scene 3

  # download a single URL
  python3 download_media.py --url "https://..." --outdir assets
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

UA = "DocumentaryVideoCreator/1.0 (educational; archival media research)"
MIN_IMAGE_WIDTH = 400
MAX_VIDEO_MB = 300


def http_json(url, timeout=25):
    """JSON via curl — some archives block python TLS fingerprints."""
    r = subprocess.run(
        ["curl", "-sS", "-L", "--max-time", str(timeout), "-A", UA,
         "-H", "Accept: application/json", "-w", "\n%{http_code}", url],
        capture_output=True, text=True, timeout=timeout + 10)
    body, _, code = r.stdout.rpartition("\n")
    if r.returncode != 0 or not code.startswith("2"):
        raise ValueError(f"HTTP {code} for {url}")
    return json.loads(body)


def safe_name(s, maxlen=60):
    s = re.sub(r"[^\w\-.]+", "_", s)[:maxlen].strip("_")
    return s or "media"


def download(url, dest, timeout=300):
    """Download via curl with size cap and content-type check."""
    r = subprocess.run(
        ["curl", "-sS", "-L", "--max-time", str(timeout), "-A", UA,
         "--max-filesize", str(MAX_VIDEO_MB * 1024 * 1024),
         "-o", dest, "-w", "%{http_code} %{content_type}", url],
        capture_output=True, text=True, timeout=timeout + 15)
    parts = (r.stdout or "").strip().split(" ", 1)
    code = parts[0] if parts else "0"
    ctype = parts[1] if len(parts) > 1 else ""
    if r.returncode != 0 or not code.startswith("2"):
        raise ValueError(f"HTTP {code} / curl rc={r.returncode}: {url}")
    if "text/html" in ctype:
        raise ValueError(f"got HTML instead of media: {url}")
    if not os.path.exists(dest) or os.path.getsize(dest) < 1024:
        raise ValueError(f"empty/too-small download: {url}")
    return dest


def ffprobe(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=60)
        return json.loads(out.stdout or "{}")
    except Exception:
        return {}


def validate(path, expect_type):
    info = ffprobe(path)
    streams = info.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v:
        return None
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    dur = float((info.get("format") or {}).get("duration") or 0)
    kind = "video" if (dur > 0.5 and v.get("codec_name") not in ("mjpeg", "png")) else "image"
    if expect_type == "image" and w < MIN_IMAGE_WIDTH:
        return None
    return {"width": w, "height": h, "duration": dur, "kind": kind}


def resolve_url(cand):
    """Return list of concrete downloadable URLs for a candidate."""
    src = cand.get("source", "")
    if src == "internet_archive" and cand.get("archive_identifier"):
        ident = cand["archive_identifier"]
        mt = cand.get("type", "video")
        exts = (".mp4", ".ogv", ".webm") if mt == "video" else (".jpg", ".jpeg", ".png")
        try:
            data = http_json(f"https://archive.org/metadata/{ident}")
            files = [f for f in (data.get("files") or [])
                     if f.get("name", "").lower().endswith(exts)]
            files.sort(key=lambda f: (0 if f.get("name", "").lower().endswith(exts[0]) else 1,
                                      float(f.get("size") or 1e12)))
            return [f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"
                    for f in files[:2]]
        except Exception as e:
            print(f"[warn] archive resolve failed {ident}: {e}", file=sys.stderr)
            return []
    if src == "nasa" and cand.get("nasa_id"):
        try:
            data = http_json(f"https://images-api.nasa.gov/asset/{cand['nasa_id']}")
            items = [i.get("href", "") for i in ((data.get("collection") or {}).get("items") or [])]
            pref = [u for u in items if u.lower().endswith(("~medium.mp4", "~mobile.mp4", "~orig.jpg", "~large.jpg"))]
            return (pref or items)[:2]
        except Exception:
            return []
    return [cand.get("url")] if cand.get("url") else []


def ext_from_url(url, fallback="bin"):
    path = urllib.parse.urlparse(url).path
    m = re.search(r"\.(\w{2,4})$", path)
    return m.group(1).lower() if m else fallback


def fetch_candidate(cand, outdir, idx):
    for url in resolve_url(cand):
        ext = ext_from_url(url, "jpg" if cand.get("type") == "image" else "mp4")
        name = f"{idx:02d}_{safe_name(cand.get('title','media'))}.{ext}"
        dest = os.path.join(outdir, name)
        try:
            download(url, dest)
            meta = validate(dest, cand.get("type", "image"))
            if not meta:
                os.remove(dest)
                print(f"[skip] invalid/too small: {url}", file=sys.stderr)
                continue
            return {
                "file": dest, **meta,
                "title": cand.get("title", ""),
                "source": cand.get("source", ""),
                "source_page": cand.get("source_page", ""),
                "license": cand.get("license", ""),
                "original_url": url,
            }
        except Exception as e:
            print(f"[skip] download failed {url}: {e}", file=sys.stderr)
            if os.path.exists(dest):
                os.remove(dest)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", help="media_plan.json from search_media.py --scenes")
    ap.add_argument("--url", help="single direct URL")
    ap.add_argument("--outdir", default="assets")
    ap.add_argument("--per-scene", type=int, default=3)
    ap.add_argument("--manifest", default=None, help="output manifest path")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    if args.url:
        res = fetch_candidate({"url": args.url, "type": "image", "title": "manual"},
                              args.outdir, 0)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    if not args.plan:
        ap.error("--plan or --url required")

    plan = json.load(open(args.plan))
    manifest = []
    counter = 0
    for scene in plan:
        sid = scene.get("scene_id")
        sdir = os.path.join(args.outdir, f"scene_{sid}")
        os.makedirs(sdir, exist_ok=True)
        got = []
        seen_titles = set()
        for cand in scene.get("candidates", []):
            if len(got) >= args.per_scene:
                break
            # skip near-duplicate items (same photo in different formats)
            tkey = re.sub(r"\.\w{2,4}$", "", (cand.get("title") or "").lower())[:50]
            if tkey and tkey in seen_titles:
                continue
            seen_titles.add(tkey)
            counter += 1
            r = fetch_candidate(cand, sdir, counter)
            if r:
                got.append(r)
                print(f"[ok] scene {sid}: {r['file']} ({r['kind']} {r['width']}x{r['height']})",
                      file=sys.stderr)
        manifest.append({"scene_id": sid, "narration": scene.get("narration", ""), "media": got})

    mpath = args.manifest or os.path.join(args.outdir, "manifest.json")
    json.dump(manifest, open(mpath, "w"), indent=2, ensure_ascii=False)
    print(f"[done] manifest -> {mpath}", file=sys.stderr)
    print(mpath)


if __name__ == "__main__":
    main()
