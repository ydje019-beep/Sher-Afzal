#!/usr/bin/env python3
"""
search_media.py — Search REAL (non-AI) archival images & videos for documentary videos.

Sources (all free/open, real historical media — NO AI-generated content):
  - Wikimedia Commons  (photos, paintings, maps, some video)
  - Internet Archive   (historical footage, newsreels, photos)
  - Library of Congress (historical photos, prints)
  - NASA Image Library (space/science media)
  - Openverse          (CC-licensed photos, aggregates Flickr/museums)

AI-content protection:
  - Only queries archival/historical collections (pre-dating generative AI or curated)
  - Filters out results whose title/description/tags mention AI generators
    (midjourney, stable diffusion, dall-e, "ai generated", etc.)

Usage:
  python3 search_media.py --query "partition of india 1947" --type images --limit 10
  python3 search_media.py --query "apollo 11" --type videos --limit 5 --source archive
  python3 search_media.py --scenes scenes.json --out media_plan.json

scenes.json format:
  [{"id": 1, "search_terms": ["mughal empire taj mahal", "shah jahan painting"], "narration": "..."}, ...]

Output: JSON list of candidates: {url, thumb, title, source, license, type, width, height}
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = "DocumentaryVideoCreator/1.0 (educational; archival media research)"

AI_BLOCKLIST = re.compile(
    r"(ai[\s\-_]?generated|midjourney|stable[\s\-_]?diffusion|dall[\s\-_·]?e|"
    r"generative\s*ai|text[\s\-_]?to[\s\-_]?image|artificial intelligence art|"
    r"neural network art|gan[\s\-_]?generated|sora[\s\-_]?video|firefly[\s\-_]?ai|"
    r"created with ai|made with ai|ai art|imagen|flux[\s\-_.]?(dev|pro|schnell))",
    re.IGNORECASE,
)


def _curl_json(url, timeout):
    """Fetch JSON via curl subprocess — some archives block python TLS fingerprints."""
    import subprocess
    r = subprocess.run(
        ["curl", "-sS", "-L", "--max-time", str(timeout),
         "-A", UA, "-H", "Accept: application/json",
         "-w", "\n%{http_code}", url],
        capture_output=True, text=True, timeout=timeout + 10)
    body, _, code = r.stdout.rpartition("\n")
    if r.returncode != 0 or not code.startswith("2"):
        raise urllib.error.HTTPError(url, int(code or 0), f"curl status {code}", {}, None)
    return json.loads(body)


def http_json(url, timeout=25, retries=3):
    last = None
    for attempt in range(retries):
        try:
            return _curl_json(url, timeout)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (403, 429, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)  # 2s, 4s backoff for rate limits
                continue
            raise
        except Exception as e:
            last = e
            if attempt < retries - 1:
                time.sleep(1.5)
                continue
            raise
    raise last


def is_ai_tainted(*texts):
    blob = " ".join(t or "" for t in texts)
    return bool(AI_BLOCKLIST.search(blob))


# ---------------------------------------------------------------- Wikimedia Commons
def search_wikimedia(query, media_type="images", limit=10):
    """Wikimedia Commons via MediaWiki API. media_type: images|videos"""
    ftype = "bitmap|drawing" if media_type == "images" else "video"
    api = (
        "https://commons.wikimedia.org/w/api.php?action=query&format=json"
        "&generator=search&gsrnamespace=6"
        f"&gsrsearch={urllib.parse.quote(query + ' filetype:' + ('video' if media_type=='videos' else 'bitmap'))}"
        f"&gsrlimit={min(limit*2,40)}"
        "&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=1600"
    )
    out = []
    try:
        data = http_json(api)
        pages = (data.get("query") or {}).get("pages") or {}
        for p in pages.values():
            ii = (p.get("imageinfo") or [{}])[0]
            mime = ii.get("mime", "")
            if media_type == "images" and not mime.startswith("image"):
                continue
            if media_type == "videos" and not mime.startswith("video"):
                continue
            meta = ii.get("extmetadata") or {}
            title = p.get("title", "")
            desc = (meta.get("ImageDescription") or {}).get("value", "")
            cats = (meta.get("Categories") or {}).get("value", "")
            if is_ai_tainted(title, desc, cats):
                continue
            lic = (meta.get("LicenseShortName") or {}).get("value", "unknown")
            out.append({
                "url": ii.get("url"),
                "thumb": ii.get("thumburl") or ii.get("url"),
                "title": re.sub(r"^File:", "", title),
                "source": "wikimedia_commons",
                "source_page": ii.get("descriptionurl", ""),
                "license": lic,
                "type": "video" if mime.startswith("video") else "image",
                "mime": mime,
                "width": ii.get("width", 0),
                "height": ii.get("height", 0),
            })
            if len(out) >= limit:
                break
    except Exception as e:
        print(f"[warn] wikimedia search failed: {e}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- Internet Archive
def search_archive_org(query, media_type="videos", limit=10):
    """Internet Archive advancedsearch. Great for historical footage/newsreels."""
    mt = "movies" if media_type == "videos" else "image"
    # require terms in title/subject for relevance (plain OR search returns noise)
    words = [w for w in re.split(r"\W+", query) if len(w) > 2]
    tq = " AND ".join(f'(title:"{w}" OR subject:"{w}" OR description:"{w}")' for w in words[:4])
    q = f'({tq}) AND mediatype:{mt} AND NOT collection:ai_generated'
    api = (
        "https://archive.org/advancedsearch.php?"
        f"q={urllib.parse.quote(q)}"
        "&fl[]=identifier&fl[]=title&fl[]=description&fl[]=licenseurl&fl[]=year&fl[]=downloads"
        f"&rows={min(limit*2,40)}&page=1&output=json&sort[]=downloads+desc"
    )
    out = []
    try:
        data = http_json(api)
        docs = (data.get("response") or {}).get("docs") or []
        for d in docs:
            title = d.get("title", "") if isinstance(d.get("title"), str) else " ".join(d.get("title") or [])
            desc = d.get("description", "")
            if isinstance(desc, list):
                desc = " ".join(str(x) for x in desc)
            if is_ai_tainted(title, str(desc)):
                continue
            ident = d.get("identifier")
            out.append({
                "url": f"https://archive.org/download/{ident}",  # resolved by download_media.py
                "archive_identifier": ident,
                "thumb": f"https://archive.org/services/img/{ident}",
                "title": title,
                "source": "internet_archive",
                "source_page": f"https://archive.org/details/{ident}",
                "license": d.get("licenseurl", "see item page"),
                "type": "video" if mt == "movies" else "image",
                "year": d.get("year"),
            })
            if len(out) >= limit:
                break
    except Exception as e:
        print(f"[warn] archive.org search failed: {e}", file=sys.stderr)
    return out


def resolve_archive_files(identifier, media_type="video", max_files=2):
    """List actual downloadable files inside an archive.org item."""
    exts_v = (".mp4", ".mpeg", ".mpg", ".avi", ".mov", ".webm", ".ogv")
    exts_i = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif")
    exts = exts_v if media_type == "video" else exts_i
    out = []
    try:
        data = http_json(f"https://archive.org/metadata/{identifier}")
        files = data.get("files") or []
        # prefer smaller mp4 derivatives for video
        cand = [f for f in files if f.get("name", "").lower().endswith(exts)]
        if media_type == "video":
            cand.sort(key=lambda f: (0 if f.get("name","").lower().endswith(".mp4") else 1,
                                     float(f.get("size", 1e12) or 1e12)))
        for f in cand[:max_files]:
            out.append(f"https://archive.org/download/{identifier}/{urllib.parse.quote(f['name'])}")
    except Exception as e:
        print(f"[warn] archive metadata failed for {identifier}: {e}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- Library of Congress
def search_loc(query, limit=10):
    """Library of Congress photos/prints (historical, public domain heavy)."""
    api = (
        f"https://www.loc.gov/photos/?q={urllib.parse.quote(query)}"
        f"&fo=json&c={min(limit*2,40)}"
    )
    out = []
    try:
        data = http_json(api)
        for item in data.get("results") or []:
            title = item.get("title", "")
            if is_ai_tainted(title, item.get("description", "") if isinstance(item.get("description"), str) else ""):
                continue
            urls = item.get("image_url") or []
            if not urls:
                continue
            best = urls[-1]
            if best.startswith("//"):
                best = "https:" + best
            out.append({
                "url": best,
                "thumb": ("https:" + urls[0]) if urls[0].startswith("//") else urls[0],
                "title": title,
                "source": "library_of_congress",
                "source_page": item.get("url", ""),
                "license": "see item page (mostly public domain)",
                "type": "image",
            })
            if len(out) >= limit:
                break
    except Exception as e:
        print(f"[warn] loc search failed: {e}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- NASA
def search_nasa(query, media_type="images", limit=10):
    mt = "image" if media_type == "images" else "video"
    api = f"https://images-api.nasa.gov/search?q={urllib.parse.quote(query)}&media_type={mt}"
    out = []
    try:
        data = http_json(api)
        items = ((data.get("collection") or {}).get("items") or [])[: limit * 2]
        for it in items:
            d = (it.get("data") or [{}])[0]
            title = d.get("title", "")
            if is_ai_tainted(title, d.get("description", "")):
                continue
            links = it.get("links") or []
            thumb = next((l["href"] for l in links if l.get("rel") == "preview"), None)
            nasa_id = d.get("nasa_id")
            out.append({
                "url": f"https://images-api.nasa.gov/asset/{nasa_id}",  # resolved on download
                "nasa_id": nasa_id,
                "thumb": thumb,
                "title": title,
                "source": "nasa",
                "source_page": f"https://images.nasa.gov/details/{nasa_id}",
                "license": "public domain (NASA)",
                "type": "video" if mt == "video" else "image",
            })
            if len(out) >= limit:
                break
    except Exception as e:
        print(f"[warn] nasa search failed: {e}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- Openverse
def search_openverse(query, limit=10):
    api = (
        f"https://api.openverse.org/v1/images/?q={urllib.parse.quote(query)}"
        f"&page_size={min(limit*2,40)}&license_type=commercial,modification"
    )
    out = []
    try:
        data = http_json(api)
        for r in data.get("results") or []:
            title = r.get("title", "")
            tags = " ".join(t.get("name", "") for t in (r.get("tags") or []) if isinstance(t, dict))
            if is_ai_tainted(title, tags, r.get("source", ""), r.get("creator", "")):
                continue
            # skip known AI-heavy sources
            if (r.get("source") or "").lower() in {"stocksnap", "nappy"}:
                pass
            out.append({
                "url": r.get("url"),
                "thumb": r.get("thumbnail") or r.get("url"),
                "title": title,
                "source": f"openverse:{r.get('source','')}",
                "source_page": r.get("foreign_landing_url", ""),
                "license": r.get("license", "") + " " + (r.get("license_version") or ""),
                "type": "image",
                "width": r.get("width") or 0,
                "height": r.get("height") or 0,
            })
            if len(out) >= limit:
                break
    except Exception as e:
        print(f"[warn] openverse search failed: {e}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- Orchestrator
SOURCES = {
    "wikimedia": lambda q, t, n: search_wikimedia(q, t, n),
    "archive": lambda q, t, n: search_archive_org(q, t, n),
    "loc": lambda q, t, n: search_loc(q, n) if t == "images" else [],
    "nasa": lambda q, t, n: search_nasa(q, t, n),
    "openverse": lambda q, t, n: search_openverse(q, n) if t == "images" else [],
}

DEFAULT_ORDER_IMAGES = ["wikimedia", "loc", "openverse", "nasa"]
DEFAULT_ORDER_VIDEOS = ["archive", "wikimedia", "nasa"]


def search_all(query, media_type="images", limit=10, sources=None):
    order = sources or (DEFAULT_ORDER_IMAGES if media_type == "images" else DEFAULT_ORDER_VIDEOS)
    results, seen = [], set()
    per = max(2, limit // len(order) + 1)
    for s in order:
        fn = SOURCES.get(s)
        if not fn:
            continue
        for r in fn(query, media_type, per):
            key = r.get("url") or r.get("archive_identifier")
            if key and key not in seen:
                seen.add(key)
                results.append(r)
        time.sleep(1.0)  # be polite between sources (avoids rate limits)
        if len(results) >= limit:
            break
    return results[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query")
    ap.add_argument("--type", choices=["images", "videos"], default="images")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--source", choices=list(SOURCES), action="append")
    ap.add_argument("--scenes", help="scenes.json file (batch mode)")
    ap.add_argument("--out", help="output JSON file (default stdout)")
    ap.add_argument("--resolve-archive", help="resolve files for an archive.org identifier")
    args = ap.parse_args()

    if args.resolve_archive:
        print(json.dumps(resolve_archive_files(args.resolve_archive, "video"), indent=2))
        return

    if args.scenes:
        scenes = json.load(open(args.scenes))
        plan = []
        for sc in scenes:
            cands = []
            for term in sc.get("search_terms", [])[:3]:
                cands += search_all(term, "images", 4, args.source)
                cands += search_all(term, "videos", 2, args.source)
                time.sleep(1.0)
            # dedupe
            seen, uniq = set(), []
            for c in cands:
                k = c.get("url")
                if k not in seen:
                    seen.add(k)
                    uniq.append(c)
            plan.append({"scene_id": sc.get("id"), "narration": sc.get("narration", ""),
                         "candidates": uniq})
            print(f"[info] scene {sc.get('id')}: {len(uniq)} candidates", file=sys.stderr)
        payload = json.dumps(plan, indent=2, ensure_ascii=False)
    else:
        if not args.query:
            ap.error("--query or --scenes required")
        res = search_all(args.query, args.type, args.limit, args.source)
        payload = json.dumps(res, indent=2, ensure_ascii=False)

    if args.out:
        open(args.out, "w").write(payload)
        print(f"[ok] written {args.out}", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
