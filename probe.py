#!/usr/bin/env python3
"""Rechenprobe: Was ergeben deine Regeln bei einigen Beispiel-Bedingungen?

Aufruf im Ordner surf-check-portugal:
    python3 probe.py            (Spot Moledo)
    python3 probe.py afife      (anderer Spot, Name wie in config/spots.toml)

Nach jeder Änderung in config/scoring.toml oder config/spots.toml kannst du
das neu laufen lassen und siehst sofort, wie sich die Scores verschieben.
Die Beispiele sind erfunden und haben nichts mit der Vorhersage zu tun.
"""
import sys

import config
import score

# (Wellenhöhe laut Modell in m, Periode in s, Wind in kn, Windrichtung in Grad, Beschreibung)
SZENARIEN = [
    (0.6, 9, 4, 90, "0,6 m, 9 s, Ost 4 kn"),
    (0.8, 10, 5, 90, "0,8 m, 10 s, Ost 5 kn"),
    (1.0, 9, 5, 90, "1,0 m, 9 s, Ost 5 kn (glatt)"),
    (1.0, 11, 5, 90, "1,0 m, 11 s, Ost 5 kn (glatt)"),
    (1.2, 9, 6, 90, "1,2 m, 9 s, Ost 6 kn"),
    (1.2, 9, 12, 270, "1,2 m, 9 s, West 12 kn (auflandig)"),
    (1.2, 7, 6, 90, "1,2 m, 7 s, Ost 6 kn (kurze Periode)"),
    (1.5, 11, 8, 45, "1,5 m, 11 s, Nordost 8 kn"),
    (1.5, 11, 10, 0, "1,5 m, 11 s, Nord 10 kn (seitlich)"),
    (1.5, 8, 15, 225, "1,5 m, 8 s, Südwest 15 kn (auflandig)"),
    (2.0, 12, 5, 90, "2,0 m, 12 s, Ost 5 kn"),
    (2.8, 12, 10, 90, "2,8 m, 12 s, Ost 10 kn (groß)"),
]


def main() -> int:
    try:
        cfg = config.lade()
    except config.ConfigFehler as e:
        print("Fehler in der Konfiguration:\n  " + str(e))
        return 1
    spot_id = sys.argv[1] if len(sys.argv) > 1 else "moledo"
    if spot_id not in cfg["spots"]:
        print(f"Den Spot '{spot_id}' gibt es nicht. Vorhanden: {', '.join(cfg['spots'])}")
        return 1
    spot = cfg["spots"][spot_id]
    regeln = cfg["scoring"]
    personen = regeln["personen"]

    print(f"Rechenprobe für {spot['name']} (Korrekturfaktor {spot['korrekturfaktor']:g}, Swell aus 290 Grad, Tide mittig, Modell)")
    print("Skala: 1-3 lohnt kaum · 4-6 surfbar · 7-9 gut · 10 Pflichttermin\n")
    kopf = "".join(f"{p['label']:>10}" for p in personen.values())
    print(f"{'Beispiel':<40}{kopf}")
    print("-" * (40 + 10 * len(personen)))
    for hoehe, periode, wind, richtung, text in SZENARIEN:
        bed = {"hoehe_m": hoehe, "periode_s": periode, "swell_richtung": 290, "wind_kn": wind,
               "boeen_kn": wind, "wind_richtung": richtung, "tide_rel": 0.5, "tide_quelle": "modell"}
        zeile = ""
        for person in personen.values():
            r = score.bewerte(bed, spot, person, regeln)
            zeile += f"{r['punkte']:>10}"
        print(f"{text:<40}{zeile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
