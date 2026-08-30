#!/usr/bin/env python3
"""Replace wrong media in specific scenes with correct, verified Commons files."""
import json, os, subprocess, sys, time, urllib.parse

UA = "DocumentaryBot/1.0 (https://example.org/docs; docs@example.org)"
API = "https://commons.wikimedia.org/w/api.php"

# Scenes that got irrelevant matches -> exact replacement searches/titles
FIX = {
    5: {  # George Buchanan the Scottish scholar (NOT James Buchanan US president)
        "titles": [
            "George Buchanan by Arnold Bronckorst.jpg",
            "George Buchanan (1506-1582), by Arnold Bronckorst.jpg",
            "Basilikon Doron.jpg",
        ],
        "queries": ["George Buchanan humanist Scotland portrait",
                    "Buchanan Rerum Scoticarum Historia",
                    "Basilikon Doron King James"],
        "block": ["james buchanan", "president", "healy", "bep"],
    },
    6: {  # Ruthven Raid / Scottish castles - no modern group photos
        "titles": [
            "Huntingtower Castle, 2003.JPG",
            "Huntingtower north 17062009.jpg",
            "Falkland Palace.jpg",
        ],
        "queries": ["Huntingtower Castle Perthshire",
                    "Falkland Palace Fife",
                    "William Ruthven Earl of Gowrie"],
        "block": ["big brother", "executive", "group portrait of men"],
    },
    10: {  # Elizabeth I (1603) - NOT Elizabeth II (2022)
        "titles": [
            "Funeral procession of Elizabeth I William Camden Clarenceux 1603.jpg",
            "A View of Richmond Palace published in 1765.jpg",
            "Claes Van Visscher - Panorama of London (1616).jpg",
        ],
        "queries": ["funeral procession Elizabeth I 1603 engraving",
                    "Richmond Palace engraving 18th century",
                    "Visscher panorama London 1616"],
        "block": ["elizabeth ii", "2022", "attendance at the funeral"],
    },
    11: {  # 1606 Union flag - not modern Sydney re-enactments
        "titles": [
            "Union Jack 1606 Scotland (vertical).png",
            "Flag of Great Britain (1707-1800).svg.png",
            "Union flag 1606 (Kings Colors).png",
        ],
        "queries": ["Kings Colours union flag 1606",
                    "royal standard James I England arms",
                    "coat of arms James VI and I"],
        "block": ["sydney", "australia", "first union jack in"],
    },
    16: {  # James I tomb / Charles I - not a random Fullerton memorial
        "titles": [
            "Charles I of England by Anthony van Dyck.jpg",
            "Charles I by Sir Anthony Van Dyck.jpg",
            "Westminster Abbey - Nave.jpg",
        ],
        "queries": ["Charles I van Dyck portrait king",
                    "Westminster Abbey nave interior",
                    "Henry VII Lady Chapel Westminster Abbey"],
        "block": ["fullerton", "magdalen"],
    },
}


def api_get(params, tries=6):
    url = API + "?" + urllib.parse.urlencode(params)
    delay = 3
    for _ in range(tries):
        r = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "40", "-A", UA,
             "-w", "\n%{http_code}", url], capture_output=True, text=True, timeout=60)
        parts = r.stdout.rsplit("\n", 1)
        if len(parts) == 2 and parts[1].strip() == "200":
            try:
                return json.loads(parts[0])
            except Exception:
                pass
        time.sleep(delay); delay = min(delay * 2, 40)
    return None


def pack(p, blocked):
    if not p.get("imageinfo"):
        return None
    ii = p["imageinfo"][0]
    title = p["title"].replace("File:", "")
    low = title.lower()
    if any(b in low for b in blocked):
        return None
    if ii.get("mime") not in ("image/jpeg", "image/png"):
        return None
    if (ii.get("width") or 0) < 700 or (ii.get("size") or 0) > 40_000_000:
        return None
    em = ii.get("extmetadata", {})
    return {
        "title": title, "url": ii["url"],
        "width": ii.get("width"), "height": ii.get("height"),
        "mime": ii["mime"],
        "license": em.get("LicenseShortName", {}).get("value", "see source"),
        "artist": em.get("Artist", {}).get("value", ""),
        "source_page": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(p['title'].replace(' ', '_'))}",
    }


