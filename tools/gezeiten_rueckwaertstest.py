#!/usr/bin/env python3
"""Rückwärtstest der Gezeiten-Korrektur.

Frage: Wie genau sind die Hoch- und Niedrigwasser-Zeiten, wenn das Modell mit dem
Versatz der VORHERIGEN Tage korrigiert wird? Für jeden Tag D wird der Versatz nur aus
den Tagen davor berechnet und dann gegen die tatsächliche Messung an Tag D geprüft.

Aufruf:  python3 tools/gezeiten_rueckwaertstest.py [Pegel-ID] [Breite] [Länge]
Standard: Viana do Castelo (74-267) und die Küste bei Moledo.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gezeiten  # noqa: E402
import quellen  # noqa: E402

station = sys.argv[1] if len(sys.argv) > 1 else "74-267"
lat = float(sys.argv[2]) if len(sys.argv) > 2 else 41.851
lon = float(sys.argv[3]) if len(sys.argv) > 3 else -8.868
TAGE = 14

jetzt = datetime.now(timezone.utc)
ende = jetzt - timedelta(hours=30)          # geprüfte Werte haben etwa 1 Tag Verzögerung
start = ende - timedelta(days=TAGE)

print(f"Pegel {station}, Modellpunkt {lat}/{lon}, Zeitraum {start:%d.%m.} bis {ende:%d.%m.%Y}")
gez, gh = quellen.lies_pegel(quellen.hole_pegel(station, start, ende)["daten"])
mod = quellen.hole_tide_modell(lat, lon, vergangene_tage=TAGE + 3, tage=1)["daten"]
mz, mh = quellen.stundenreihe(mod, "sea_level_height_msl")
print(f"Messwerte: {len(gh)} (alle 5 Minuten), Modellwerte: {sum(v is not None for v in mh)} (stündlich)")

ext_g = gezeiten.finde_extrema(gez, gh, glaetten_min=25)
ext_m = gezeiten.finde_extrema(mz, mh)
ext_m = [e for e in ext_m if start <= e[1] <= ende]
print(f"Gefundene Hoch-/Niedrigwasser: gemessen {len(ext_g)}, Modell {len(ext_m)}\n")

# Rückwärtstest: je Tag Versatz aus den 3 Tagen davor
unkorr, korr, versatz_liste = [], [], []
tage = sorted({e[1].date() for e in ext_g})
for d in tage:
    t0 = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    vorher_g = [e for e in ext_g if t0 - timedelta(days=3) <= e[1] < t0]
    vorher_m = [e for e in ext_m if t0 - timedelta(days=3, hours=3) <= e[1] < t0 + timedelta(hours=3)]
    v = gezeiten.versatz_minuten(vorher_m, vorher_g)
    if v is None:
        continue
    off = v[0]
    for art, t, _ in [e for e in ext_g if t0 <= e[1] < t0 + timedelta(days=1)]:
        passend = [(abs((tm - t).total_seconds()), tm) for a, tm, _ in ext_m if a == art]
        if not passend:
            continue
        ab, tm = min(passend)
        if ab > 3 * 3600:
            continue
        roh = (tm - t).total_seconds() / 60
        unkorr.append(abs(roh))
        korr.append(abs(roh - off))
        versatz_liste.append(roh)

print(f"Geprüfte Hoch-/Niedrigwasser: {len(korr)}")
print(f"Modell ohne Korrektur:  mittlere Abweichung {mean(unkorr):5.1f} min, Median {median(unkorr):5.1f}, schlechtester {max(unkorr):5.1f}")
print(f"Modell mit Korrektur:   mittlere Abweichung {mean(korr):5.1f} min, Median {median(korr):5.1f}, schlechtester {max(korr):5.1f}")
anteil15 = sum(k <= 15 for k in korr) / len(korr) * 100
anteil30 = sum(k <= 30 for k in korr) / len(korr) * 100
print(f"Davon höchstens 15 min daneben: {anteil15:.0f} %, höchstens 30 min: {anteil30:.0f} %")
print(f"Versatz des Modells (Modell minus Messung): Mittel {mean(versatz_liste):+.0f} min, Spanne {min(versatz_liste):+.0f} bis {max(versatz_liste):+.0f} min")
