"""Erfundene Rohdaten im selben Aufbau wie die echten Abrufe, nur für Tests.

Die Zahlen sind absichtlich einfach (gleichmäßige Welle, ruhiger Wind, eine saubere
Tidenkurve), damit man das erwartete Ergebnis im Kopf nachrechnen kann.
"""
import math
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
MODELLE_WETTER = ("gfs_seamless", "icon_seamless", "ecmwf_ifs025")
TIDE_PERIODE_H = 12.42


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M")


def _stunden(start, anzahl):
    return [start + timedelta(hours=i) for i in range(anzahl)]


def eintrag(daten, jetzt, status="ok"):
    return {"status": status, "abgerufen_um": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ"), "url": "test", "daten": daten}


def rohdaten(cfg, jetzt, hoehe=1.5, periode=11.0, wind=5.0, wind_richtung=90.0, welle_richtung=290.0,
             modell_vorlauf_min=30, regen_wk=5, temperatur=20.0, wolken=10, hoehe_je_spot=None,
             swell_h=None, wind_h=None, swell_dir=290.0, wind_dir=0.0, swell_t=11.0, wind_t=5.0):
    """Rohdaten für alle Spots und Basen der Konfiguration. Das Tidenmodell geht `modell_vorlauf_min` zu früh.

    hoehe_je_spot: {"matosinhos": 2.0} setzt für einzelne Spots eine eigene Wellenhöhe.
    swell_h / wind_h: Swell und Windsee getrennt (Höhe in m, Richtung, Periode). GFS und ICON liefern diese
    Aufteilung, ECMWF nur die Gesamthöhe (wie bei Open-Meteo). Die Gesamthöhe ist dann hypot(swell, wind).
    """
    start = jetzt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=4)
    zeiten = _stunden(start, 24 * 11)
    heute = jetzt.date()
    roh = {"abgerufen_um": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ"), "quellen": {}}
    q = roh["quellen"]

    def sinus(t, versatz_min=0):
        x = ((t - start).total_seconds() / 3600.0 - versatz_min / 60.0) / TIDE_PERIODE_H
        return 1.0 * math.sin(2 * math.pi * x)

    sonne = {"time": [], "sunrise": [], "sunset": []}
    for i in range(-4, 7):
        d = heute + timedelta(days=i)
        sonne["time"].append(d.isoformat())
        sonne["sunrise"].append(f"{d.isoformat()}T06:38")
        sonne["sunset"].append(f"{d.isoformat()}T18:06")

    gesehen = set()
    for basis in cfg["basen"]:
        for sid in basis["spots"]:
            if sid in gesehen:
                continue
            gesehen.add(sid)
            h = {"time": [_iso(t) for t in zeiten]}
            for m in MODELLE_WETTER:
                h[f"temperature_2m_{m}"] = [temperatur] * len(zeiten)
                h[f"precipitation_probability_{m}"] = [regen_wk] * len(zeiten)
                h[f"precipitation_{m}"] = [0.0] * len(zeiten)
                h[f"cloud_cover_{m}"] = [wolken] * len(zeiten)
                h[f"wind_speed_10m_{m}"] = [wind] * len(zeiten)
                h[f"wind_direction_10m_{m}"] = [wind_richtung] * len(zeiten)
                h[f"wind_gusts_10m_{m}"] = [wind] * len(zeiten)
                h[f"weather_code_{m}"] = [0] * len(zeiten)
            q[f"wetter:{sid}"] = eintrag({"hourly": h, "daily": dict(sonne)}, jetzt)
            for name in [m["name"] for m in cfg["quellen"]["modelle"]]:
                n = len(zeiten)
                gesamt = (math.hypot(swell_h, wind_h or 0.0) if swell_h is not None
                          else (hoehe_je_spot or {}).get(sid, hoehe))
                stunde = {"time": [_iso(t) for t in zeiten], "wave_height": [gesamt] * n,
                          "wave_period": [periode - 1] * n, "wave_peak_period": [periode] * n,
                          "wave_direction": [welle_richtung] * n}
                if swell_h is not None and name in ("GFS", "ICON"):
                    stunde.update(swell_wave_height=[swell_h] * n, swell_wave_period=[swell_t] * n,
                                  swell_wave_direction=[swell_dir] * n, wind_wave_height=[wind_h or 0.0] * n,
                                  wind_wave_period=[wind_t] * n, wind_wave_direction=[wind_dir] * n)
                q[f"welle:{sid}:{name}"] = eintrag({"latitude": 41.75, "longitude": -9.0, "hourly": stunde}, jetzt)
        bid = basis["id"]
        q[f"tide_modell:{bid}"] = eintrag({"hourly": {
            "time": [_iso(t) for t in zeiten],
            "sea_level_height_msl": [round(sinus(t), 3) for t in zeiten]}}, jetzt)
        # Pegel: 5-Minuten-Werte, die Messung kommt `modell_vorlauf_min` später als das Modell
        pt = []
        t = jetzt - timedelta(days=4)
        while t <= jetzt - timedelta(hours=20):
            pt.append(t)
            t += timedelta(minutes=5)
        q[f"pegel:{bid}"] = eintrag({"coverages": [{"domain": {"axes": {"t": {"values": [
            x.strftime("%Y-%m-%dT%H:%M:%SZ") for x in pt]}}}, "ranges": {"sea_surface_height": {"values": [
                round(2.0 + sinus(x, modell_vorlauf_min), 3) for x in pt]}}}]}, jetzt)
        q[f"ipma_stadt:{bid}"] = eintrag({"data": [
            {"forecastDate": (heute + timedelta(days=i)).isoformat(), "tMin": "12.0", "tMax": "22.0", "precipitaProb": "10.0"}
            for i in range(5)]}, jetzt)
    for tag in range(3):
        d = (heute + timedelta(days=tag)).isoformat()
        q[f"ipma_see:{tag}"] = eintrag({"forecastDate": d, "data": [
            {"globalIdLocal": b.get("ipma_see"), "sstMin": "16.0", "sstMax": "17.0"} for b in cfg["basen"]]}, jetzt)
    q["ipma_warnungen"] = eintrag([], jetzt)
    unix = int(jetzt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    for m in cfg["quellen"]["modelle"]:
        q[f"lauf:welle:{m['lauf_welle']}"] = eintrag({"last_run_initialisation_time": unix}, jetzt)
        q[f"lauf:wetter:{m['lauf_wetter']}"] = eintrag({"last_run_initialisation_time": unix}, jetzt)
    return roh


def ausfall(roh, schluessel, grund="HTTP 500"):
    """Macht aus einer Quelle einen Ausfall ohne ältere Daten."""
    roh["quellen"][schluessel] = {"status": "fehler", "abgerufen_um": None, "url": None, "daten": None, "fehler": grund}