def by_titles(titles, blocked):
    if not titles:
        return []
    d = api_get({"action": "query", "format": "json",
                 "titles": "|".join("File:" + t for t in titles),
                 "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata"})
    out = []
    if d:
        for p in (d.get("query", {}).get("pages") or {}).values():
            if "missing" in p:
                continue
            c = pack(p, blocked)
            if c:
                out.append(c)
    return out


def by_query(q, blocked, limit=8):
    d = api_get({"action": "query", "format": "json", "generator": "search",
                 "gsrsearch": f"filetype:bitmap|drawing {q}", "gsrnamespace": "6",
                 "gsrlimit": str(limit), "prop": "imageinfo",
                 "iiprop": "url|size|mime|extmetadata"})
    out = []
    if d:
        for p in (d.get("query", {}).get("pages") or {}).values():
            c = pack(p, blocked)
            if c:
                out.append(c)
    return out


def download(url, dest, tries=5):
    delay = 3
    for _ in range(tries):
        r = subprocess.run(["curl", "-sS", "-L", "--max-time", "180", "-A", UA,
                            "-o", dest, "-w", "%{http_code}", url],
                           capture_output=True, text=True, timeout=220)
        if r.stdout.strip() == "200" and os.path.exists(dest) and os.path.getsize(dest) > 20000:
            return True
        time.sleep(delay); delay = min(delay * 2, 30)
    if os.path.exists(dest):
        os.remove(dest)
    return False


def valid(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        w, h = [int(x) for x in r.stdout.strip().split(",")[:2]]
        return w >= 600 and h >= 400
    except Exception:
        return False


def main():
    man = json.load(open("assets/manifest_wiki.json"))
    want = 3
    for s in man:
        sid = s["scene_id"]
        if sid not in FIX:
            continue
        cfg = FIX[sid]
        blocked = cfg["block"]

        # drop bad existing files
        keep = []
        for x in s["media"]:
            if any(b in x["title"].lower() for b in blocked):
                print(f"[drop] scene {sid}: {x['title'][:60]}", flush=True)
                if os.path.exists(x["file"]):
                    os.remove(x["file"])
            else:
                keep.append(x)

        have = {x["title"] for x in keep}
        cands = [c for c in by_titles(cfg["titles"], blocked) if c["title"] not in have]
        for q in cfg["queries"]:
            if len(keep) + len(cands) >= want + 2:
                break
            for c in by_query(q, blocked):
                if c["title"] not in have and c["title"] not in {x["title"] for x in cands}:
                    cands.append(c)
            time.sleep(1.5)

        outdir = f"assets/scene_{sid}"
        os.makedirs(outdir, exist_ok=True)
        idx = 90
        for c in cands:
            if len(keep) >= want:
                break
            safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in c["title"])[:70]
            ext = ".png" if c["mime"] == "image/png" else ".jpg"
            dest = os.path.join(outdir, f"{idx}_{safe}{ext}")
            idx += 1
            print(f"[get] scene {sid}: {c['title'][:64]}", flush=True)
            if download(c["url"], dest) and valid(dest):
                keep.append({"file": dest, "width": c["width"], "height": c["height"],
                             "duration": 0.04, "kind": "image", "title": c["title"],
                             "source": "wikimedia_commons", "source_page": c["source_page"],
                             "license": c["license"], "artist": c["artist"],
                             "original_url": c["url"]})
                print(f"  [ok] {dest}", flush=True)
            else:
                print("  [fail]", flush=True)
            time.sleep(1.0)

        s["media"] = keep
        print(f"=== scene {sid}: now {len(keep)} images ===", flush=True)

    json.dump(man, open("assets/manifest_wiki.json", "w"), indent=1)
    print("\nUPDATED manifest_wiki.json")
    for s in man:
        print(f"  scene {s['scene_id']:>2}: {len(s['media'])}")


if __name__ == "__main__":
    main()
