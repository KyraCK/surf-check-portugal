"""Adressen und Auslese der Datenquellen (Open-Meteo, IPMA, Instituto Hidrográfico).

Alle Zeiten werden in UTC abgefragt. Umgerechnet wird erst bei der Anzeige,
weil die lokalen Uhrzeiten bei der Zeitumstellung am 25.10. doppelt vorkommen.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from netz import AbrufFehler, hole_json

OPEN_METEO = "https://api.open-meteo.com"
MARINE = "https://marine-api.open-meteo.com"
IH = "https://ogcapi.hidrografico.pt"
IPMA = "https://api.ipma.pt/open-data"

WETTER_VARIABLEN = ("temperature_2m,precipitation_probability,precipitation,cloud_cover,"
                    "wind_speed_10m,wind_direction_10m,wind_gusts_10m,weather_code")
WELLEN_VARIABLEN = ("wave_height,wave_period,wave_peak_period,wave_direction,"
                    "swell_wave_height,swell_wave_period,swell_wave_direction,"
                    "wind_wave_height,wind_wave_period,wind_wave_direction")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def zeit(s: str) -> datetime:
    """'2026-10-07T09:00' oder '...Z' (UTC) in eine zeitzonenbewusste datetime."""
    s = s.replace("Z", "")
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# ---- Open-Meteo -----------------------------------------------------------

def hole_wetter(lat, lon, modelle, tage=6):
    url = (f"{OPEN_METEO}/v1/forecast?latitude={lat}&longitude={lon}&hourly={WETTER_VARIABLEN}"
           f"&daily=sunrise,sunset&models={','.join(modelle)}&wind_speed_unit=kn&timezone=UTC&forecast_days={tage}")
    return {"url": url, "daten": hole_json(url)}


def hole_wellen(lat, lon, modell, tage=6):
    url = (f"{MARINE}/v1/marine?latitude={lat}&longitude={lon}&hourly={WELLEN_VARIABLEN}"
           f"&models={modell}&timezone=UTC&forecast_days={tage}")
    return {"url": url, "daten": hole_json(url)}


def _als_liste(d, n):
    """Open-Meteo antwortet bei mehreren Orten mit einer Liste, bei einem Ort mit einem Objekt."""
    liste = d if isinstance(d, list) else [d]
    if len(liste) != n:
        raise AbrufFehler(f"Open-Meteo lieferte {len(liste)} statt {n} Antworten")
    return liste


def hole_wetter_mehrere(punkte, modelle, tage=6):
    """Wetter für mehrere Orte in einer Anfrage. punkte: Liste von (Breite, Länge)."""
    breite = ",".join(str(p[0]) for p in punkte)
    laenge = ",".join(str(p[1]) for p in punkte)
    url = (f"{OPEN_METEO}/v1/forecast?latitude={breite}&longitude={laenge}&hourly={WETTER_VARIABLEN}"
           f"&daily=sunrise,sunset&models={','.join(modelle)}&wind_speed_unit=kn&timezone=UTC&forecast_days={tage}")
    return [{"url": url, "daten": d} for d in _als_liste(hole_json(url), len(punkte))]


def hole_wellen_mehrere(punkte, modell, tage=6):
    breite = ",".join(str(p[0]) for p in punkte)
    laenge = ",".join(str(p[1]) for p in punkte)
    url = (f"{MARINE}/v1/marine?latitude={breite}&longitude={laenge}&hourly={WELLEN_VARIABLEN}"
           f"&models={modell}&timezone=UTC&forecast_days={tage}")
    return [{"url": url, "daten": d} for d in _als_liste(hole_json(url), len(punkte))]


def hole_tide_modell(lat, lon, vergangene_tage=4, tage=6):
    url = (f"{MARINE}/v1/marine?latitude={lat}&longitude={lon}&hourly=sea_level_height_msl"
           f"&timezone=UTC&past_days={vergangene_tage}&forecast_days={tage}")
    return {"url": url, "daten": hole_json(url)}


def hole_modelllauf(host, modell):
    """Zeitpunkt, an dem das Modell gerechnet wurde (UTC), laut Open-Meteo."""
    base = MARINE if host == "marine" else OPEN_METEO
    url = f"{base}/data/{modell}/static/meta.json"
    d = hole_json(url)
    return {"url": url, "daten": {k: d.get(k) for k in (
        "last_run_initialisation_time", "last_run_availability_time", "data_end_time", "update_interval_seconds")}}


def modelllauf_text(unix) -> str:
    return datetime.fromtimestamp(unix, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- Instituto Hidrográfico (gemessener Pegel) -----------------------------

def hole_pegel(station, von: datetime, bis: datetime):
    """Gemessener Wasserstand (5-Minuten-Werte, geprüft). Ca. 1 Tag Verzögerung."""
    url = (f"{IH}/collections/tide_obs_nrt/instances/l2/locations/{station}"
           f"?f=json&parameter-name=sea_surface_height&datetime={iso(von)}/{iso(bis)}")
    return {"url": url, "daten": hole_json(url)}


def lies_pegel(d):
    """(zeiten, hoehen) aus der Antwort der Pegel-Schnittstelle. Leer, wenn es keine Werte gibt."""
    if not d or not d.get("coverages"):
        return [], []
    cov = d["coverages"][0]
    ts = [zeit(t) for t in cov["domain"]["axes"]["t"]["values"]]
    vs = cov["ranges"]["sea_surface_height"]["values"]
    return ts, vs


# ---- IPMA ------------------------------------------------------------------

def hole_ipma_stadt(ort):
    url = f"{IPMA}/forecast/meteorology/cities/daily/{ort}.json"
    return {"url": url, "daten": hole_json(url)}


def hole_ipma_see(tag_index):
    url = f"{IPMA}/forecast/oceanography/daily/hp-daily-sea-forecast-day{tag_index}.json"
    return {"url": url, "daten": hole_json(url)}


def hole_ipma_warnungen():
    url = f"{IPMA}/forecast/warnings/warnings_www.json"
    return {"url": url, "daten": hole_json(url)}


def stundenreihe(d, name, modell=None):
    """Werte einer stündlichen Variable aus einer Open-Meteo-Antwort.

    Bei mehreren Modellen heißen die Felder `<name>_<modell>`.
    Gibt (zeiten, werte) zurück.
    """
    h = d["hourly"]
    feld = f"{name}_{modell}" if modell and f"{name}_{modell}" in h else name
    return [zeit(t) for t in h["time"]], h.get(feld, [None] * len(h["time"]))
