#!/usr/bin/env python3
"""Targeted Wikimedia Commons fetcher with rate-limit backoff.

Downloads specific, curated Commons file titles per scene so every shot is
historically relevant. Real archival media only (paintings, engravings,
photographs) - no AI generation.
"""
import json, os, subprocess, sys, time, urllib.parse

UA = "DocumentaryBot/1.0 (https://example.org/docs; docs@example.org)"
API = "https://commons.wikimedia.org/w/api.php"

# Curated Commons file titles per scene (verified subjects for James VI & I)
CURATED = {
    1: [
        "Anoniem (Noordelijke Nederlanden) - Portrait of James I (1566-1625), King of England - 105 - Mauritshuis.jpg",
        "King James I of England and VI of Scotland by Arnold van Brounckhorst.jpg",
        "James I of England by Daniel Mytens.jpg",
    ],
    2: [
        "Edinburgh Castle during the 'Lang Siege' (May 1573).jpg",
        "Mary, Queen of Scots after Nicholas Hilliard.jpg",
        "Henry Stuart, Lord Darnley and Mary, Queen of Scots.jpg",
    ],
    3: [
        "Mary Queen of Scots Blairs Museum.jpg",
        "James VI of Scotland aged 8, 1574.jpg",
        "Stirling Castle - Chapel Royal.jpg",
    ],
    4: [
        "Stirling Castle Great Hall 2016.jpg",
        "The Great Hall, Stirling Castle - geograph.org.uk - 3212386.jpg",
        "James Douglas, 4th Earl of Morton.jpg",
    ],
    5: [
        "George Buchanan by Arnold Bronckorst.jpg",
        "Buchanan Rerum Scoticarum Historia 1582.jpg",
        "Basilikon Doron 1603.jpg",
    ],
    6: [
        "Huntingtower Castle - geograph.org.uk - 1732258.jpg",
        "William Ruthven, 1st Earl of Gowrie.jpg",
        "Falkland Palace - geograph.org.uk - 1543470.jpg",
    ],
    7: [
        "Execution of Mary, Queen of Scots.jpg",
        "Fotheringhay Castle 1690.jpg",
        "Elizabeth I in coronation robes.jpg",
    ],
    8: [
        "Anne of Denmark by Paul van Somer.jpg",
        "Anna of Denmark by Nicholas Hilliard.jpg",
        "Kronborg Castle Helsingor Denmark.jpg",
    ],
    9: [
        "Daemonologie.jpg",
        "Witches Newes from Scotland 1591.jpg",
        "The Trve Lawe of free Monarchies 1598.jpg",
    ],
    10: [
        "Elizabeth I funeral procession.jpg",
        "Richmond Palace 1765.jpg",
        "Visscher panorama of London, 1616.jpg",
    ],
    11: [
        "Flag of Great Britain (1707-1800).svg",
        "Union flag 1606 (Kings Colors).svg",
        "Royal Coat of Arms of the Kingdom of England (1603-1649).svg",
    ],
    12: [
        "Gunpowder Plot conspirators.jpg",
        "Guy Fawkes by Cruikshank.jpg",
        "Old Palace of Westminster.jpg",
    ],
    13: [
        "KJV-King-James-Version-Bible-first-edition-title-page-1611.jpg",
        "King James Version Bible first edition title page 1611.jpg",
        "Bible King James Version 1611 Genesis.jpg",
    ],
    14: [
        "Jamestown 1607.jpg",
        "Susan Constant, Godspeed and Discovery replicas.jpg",
        "Virginia and Maryland 1671.jpg",
    ],
    15: [
        "George Villiers, 1st Duke of Buckingham by Michiel Jansz van Miereveldt.jpg",
        "Somerset House Conference 1604.jpg",
        "James I of England 1621.jpg",
    ],
    16: [
        "Tomb of James I of England Westminster Abbey.jpg",
        "Charles I by Anthony van Dyck.jpg",
        "Westminster Abbey interior nave London.jpg",
    ],
}

# Fallback search queries when curated titles are unavailable
FALLBACK = {
    1: ["James VI and I portrait", "James I of England painting"],
    2: ["Mary Queen of Scots portrait", "Edinburgh Castle engraving", "Lord Darnley portrait"],
    3: ["James VI of Scotland child portrait", "Stirling Castle chapel", "Mary Queen of Scots abdication"],
    4: ["Stirling Castle great hall", "Earl of Morton regent portrait", "Scottish regent 16th century portrait"],
    5: ["George Buchanan portrait", "Basilikon Doron", "16th century Latin book Scotland"],
    6: ["Huntingtower Castle", "Earl of Gowrie portrait", "Ruthven Raid"],
    7: ["execution of Mary Queen of Scots engraving", "Fotheringhay Castle", "Elizabeth I portrait"],
    8: ["Anne of Denmark portrait", "Kronborg castle", "Stuart royal children portrait"],
    9: ["Daemonologie", "witch trial Scotland woodcut", "Newes from Scotland witchcraft"],
    10: ["Elizabeth I funeral", "Richmond Palace", "London 1616 panorama Visscher"],
    11: ["Union Jack 1606", "Kings Colours flag", "royal arms James I England"],
    12: ["Gunpowder Plot", "Guy Fawkes portrait", "Old Palace of Westminster"],
    13: ["King James Bible 1611 title page", "King James Bible Genesis page", "1611 Authorized Version"],
    14: ["Jamestown Virginia 1607", "Susan Constant ship replica", "colonial Virginia map 17th century"],
    15: ["Duke of Buckingham Villiers portrait", "Somerset House Conference", "James I England old portrait"],
    16: ["Westminster Abbey tomb James I", "Charles I van Dyck portrait", "Westminster Abbey nave"],
}


