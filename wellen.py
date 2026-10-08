"""Wellen-Daten lesen und bestimmen, welche Welle am Spot ankommt.

Gemeinsam genutzt von der Auswertung (auswerten.py) und vom Lernen aus Beobachtungen (lernen.py).
"""
from __future__ import annotations

import math
from statistics import mean

import quellen
import score


def kreismittel(grade):
    g = [x for x in grade if x is not None]
    if not g:
        return None
    s = sum(math.sin(math.radians(x)) for x in g)
    c = sum(math.cos(math.radians(x)) for x in g)
    return math.degrees(math.atan2(s, c)) % 360


def mittel(werte):
    w = [x for x in werte if x is not None]
    return mean(w) if w else None


def alter_h(iso_text, jetzt):
    return (jetzt - quellen.zeit(iso_text)).total_seconds() / 3600.0


def hole(roh, schluessel, max_alter_h, jetzt):
    """(daten, info) für eine Quelle. daten ist None, wenn sie fehlt oder zu alt ist."""
    e = roh.get("quellen", {}).get(schluessel)
    if not e or e.get("daten") is None or not e.get("abgerufen_um"):
        return None, {"status": "ausgefallen", "stand": None, "fehler": (e or {}).get("fehler", "nicht abgerufen")}
    a = alter_h(e["abgerufen_um"], jetzt)
    if a > max_alter_h:
        return None, {"status": "ausgefallen", "stand": e["abgerufen_um"], "fehler": f"Daten sind {a:.0f} Stunden alt"}
    status = "aktuell" if e["status"] == "ok" else "veraltet"
    return e["daten"], {"status": status, "stand": e["abgerufen_um"], "fehler": e.get("fehler"), "url": e.get("url")}


def lies_wellen(roh, cfg, spot_id, jetzt, max_alter, praefix="welle"):
    """Wellen je Modell-Kombination für einen Spot.

    Gibt ({modell: {zeit: eintrag}}, {modell: info}) zurück. praefix "welle" sind die Vorhersagen,
    "beob" sind die Daten aus den vergangenen Tagen für die Beobachtungen.
    """
    modelle = cfg["quellen"]["modelle"]
    wellen = {}
    infos = {}
    for m in modelle:
        d, info = hole(roh, f"{praefix}:{spot_id}:{m['name']}", max_alter, jetzt)
        infos[m["name"]] = info
        if d is None:
            continue
        info["punkt"] = (d.get("latitude"), d.get("longitude"))
        zeiten, hoehe = quellen.stundenreihe(d, "wave_height")
        spitze = quellen.stundenreihe(d, "wave_peak_period")[1]
        mittlere = quellen.stundenreihe(d, "wave_period")[1]
        teil = {k: quellen.stundenreihe(d, k)[1] for k in (
            "swell_wave_height", "swell_wave_period", "swell_wave_direction",
            "wind_wave_height", "wind_wave_period", "wind_wave_direction")}
        richtung = quellen.stundenreihe(d, "wave_direction")[1]
        wellen[m["name"]] = {}
        for i, t in enumerate(zeiten):
            spitzen_wert = spitze[i]
            # Eine Welle von genau 0,0 m mit Periode 0 gibt es nicht: So meldet ein Modell einen Gitterpunkt an Land.
            if hoehe[i] == 0 and not mittlere[i] and not spitzen_wert:
                continue
            wellen[m["name"]][t] = {
                "hoehe": hoehe[i], "periode": spitzen_wert if spitzen_wert is not None else mittlere[i],
                "periode_art": "Spitze" if spitzen_wert is not None else "mittlere", "richtung": richtung[i],
                "swell_h": teil["swell_wave_height"][i], "swell_t": teil["swell_wave_period"][i],
                "swell_dir": teil["swell_wave_direction"][i], "wind_h": teil["wind_wave_height"][i],
                "wind_t": teil["wind_wave_period"][i], "wind_dir": teil["wind_wave_direction"][i]}
        info["periode_art"] = "Spitze" if any(v is not None for v in spitze) else "mittlere"
        if not wellen[m["name"]]:
            del wellen[m["name"]]
            info.update(status="nicht_verfuegbar", fehler="Der Modellpunkt liegt an Land, das Modell liefert hier keine Werte")
    return wellen, infos


def wirksame_wellen(kombis, spot, regeln):
    """Welche Welle kommt je Modell-Kombination am Spot an?

    Modelle mit Aufteilung in Swell und Windsee (GFS, Météo-France): beide Teile getrennt, jeweils nach
    der Richtung zur Küste. Modelle ohne Aufteilung (ECMWF bei Open-Meteo): Der Anteil, der bei den
    anderen Modellen ankommt, wird übernommen. Gibt es gar keine Aufteilung, zählt nur die Richtung.
    """
    geteilt = {n: score.teile_welle(e["welle"], spot, regeln) for n, e in kombis.items()}
    vorhanden = {n: g for n, g in geteilt.items() if g}
    aus = {}
    for n, e in kombis.items():
        w = e["welle"]
        g = geteilt[n]
        if g:
            aus[n] = dict(g, quelle="geteilt")
        elif vorhanden:
            anteile = [x["hoehe"] / x["gesamt"] for x in vorhanden.values() if x["gesamt"]]
            perioden = [x["periode"] for x in vorhanden.values() if x["periode"]]
            richtungen = [x["richtung"] for x in vorhanden.values() if x["richtung"] is not None]
            anteil = mean(anteile) if anteile else 1.0
            aus[n] = {"hoehe": w["hoehe"] * anteil, "gesamt": w["hoehe"], "periode": mean(perioden) if perioden else w["periode"],
                      "richtung": kreismittel(richtungen) if richtungen else w["richtung"], "art": "übernommen",
                      "quelle": "übernommen"}
        else:
            faktor = score.richtungsfaktor(w["richtung"], spot, regeln)
            aus[n] = {"hoehe": w["hoehe"] * faktor, "gesamt": w["hoehe"], "periode": w["periode"],
                      "richtung": w["richtung"], "art": w["periode_art"], "quelle": "ohne Aufteilung"}
    return aus
