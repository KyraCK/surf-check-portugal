"""Gezeiten: Hoch- und Niedrigwasser finden, Modell mit dem Pegel abgleichen, Tide-Stand berechnen.

Die Vorhersage kommt von der Modellkurve (Open-Meteo `sea_level_height_msl`).
Ihr Zeitversatz wird gegen den gemessenen Pegel des Instituto Hidrográfico
bestimmt und herausgerechnet. Aus Hoch- und Niedrigwasser ergibt sich eine
Zahl von 0 (Niedrigwasser) bis 1 (Hochwasser) für jede Uhrzeit.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import median

MIN_HUB_M = 0.5          # kleinere Schwankungen zählen nicht als Hoch-/Niedrigwasser
FENSTER_H = 3.0          # ein Extrem muss im Umkreis von +-3 h das höchste/tiefste sein
FIT_H = 1.0              # Parabel-Anpassung mit Punkten +-1 h um das Extrem


def _glaetten(zeiten, werte, breite_min):
    """Gleitender Mittelwert über `breite_min` Minuten (entfernt Zittern im Hafen)."""
    if breite_min <= 0:
        return list(werte)
    halb = timedelta(minutes=breite_min / 2)
    aus, lo, hi, summe = [], 0, 0, 0.0
    n = len(zeiten)
    for i in range(n):
        while hi < n and zeiten[hi] <= zeiten[i] + halb:
            summe += werte[hi]
            hi += 1
        while zeiten[lo] < zeiten[i] - halb:
            summe -= werte[lo]
            lo += 1
        aus.append(summe / (hi - lo))
    return aus


def _parabel_scheitel(punkte):
    """Zeit des Scheitels (in Stunden relativ zum ersten Punkt) einer Ausgleichsparabel, oder None."""
    n = len(punkte)
    if n < 3:
        return None
    sx = sx2 = sx3 = sx4 = sy = sxy = sx2y = 0.0
    for x, y in punkte:
        sx += x; sx2 += x * x; sx3 += x ** 3; sx4 += x ** 4
        sy += y; sxy += x * y; sx2y += x * x * y
    # Normalgleichungen für y = a x^2 + b x + c
    m = [[sx4, sx3, sx2, sx2y], [sx3, sx2, sx, sxy], [sx2, sx, float(n), sy]]
    for i in range(3):
        piv = max(range(i, 3), key=lambda r: abs(m[r][i]))
        if abs(m[piv][i]) < 1e-12:
            return None
        m[i], m[piv] = m[piv], m[i]
        for r in range(3):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [a - f * b for a, b in zip(m[r], m[i])]
    a, b = m[0][3] / m[0][0], m[1][3] / m[1][1]
    if abs(a) < 1e-12:
        return None
    return -b / (2 * a)


def finde_extrema(zeiten, werte, glaetten_min=0):
    """Liste von (art, zeit, hoehe) mit art 'HW' oder 'NW', zeitlich aufsteigend.

    zeiten: aufsteigende, zeitzonenbewusste datetime; werte: Meter (None-Lücken erlaubt).
    """
    paare = [(t, v) for t, v in zip(zeiten, werte) if v is not None]
    if len(paare) < 5:
        return []
    zs = [t for t, _ in paare]
    vs = _glaetten(zs, [v for _, v in paare], glaetten_min)
    fenster = timedelta(hours=FENSTER_H)
    kandidaten = []
    lo = hi = 0
    n = len(zs)
    for i in range(n):
        while zs[lo] < zs[i] - fenster:
            lo += 1
        while hi < n and zs[hi] <= zs[i] + fenster:
            hi += 1
        # Am Rand fehlt die Hälfte des Fensters: dort nicht entscheiden
        if zs[i] - zs[0] < fenster or zs[-1] - zs[i] < fenster:
            continue
        seg = vs[lo:hi]
        if vs[i] == max(seg) and vs[i] - min(seg) >= MIN_HUB_M:
            kandidaten.append(("HW", i))
        elif vs[i] == min(seg) and max(seg) - vs[i] >= MIN_HUB_M:
            kandidaten.append(("NW", i))
    # Plateaus (gleich hohe Nachbarn) zusammenfassen
    roh = []
    for art, i in kandidaten:
        if roh and roh[-1][0] == art and zs[i] - zs[roh[-1][1]] < timedelta(hours=3):
            continue
        roh.append((art, i))
    aus = []
    for art, i in roh:
        t0 = zs[i]
        nah = [((zs[j] - t0).total_seconds() / 3600.0, vs[j]) for j in range(n)
               if abs((zs[j] - t0).total_seconds()) <= FIT_H * 3600]
        dt = _parabel_scheitel(nah)
        if dt is not None and abs(dt) <= FIT_H:
            aus.append((art, t0 + timedelta(hours=dt), vs[i]))
        else:
            aus.append((art, t0, vs[i]))
    return aus


def versatz_minuten(modell, gemessen, max_abstand_h=3.0):
    """Wie viele Minuten das Modell gegenüber der Messung nachgeht (negativ = Modell zu früh).

    Gibt (Median, Anzahl Paare, Streuung in Minuten) zurück oder None, wenn zu wenige Paare.
    """
    diffs = []
    for art, t, _ in gemessen:
        passend = [(abs((tm - t).total_seconds()), tm) for a, tm, _ in modell if a == art]
        if not passend:
            continue
        abstand, tm = min(passend)
        if abstand <= max_abstand_h * 3600:
            diffs.append((tm - t).total_seconds() / 60.0)
    if len(diffs) < 4:
        return None
    med = median(diffs)
    return med, len(diffs), median(abs(d - med) for d in diffs)


def verschiebe(extrema, minuten):
    """Hoch-/Niedrigwasser um `minuten` verschieben (zum Korrigieren: -Versatz)."""
    return [(a, t + timedelta(minutes=minuten), h) for a, t, h in extrema]


def tide_rel(extrema, t):
    """0 = Niedrigwasser, 1 = Hochwasser zur Zeit t (Kosinus-Verlauf), plus Richtung.

    Gibt (rel, 'steigend'|'fallend') zurück oder None, wenn t außerhalb der bekannten Extrema liegt.
    """
    for (a0, t0, _), (a1, t1, _) in zip(extrema, extrema[1:]):
        if t0 <= t <= t1 and a0 != a1:
            x = (t - t0).total_seconds() / (t1 - t0).total_seconds()
            if a0 == "NW":
                return 0.5 - 0.5 * math.cos(math.pi * x), "steigend"
            return 0.5 + 0.5 * math.cos(math.pi * x), "fallend"
    return None


def aus_manuell(eintraege, tz):
    """Eigene Eingaben (Datum plus 'HH:MM'-Listen) in dieselbe Extrema-Form bringen.

    Höhen sind unbekannt (None). eintraege: Liste von Dicts mit datum, hochwasser, niedrigwasser.
    """
    aus = []
    for e in eintraege:
        for art, key in (("HW", "hochwasser"), ("NW", "niedrigwasser")):
            for hhmm in e.get(key, []):
                h, m = hhmm.split(":")
                lokal = datetime(e["datum"].year, e["datum"].month, e["datum"].day, int(h), int(m), tzinfo=tz)
                aus.append((art, lokal.astimezone(timezone.utc), None))
    return sorted(aus, key=lambda x: x[1])