def api_get(params, tries=6):
    """Wikimedia API GET with exponential backoff on 429."""
    url = API + "?" + urllib.parse.urlencode(params)
    delay = 3
    for attempt in range(tries):
        r = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "40", "-H", f"User-Agent: {UA}",
             "-w", "\n%{http_code}", url],
            capture_output=True, text=True, timeout=60)
        out = r.stdout.rsplit("\n", 1)
        if len(out) == 2 and out[1].strip() == "200":
            try:
                return json.loads(out[0])
            except Exception:
                pass
        time.sleep(delay)
        delay = min(delay * 2, 40)
    return None


def imageinfo(titles):
    """Get direct file URLs + license for a list of File: titles."""
    res = {}
    for i in range(0, len(titles), 10):
        chunk = titles[i:i + 10]
        d = api_get({
            "action": "query", "format": "json",
            "titles": "|".join("File:" + t for t in chunk),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
        })
        if not d:
            continue
        for p in (d.get("query", {}).get("pages") or {}).values():
            if "missing" in p or not p.get("imageinfo"):
                continue
            ii = p["imageinfo"][0]
            em = ii.get("extmetadata", {})
            res[p["title"]] = {
                "title": p["title"].replace("File:", ""),
                "url": ii["url"],
                "width": ii.get("width"),
                "height": ii.get("height"),
                "mime": ii.get("mime", ""),
                "license": em.get("LicenseShortName", {}).get("value", "see source"),
                "artist": em.get("Artist", {}).get("value", ""),
                "source_page": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(p['title'].replace(' ', '_'))}",
            }
        time.sleep(1.5)
    return res


def search_files(query, limit=6):
    """Search Commons for image files matching a query."""
    d = api_get({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f'filetype:bitmap|drawing {query}',
        "gsrnamespace": "6", "gsrlimit": str(limit),
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
    })
    out = []
    if not d:
        return out
    for p in (d.get("query", {}).get("pages") or {}).values():
        if not p.get("imageinfo"):
            continue
        ii = p["imageinfo"][0]
        if (ii.get("width") or 0) < 700:
            continue
        # skip huge originals (TIFs etc) and non-raster formats
        if (ii.get("size") or 0) > 40_000_000:
            continue
        if ii.get("mime", "") not in ("image/jpeg", "image/png"):
            continue
        em = ii.get("extmetadata", {})
        out.append({
            "title": p["title"].replace("File:", ""),
            "url": ii["url"],
            "width": ii.get("width"),
            "height": ii.get("height"),
            "mime": ii.get("mime", ""),
            "license": em.get("LicenseShortName", {}).get("value", "see source"),
            "artist": em.get("Artist", {}).get("value", ""),
            "source_page": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(p['title'].replace(' ', '_'))}",
        })
    return out


def download(url, dest, tries=5):
    delay = 3
    for _ in range(tries):
        r = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "180", "-H", f"User-Agent: {UA}",
             "-o", dest, "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=220)
        if r.stdout.strip() == "200" and os.path.exists(dest) and os.path.getsize(dest) > 20000:
            return True
        time.sleep(delay)
        delay = min(delay * 2, 30)
    if os.path.exists(dest):
        os.remove(dest)
    return False


def valid_image(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    try:
        w, h = [int(x) for x in r.stdout.strip().split(",")[:2]]
        return w >= 600 and h >= 400
    except Exception:
        return False


def main():
    scenes = json.load(open("scenes.json"))
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    manifest = []

    for sc in scenes:
        sid = sc["id"]
        outdir = f"assets/scene_{sid}"
        os.makedirs(outdir, exist_ok=True)
        picked, seen = [], set()

        # 1) curated titles
        info = imageinfo(CURATED.get(sid, []))
        cands = [info[k] for k in info
                 if info[k].get("mime") in ("image/jpeg", "image/png")]

        # 2) fallback searches until we have enough candidates
        for q in FALLBACK.get(sid, []):
            if len(cands) >= want + 3:
                break
            for c in search_files(q, 6):
                if c["title"] not in {x["title"] for x in cands}:
                    cands.append(c)
            time.sleep(1.5)

        for c in cands:
            if len(picked) >= want or c["title"] in seen:
                continue
            seen.add(c["title"])
            ext = ".jpg" if "jpeg" in c["mime"] or c["title"].lower().endswith((".jpg", ".jpeg")) else \
                  ".png" if "png" in c["mime"] or c["title"].lower().endswith(".png") else ".jpg"
            safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in c["title"])[:70]
            dest = os.path.join(outdir, f"{len(picked):02d}_{safe}{ext}")
            print(f"[get] scene {sid}: {c['title'][:64]}", flush=True)
            if download(c["url"], dest) and valid_image(dest):
                picked.append({
                    "file": dest, "width": c["width"], "height": c["height"],
                    "duration": 0.04, "kind": "image", "title": c["title"],
                    "source": "wikimedia_commons", "source_page": c["source_page"],
                    "license": c["license"], "artist": c["artist"],
                    "original_url": c["url"],
                })
                print(f"  [ok] {dest}", flush=True)
            else:
                print("  [fail]", flush=True)
            time.sleep(1.0)

        print(f"=== scene {sid}: {len(picked)} images ===", flush=True)
        manifest.append({"scene_id": sid, "narration": sc["narration"], "media": picked})

    json.dump(manifest, open("assets/manifest_wiki.json", "w"), indent=1)
    tot = sum(len(s["media"]) for s in manifest)
    print(f"\nWROTE assets/manifest_wiki.json - {tot} images total")
    for s in manifest:
        if not s["media"]:
            print(f"  !! scene {s['scene_id']} EMPTY")


if __name__ == "__main__":
    main()
