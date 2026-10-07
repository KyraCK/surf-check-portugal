#!/usr/bin/env python3
"""Ein Befehl für alles: Daten holen, auswerten, Seite bauen.

    python3 aktualisieren.py              holt neue Daten und baut docs/index.html
    python3 aktualisieren.py --ohne-abruf baut die Seite nur neu (z. B. nach einer Regel-Änderung)

Danach die Datei docs/index.html im Browser öffnen.
"""
import sys

import build
import fetch


def main() -> int:
    if "--ohne-abruf" not in sys.argv:
        stand = fetch.main()
        if stand == 1:  # Konfigurationsfehler: nicht weitermachen
            return 1
        print()
    return build.main()


if __name__ == "__main__":
    sys.exit(main())
