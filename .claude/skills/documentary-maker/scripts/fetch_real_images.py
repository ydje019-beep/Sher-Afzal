#!/usr/bin/env python3
"""
fetch_real_images.py — Download REAL public-domain / CC archival images.
Sources: Wikimedia Commons API, Library of Congress API. NEVER AI-generated.

Usage:
  python3 fetch_real_images.py "Shadowbrook Lenox mansion" 5 ./images [--count 3] [--min-width 800]

Downloads best candidates to <out_dir>/scene_<id>_<n>.jpg and appends attribution
lines to <out_dir>/CREDITS.md. Prints a JSON summary to stdout.
"""
import argparse, json, os, re, sys, urllib.parse, urllib.request

UA = {"User-Agent": "DocumentaryMakerBot/1.0 (https://example.org/contact; research use)"}

BLOCK_PAT = re.compile(r"(getty|shutterstock|alamy|istock|adobe\s*stock)", re.I)
BAD_EXT = (".svg", ".gif", ".tif", ".tiff", ".pdf", ".webm", ".ogv", ".djvu")


def http_json(url, retries=2):
    import time
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def download(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    return os.path.getsize(path)


def search_commons(query, limit=12, min_width=700):
    """Wikimedia Commons file search with license + size metadata."""
    q = urllib.parse.quote(query)
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
           f"&generator=search&gsrsearch=filetype:bitmap%20{q}&gsrnamespace=6&gsrlimit={limit}"
           "&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=1600")
    try:
        data = http_json(url)
    except Exception as e:
        print(f"[commons] search error: {e}", file=sys.stderr)
        return []
    out = []
    for page in (data.get("query", {}).get("pages", {}) or {}).values():
        for ii in page.get("imageinfo", []):
            w, h = ii.get("width", 0), ii.get("height", 0)
            u = ii.get("thumburl") or ii.get("url", "")
            if w < min_width or not u or u.lower().endswith(BAD_EXT):
                continue
            meta = ii.get("extmetadata", {}) or {}
            lic = (meta.get("LicenseShortName", {}) or {}).get("value", "unknown")
            artist = re.sub(r"<[^>]+>", "", (meta.get("Artist", {}) or {}).get("value", "unknown"))[:120]
            title = page.get("title", "")
            if BLOCK_PAT.search(title + artist):
                continue
            out.append({"source": "Wikimedia Commons", "title": title, "url": u,
                        "page": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title)}",
                        "width": w, "height": h, "license": lic, "artist": artist.strip()})
    return out


def search_loc(query, limit=10, min_width=700):
    """Library of Congress photo search (public domain heavy)."""
    q = urllib.parse.quote(query)
    url = f"https://www.loc.gov/photos/?q={q}&fo=json&c={limit}"
    try:
        data = http_json(url)
    except Exception as e:
        print(f"[loc] search error: {e}", file=sys.stderr)
        return []
    out = []
    for item in data.get("results", []) or []:
        urls = item.get("image_url", []) or []
        if not urls:
            continue
        u = urls[-1]  # largest
        if u.startswith("//"):
            u = "https:" + u
        if u.lower().endswith(BAD_EXT):
            continue
        out.append({"source": "Library of Congress", "title": (item.get("title") or "")[:150],
                    "url": u, "page": item.get("url", ""), "width": 9999, "height": 9999,
                    "license": "See LOC rights", "artist": "LOC collection"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("scene_id", type=int)
    ap.add_argument("out_dir")
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--min-width", type=int, default=700)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    cands = search_commons(a.query, min_width=a.min_width)
    if len(cands) < a.count:
        cands += search_loc(a.query, min_width=a.min_width)
    # prefer larger images
    cands.sort(key=lambda c: -(c["width"] * min(c["height"], 4000)))

    saved, credits = [], []
    for c in cands:
        if len(saved) >= a.count:
            break
        n = len(saved) + 1
        path = os.path.join(a.out_dir, f"scene_{a.scene_id:03d}_{n}.jpg")
        try:
            size = download(c["url"], path)
            if size < 20_000:  # too small = junk
                os.remove(path)
                continue
            saved.append({"path": path, **c})
            credits.append(f"- scene {a.scene_id:03d}: **{c['title']}** — {c['source']}, "
                           f"license: {c['license']}, artist: {c['artist']}, page: {c['page']}")
        except Exception as e:
            print(f"[dl] failed {c['url'][:80]}: {e}", file=sys.stderr)

    if credits:
        with open(os.path.join(a.out_dir, "CREDITS.md"), "a") as f:
            f.write("\n".join(credits) + "\n")

    print(json.dumps({"scene_id": a.scene_id, "query": a.query,
                      "found": len(saved), "files": [s["path"] for s in saved],
                      "titles": [s["title"] for s in saved]}, indent=2))
    sys.exit(0 if saved else 3)


if __name__ == "__main__":
    main()
