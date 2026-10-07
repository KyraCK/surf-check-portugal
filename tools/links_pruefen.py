#!/usr/bin/env python3
"""Prüft, ob alle Links in den Konfigurationsdateien noch erreichbar sind.

Aufruf:  python3 tools/links_pruefen.py
Seiten, die Programme aussperren (Fehler 403), gelten als "nicht prüfbar", nicht als kaputt.
"""
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

UA = "Mozilla/5.0 (Linkprüfung für ein privates Projekt)"


def sammle(cfg):
    links = {}
    for sid, s in cfg["spots"].items():
        for feld in ("quellen", "webcams", "vergleich"):
            for u in s.get(feld, []):
                links.setdefault(u, []).append(f"Spot {s['name']} ({feld})")
    for b in cfg["basen"]:
        for l in b.get("links", []):
            links.setdefault(l["url"], []).append(f"Basis {b['name']}")
    for z in cfg["ausfluege"]:
        if z.get("quelle"):
            links.setdefault(z["quelle"], []).append(f"Ausflug {z['name']}")
    return links


def pruefe(url):
    if "#" in url:
        url = url.split("#")[0]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"{type(e).__name__}"


def main():
    links = sammle(config.lade())
    with ThreadPoolExecutor(8) as pool:
        ergebnis = dict(zip(links, pool.map(pruefe, links)))
    ok = [u for u, s in ergebnis.items() if isinstance(s, int) and 200 <= s < 400]
    gesperrt = [u for u, s in ergebnis.items() if s in (401, 403, 429)]
    kaputt = {u: s for u, s in ergebnis.items() if u not in ok and u not in gesperrt}
    print(f"{len(links)} Links geprüft: {len(ok)} erreichbar, {len(gesperrt)} nicht prüfbar (Seite sperrt Programme), {len(kaputt)} kaputt.")
    for u in gesperrt:
        print("  nicht prüfbar:", u)
    for u, s in kaputt.items():
        print(f"  KAPUTT ({s}): {u}")
        for wo in links[u]:
            print("      verwendet in:", wo)
    return 1 if kaputt else 0


if __name__ == "__main__":
    sys.exit(main())
