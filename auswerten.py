"""Macht aus den Rohdaten (data/rohdaten.json) das fertige Ergebnis für die Seite.

Ablauf:
  1. Pro Spot und Stunde eine Bedingung je Modell-Kombination (Welle + Wetter + Tide).
  2. Pro Person ein Score je Stunde und Kombination (score.py), daraus Konsens und Streuung.
  3. Zeitfenster bei Tageslicht, bestes Fenster, bester Spot je Tag.
  4. Fazit, Sicherheit, Badetag, Datenlage mit Quelle und Modelllauf.

Es werden nur Werte aus den Quellen verwendet. Fehlt etwas, bleibt das Feld None
und die Seite zeigt einen Strich oder einen Hinweis.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

import config
import gezeiten
import quellen
import score

TZ = ZoneInfo("Europe/Lisbon")
UTC = timezone.utc
KOMPASS = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]
KOMPASS_LANG = ["Nord", "Nordost", "Ost", "Südost", "Süd", "Südwest", "West", "Nordwest"]
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WOCHENTAGE_LANG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
IPMA_WARNUNG = {
    "Agitação Marítima": "Seegang", "Vento": "Wind", "Precipitação": "Regen", "Trovoada": "Gewitter",
    "Nevoeiro": "Nebel", "Tempo Quente": "Hitze", "Tempo Frio": "Kälte", "Neve": "Schnee",
}
IPMA_STUFE = {"yellow": "gelb", "orange": "orange", "red": "rot"}
UMSCHALT_STUNDE = 18  # ab dieser Ortszeit zeigt die Seite den nächsten Morgen


# ---- kleine Helfer ---------------------------------------------------------

def kompass(grad):
    return None if grad is None else KOMPASS[int((grad % 360 + 22.5) // 45) % 8]


def kompass_lang(grad):
    return None if grad is None else KOMPASS_LANG[int((grad % 360 + 22.5) // 45) % 8]


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


def spanne(werte):
    w = [x for x in werte if x is not None]
    return (min(w), max(w)) if w else None


def lokal(t: datetime) -> datetime:
    return t.astimezone(TZ)


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


def schlechtester_status(infos):
    reihenfolge = {"aktuell": 0, "nicht_verfuegbar": 1, "veraltet": 2, "ausgefallen": 3}
    infos = list(infos)
    if not infos:
        return {"status": "ausgefallen", "stand": None, "fehler": "keine Quelle"}
    schlecht = max(infos, key=lambda i: reihenfolge[i["status"]])
    staende = [i["stand"] for i in infos if i.get("stand")]
    return {"status": schlecht["status"], "stand": min(staende) if staende else None, "fehler": schlecht.get("fehler")}


# ---- Gezeiten --------------------------------------------------------------

def tide_fuer_basis(roh, cfg, basis, jetzt, max_alter):
    """Hoch-/Niedrigwasser (korrigiert), Tage mit eigenen Einträgen und Infos für eine Basis."""
    info = {"quelle": None, "versatz_min": None, "paare": 0, "hinweis": None, "pegel": basis.get("pegel")}
    modell, i_mod = hole(roh, f"tide_modell:{basis['id']}", max_alter, jetzt)
    info["status"] = i_mod
    ext = []
    if modell is not None:
        z, h = quellen.stundenreihe(modell, "sea_level_height_msl")
        ext = gezeiten.finde_extrema(z, h)
        info["quelle"] = "modell"
        pegel, i_peg = hole(roh, f"pegel:{basis['id']}", max_alter, jetzt)
        info["pegel_status"] = i_peg
        if pegel is not None:
            pz, ph = quellen.lies_pegel(pegel)
            gemessen = gezeiten.finde_extrema(pz, ph, glaetten_min=25) if pz else []
            nah = [e for e in ext if pz and pz[0] - timedelta(hours=3) <= e[1] <= pz[-1] + timedelta(hours=3)]
            v = gezeiten.versatz_minuten(nah, gemessen) if gemessen else None
            if v is not None:
                ext = gezeiten.verschiebe(ext, -v[0])
                info.update(quelle="modell_korrigiert", versatz_min=v[0], paare=v[1])
            else:
                info["hinweis"] = "Zu wenige gemessene Hoch- und Niedrigwasser für die Korrektur, das Modell geht dann etwa 30 Minuten zu früh."
        else:
            info["hinweis"] = "Pegel nicht erreichbar, das Modell geht dann etwa 30 Minuten zu früh."
    manuell = gezeiten.aus_manuell(cfg["manuell"], TZ)
    manuelle_tage = {lokal(t).date() for _, t, _ in manuell}
    if manuell:
        ext = [e for e in ext if lokal(e[1]).date() not in manuelle_tage] + manuell
        ext.sort(key=lambda e: e[1])
    info["manuelle_tage"] = sorted(manuelle_tage)
    return ext, manuelle_tage, info


def tide_zu_zeit(ext, manuelle_tage, t):
    """(rel, richtung, quelle) zur Zeit t oder None."""
    r = gezeiten.tide_rel(ext, t)
    if r is None:
        return None
    return r[0], r[1], ("manuell" if lokal(t).date() in manuelle_tage else "modell")


# ---- Wetter und Wellen je Spot -----------------------------------------------

def lies_spot(roh, cfg, spot_id, jetzt, max_alter):
    """Stündliche Wetter- und Wellendaten je Modell-Kombination für einen Spot."""
    modelle = cfg["quellen"]["modelle"]
    infos = {}
    wetter_d, infos["wetter"] = hole(roh, f"wetter:{spot_id}", max_alter, jetzt)
    wetter = {m["name"]: {} for m in modelle}
    sonne = {}
    if wetter_d is not None:
        for m in modelle:
            r = {n: quellen.stundenreihe(wetter_d, n, m["wetter"]) for n in (
                "temperature_2m", "precipitation_probability", "cloud_cover", "wind_speed_10m",
                "wind_direction_10m", "wind_gusts_10m", "precipitation")}
            for i, t in enumerate(r["wind_speed_10m"][0]):
                wetter[m["name"]][t] = {
                    "temp": r["temperature_2m"][1][i], "regen_wk": r["precipitation_probability"][1][i],
                    "wolken": r["cloud_cover"][1][i], "wind": r["wind_speed_10m"][1][i],
                    "richtung": r["wind_direction_10m"][1][i], "boeen": r["wind_gusts_10m"][1][i],
                }
        tage = wetter_d["daily"]
        auf = next((tage[k] for k in tage if k.startswith("sunrise")), [])
        unter = next((tage[k] for k in tage if k.startswith("sunset")), [])
        for tag, a, u in zip(tage["time"], auf, unter):
            if a and u:
                sonne[date.fromisoformat(tag)] = (quellen.zeit(a), quellen.zeit(u))
    wellen = {}
    infos["wellen"] = {}
    for m in modelle:
        d, info = hole(roh, f"welle:{spot_id}:{m['name']}", max_alter, jetzt)
        infos["wellen"][m["name"]] = info
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
    stunden = {}
    for name, reihe in wellen.items():
        for t, w in reihe.items():
            stunden.setdefault(t, {})[name] = {"welle": w, "wetter": wetter.get(name, {}).get(t)}
    return {"stunden": stunden, "wetter": wetter, "sonne": sonne, "infos": infos}


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


def bedingung(eintrag, tide, wirk):
    """Eingabe für score.bewerte aus einem Stundeneintrag, der wirksamen Welle und dem Tide-Stand."""
    we = eintrag["wetter"] or {}
    return {
        "hoehe_m": wirk["hoehe"], "hoehe_gesamt_m": wirk["gesamt"], "periode_s": wirk["periode"],
        "periode_art": wirk["art"], "swell_richtung": wirk["richtung"], "wind_kn": we.get("wind"),
        "boeen_kn": we.get("boeen"), "wind_richtung": we.get("richtung"),
        "tide_rel": tide[0] if tide else None, "tide_quelle": tide[2] if tide else None,
    }


def bewerte_stunden(daten, spot, personen, regeln, ext, manuelle_tage):
    """Pro Stunde: Bedingungen, Tide, Scores je Person und Kombination, Konsens."""
    aus = {}
    for t, kombis in sorted(daten["stunden"].items()):
        tide = tide_zu_zeit(ext, manuelle_tage, t)
        je_kombi = {}
        wirk = wirksame_wellen(kombis, spot, regeln)
        for name, eintrag in kombis.items():
            bed = bedingung(eintrag, tide, wirk[name])
            je_kombi[name] = {"bed": bed, "personen": {pid: score.bewerte(bed, spot, p, regeln) for pid, p in personen.items()}}
        konsens = {}
        for pid in personen:
            rohs = [k["personen"][pid]["roh"] for k in je_kombi.values() if k["personen"][pid]["punkte"] is not None]
            konsens[pid] = max(0.0, mean(rohs)) if rohs else None
        aus[t] = {"kombis": je_kombi, "tide": tide, "konsens_roh": konsens}
    return aus


# ---- Zeitfenster -----------------------------------------------------------

def punkte_aus_roh(roh):
    return None if roh is None else max(1, min(10, score.runde(roh)))


def tageslicht_bloecke(tag: date, sonne, laenge):
    """Anfänge der Zeitfenster (lokale Zeit), die ganz zwischen Sonnenaufgang und -untergang liegen."""
    if tag not in sonne:
        return []
    auf, unter = lokal(sonne[tag][0]), lokal(sonne[tag][1])
    start = auf.replace(minute=0, second=0, microsecond=0)
    if start < auf:
        start += timedelta(hours=1)
    bloecke = []
    while start + timedelta(hours=laenge) <= unter:
        bloecke.append(start)
        start += timedelta(hours=laenge)
    return bloecke


def block_auswerten(start, laenge, st, personen, regeln, spot, modelle_namen, jetzt):
    """Alle Kennzahlen eines Zeitfensters. None, wenn für einzelne Stunden Daten fehlen."""
    start_utc = start.astimezone(UTC)
    stunden_t = [start_utc + timedelta(hours=i) for i in range(laenge)]
    if any(t not in st for t in stunden_t):
        return None
    ende = lokal(start_utc + timedelta(hours=laenge))
    b = {"start": start, "ende": ende, "vorbei": ende <= lokal(jetzt), "personen": {}}
    for pid in personen:
        rohs = [st[t]["konsens_roh"][pid] for t in stunden_t]
        punkte = None if any(r is None for r in rohs) else punkte_aus_roh(mean(rohs))
        je_modell = {}
        for n in modelle_namen:
            r = [st[t]["kombis"].get(n, {}).get("personen", {}).get(pid, {}).get("roh") for t in stunden_t]
            je_modell[n] = None if any(x is None for x in r) else punkte_aus_roh(max(0.0, mean(r)))
        b["personen"][pid] = {"punkte": punkte, "je_modell": je_modell}
    je_n = {n: [st[t]["kombis"][n]["bed"] for t in stunden_t if n in st[t]["kombis"]] for n in modelle_namen}
    je_n = {n: v for n, v in je_n.items() if len(v) == laenge and all(x["wind_kn"] is not None for x in v)}
    korr = spot["korrekturfaktor"]
    b["modelle"] = [n for n in modelle_namen if n in je_n]
    b["welle_m"] = spanne([mittel([x["hoehe_m"] * korr for x in v]) for v in je_n.values()])
    b["welle_modell_m"] = spanne([mittel([x["hoehe_m"] for x in v]) for v in je_n.values()])
    b["welle_gesamt_m"] = spanne([mittel([x["hoehe_gesamt_m"] for x in v]) for v in je_n.values()])
    b["periode_s"] = spanne([mittel([x["periode_s"] for x in v]) for v in je_n.values()])
    b["periode_art"] = {n: v[0]["periode_art"] for n, v in je_n.items()}
    b["je_modell"] = {n: {"welle": mittel([x["hoehe_m"] * korr for x in v]), "periode": mittel([x["periode_s"] for x in v]),
                          "wind": mittel([x["wind_kn"] for x in v])} for n, v in je_n.items()}
    b["wind_kn"] = spanne([mittel([x["wind_kn"] for x in v]) for v in je_n.values()])
    b["boeen_kn"] = max([x["boeen_kn"] for v in je_n.values() for x in v if x["boeen_kn"] is not None], default=None)
    b["wind_richtung"] = kreismittel([x["wind_richtung"] for v in je_n.values() for x in v])
    b["swell_richtung"] = kreismittel([x["swell_richtung"] for v in je_n.values() for x in v])
    erste = next(iter(personen))
    arten = [r["windart"] for t in stunden_t for k in st[t]["kombis"].values()
             for r in [k["personen"][erste]] if r.get("punkte") is not None]
    b["windart"] = max(set(arten), key=arten.count) if arten else None
    t_mitte = st[stunden_t[len(stunden_t) // 2]].get("tide")
    b["tide"] = {"rel": t_mitte[0], "richtung": t_mitte[1], "quelle": t_mitte[2]} if t_mitte else None
    # beste Person und Urteil
    gewertet = {pid: v["punkte"] for pid, v in b["personen"].items() if v["punkte"] is not None}
    b["bester_pid"] = max(gewertet, key=gewertet.get) if gewertet else None
    b["urteile"] = {pid: urteil(b, st, stunden_t, personen, regeln, pid)
                    for pid in personen if b["personen"][pid]["punkte"] is not None}
    b["sicherheit"] = None
    b["urteil"] = None
    if b["bester_pid"]:
        pid = b["bester_pid"]
        b["sicherheit"] = score.sicherheit(list(b["personen"][pid]["je_modell"].values()), regeln)
        b["urteil"] = b["urteile"].get(pid)
    return b


def urteil(block, st, stunden_t, personen, regeln, pid):
    """Ein Wort zum Fenster, abhängig vom schwächsten Punkt der besten Person."""
    w = regeln["urteile"]
    punkte = block["personen"][pid]["punkte"]
    anteile, n = {}, 0
    for t in stunden_t:
        for k in st[t]["kombis"].values():
            r = k["personen"][pid]
            if r.get("punkte") is None:
                continue
            n += 1
            for name, wert in r["anteile"].items():
                anteile[name] = anteile.get(name, 0.0) + wert
            anteile["hoehe"] = anteile.get("hoehe", 0.0) + r["grundpunkte"] * 10.0
    if not n:
        return None
    anteile = {k: v / n for k, v in anteile.items()}
    if punkte > regeln["skala"]["surfbar_bis"]:
        return w["sauber"] if anteile["wind"] >= 90 and anteile["periode"] >= 85 else w["gut"]
    schwach = min(anteile, key=anteile.get)
    if schwach == "hoehe":
        h = block["welle_m"][1] if block["welle_m"] else 0.0
        beste_hoehe = max(p for p, y in personen[pid]["hoehe"] if y >= 10) if any(y >= 10 for _, y in personen[pid]["hoehe"]) else 0
        return w["zu_gross"] if h > beste_hoehe else w["zu_klein"]
    wort = {"periode": w["kurze_periode"], "wind": w["windig"], "swell": w["swell_passt_nicht"],
            "tide": w["tide_passt_nicht"], "groesse": w["zu_gross"]}[schwach]
    if punkte <= regeln["skala"]["lohnt_kaum_bis"]:
        return wort
    return f"{w['surfbar']}, {wort}" if anteile[schwach] < 85 else w["surfbar"]


def punkte_liste(b):
    return [v["punkte"] for v in b["personen"].values() if v["punkte"] is not None]


def bester_block(bloecke, nur_zukunft=False):
    """Fenster mit dem höchsten Score einer Person, bei Gleichstand der höheren Summe."""
    kand = [b for b in bloecke if b and punkte_liste(b) and not (nur_zukunft and b["vorbei"])]
    return max(kand, key=lambda b: (max(punkte_liste(b)), sum(punkte_liste(b)))) if kand else None


# ---- Wetter pro Tag ----------------------------------------------------------

def tageswetter(datum, daten):
    """Temperatur, Wind und Symbol für einen Tag aus allen Modellen. Felder sind None, wenn Daten fehlen."""
    stunden = [(t, w) for reihe in daten["wetter"].values() for t, w in reihe.items() if lokal(t).date() == datum]
    sonne = daten["sonne"].get(datum)
    hell = [(t, w) for t, w in stunden if sonne and sonne[0] <= t <= sonne[1]]
    temps = [w["temp"] for _, w in stunden if w["temp"] is not None]
    wind = [w["wind"] for _, w in hell if w["wind"] is not None]
    wolken = mittel([w["wolken"] for _, w in hell])
    regen = mittel([w["regen_wk"] for _, w in hell])
    symbol = None
    if wolken is not None:
        symbol = "rain" if (regen is not None and regen >= 50) else ("sun" if wolken < 25 else ("partly" if wolken < 65 else "cloud"))
    return {"tmax": max(temps) if temps else None, "tmin": min(temps) if temps else None,
            "wind_kn": mittel(wind), "wind_richtung": kreismittel([w["richtung"] for _, w in hell]),
            "regen_wk": regen, "wolken": wolken, "symbol": symbol}


# ---- Baden -------------------------------------------------------------------

def baden_rechnen(datum, daten, ext, manuelle, regeln):
    """Wie gut passt der Tag zum Baden (0 bis 100 %) und ab wann."""
    b = regeln["baden"]
    werte = []
    for stunde in range(b["von_uhr"], b["bis_uhr"]):
        t = datetime(datum.year, datum.month, datum.day, stunde, tzinfo=TZ).astimezone(UTC)
        modelle = [r[t] for r in daten["wetter"].values() if t in r]
        temp = mittel([m["temp"] for m in modelle])
        wind = mittel([m["wind"] for m in modelle])
        regen = mittel([m["regen_wk"] for m in modelle])
        if temp is None or wind is None or regen is None:
            werte.append((stunde, None, False, None))
            continue
        tide = tide_zu_zeit(ext, manuelle, t)
        f = (score.kennlinie(b["temperatur_c"], temp) * score.kennlinie(b["wind_kn"], wind)
             * score.kennlinie(b["regen_prozent"], regen)) / 10000.0
        if tide:
            f *= score.kennlinie(b["tide"], tide[0]) / 100.0
        werte.append((stunde, f, tide is not None, {"temp": temp, "wind": wind, "regen": regen, "tide": tide[0] if tide else None}))
    best = None
    for i in range(len(werte) - 2):
        fenster = werte[i:i + 3]
        if any(w[1] is None for w in fenster):
            continue
        m = mean(w[1] for w in fenster)
        if best is None or m > best[1]:
            details = {k: mittel([w[3][k] for w in fenster]) for k in ("temp", "wind", "regen", "tide")}
            best = (fenster[0][0], m, all(w[2] for w in fenster), details)
    if best is None:
        return None
    return {"prozent": best[1], "ab_uhr": best[0], "mit_tide": best[2], "details": best[3]}


# ---- IPMA ------------------------------------------------------------------

def ipma_infos(roh, basis, jetzt, max_alter):
    aus = {"see": None, "stadt": {}, "warnungen": [], "status": {}}
    if basis.get("ipma_see"):
        for tag in range(3):
            d, info = hole(roh, f"ipma_see:{tag}", max_alter, jetzt)
            if d is not None:
                eintrag = next((x for x in d["data"] if x["globalIdLocal"] == basis["ipma_see"]), None)
                if eintrag:
                    aus["see"] = aus["see"] or {}
                    aus["see"][d["forecastDate"]] = eintrag
            aus["status"][f"see{tag}"] = info
    if basis.get("ipma_stadt"):
        d, info = hole(roh, f"ipma_stadt:{basis['id']}", max_alter, jetzt)
        aus["status"]["stadt"] = info
        if d is not None:
            aus["stadt"] = {x["forecastDate"]: x for x in d["data"]}
    d, info = hole(roh, "ipma_warnungen", max_alter, jetzt)
    aus["status"]["warnungen"] = info
    if d is not None and basis.get("ipma_warngebiet"):
        for w in d:
            if w["idAreaAviso"] != basis["ipma_warngebiet"] or w["awarenessLevelID"] == "green":
                continue
            if quellen.zeit(w["endTime"]).replace(tzinfo=TZ) < lokal(jetzt):
                continue
            aus["warnungen"].append({
                "art": IPMA_WARNUNG.get(w["awarenessTypeName"], w["awarenessTypeName"]),
                "stufe": IPMA_STUFE.get(w["awarenessLevelID"], w["awarenessLevelID"]),
                "bis": quellen.zeit(w["endTime"]).replace(tzinfo=TZ)})
    return aus


def modelllaeufe(roh, cfg, jetzt, max_alter):
    """Zeitpunkt der letzten Modellläufe (UTC) je Modell-Kombination laut Open-Meteo."""
    aus = {}
    for m in cfg["quellen"]["modelle"]:
        eintrag = {}
        for art, name in (("welle", m["lauf_welle"]), ("wetter", m["lauf_wetter"])):
            d, _ = hole(roh, f"lauf:{art}:{name}", max_alter, jetzt)
            unix = d.get("last_run_initialisation_time") if d else None
            eintrag[art] = datetime.fromtimestamp(unix, tz=UTC) if unix else None
        aus[m["name"]] = eintrag
    return aus


# ---- Auswahl: normale Spots und Ausweich-Spots ----------------------------------

def wert(b):
    """Sortierschlüssel eines Fensters: höchster Score einer Person, dann Summe."""
    p = punkte_liste(b)
    return (max(p), sum(p))


def waehle(kandidaten: dict, cfg):
    """Spot-id mit dem besten Fenster. Ausweich-Spots nur, wenn sie deutlich besser sind."""
    if not kandidaten:
        return None
    haupt = {s: b for s, b in kandidaten.items() if not cfg["spots"][s].get("ausweich")}
    ausw = {s: b for s, b in kandidaten.items() if cfg["spots"][s].get("ausweich")}
    bester_h = max(haupt, key=lambda s: wert(haupt[s])) if haupt else None
    bester_a = max(ausw, key=lambda s: wert(ausw[s])) if ausw else None
    if bester_h is None:
        return bester_a
    vorsprung = cfg["scoring"]["ausweich"]["vorsprung_punkte"]
    if bester_a and wert(ausw[bester_a])[0] >= wert(haupt[bester_h])[0] + vorsprung:
        return bester_a
    return bester_h


def bester_fuer_person(spots_tag, pid, cfg, nur_zukunft):
    """Bestes Fenster einer Person über alle Spots (Ausweich-Regel wie oben)."""
    def beste(sids):
        best = None
        for sid in sids:
            for b in spots_tag[sid]["bloecke"]:
                p = b["personen"][pid]["punkte"] if b else None
                if p is not None and not (nur_zukunft and b["vorbei"]) and (best is None or p > best["punkte"]):
                    best = {"spot": sid, "block": b, "punkte": p}
        return best
    haupt = beste([s for s in spots_tag if not cfg["spots"][s].get("ausweich")])
    ausw = beste([s for s in spots_tag if cfg["spots"][s].get("ausweich")])
    vorsprung = cfg["scoring"]["ausweich"]["vorsprung_punkte"]
    if haupt is None:
        return ausw
    if ausw and ausw["punkte"] >= haupt["punkte"] + vorsprung:
        return ausw
    return haupt


# ---- Ausflüge ----------------------------------------------------------------

def ausfluege_waehlen(cfg, basis_id, wetter, surftag):
    """Ein bis zwei Ausflüge für einen Tag nach den Regeln in config/ausfluege.toml."""
    r = cfg["ausflug_regeln"]
    ziele = [z for z in cfg["ausfluege"] if z["basis"] == basis_id]
    aus = {"modus": None, "vorschlaege": [], "hinweis": None, "surftag": surftag}
    if not ziele:
        aus["hinweis"] = "Für diese Basis sind noch keine Ausflugsziele eingetragen."
        return aus
    if not wetter or wetter.get("wind_kn") is None or wetter.get("regen_wk") is None or wetter.get("tmax") is None:
        aus["hinweis"] = "Ohne Wetterdaten gibt es keine Ausflugstipps."
        return aus
    wind, richtung, regen, tmax = wetter["wind_kn"], wetter["wind_richtung"], wetter["regen_wk"], wetter["tmax"]
    wolken = wetter.get("wolken")
    nordwind = wind >= r["nordwind_ab_kn"] and abstand_zum_sektor_text(richtung, r["nordwind_sektor_grad"])
    regentag = regen >= r["regen_ab_prozent"]
    trocken = regen < r["klar_regen_unter_prozent"]
    klar = trocken and wolken is not None and wolken < r["klar_wolken_unter_prozent"]
    warm_ruhig = tmax >= r["warm_ab_c"] and wind < r["ruhig_bis_kn"] and trocken
    aus["modus"] = "regen" if regentag else ("nordwind" if nordwind else ("warm_ruhig" if warm_ruhig else "normal"))

    def passt(z):
        b = set(z["bedingung"])
        if regentag:
            return "regen" in b
        if nordwind:
            return "nordwind" in b
        return (("jedes_wetter" in b and regen < r["starkregen_ab_prozent"]) or ("klar" in b and klar)
                or ("warm_ruhig" in b and warm_ruhig) or ("nordwind" in b and regen < r["regen_ab_prozent"])
                or "regen" in b)

    def punkte(z):
        b = set(z["bedingung"])
        p = 0
        if regentag and "regen" in b:
            p += 10
        if nordwind and "nordwind" in b:
            p += 10
        if warm_ruhig and "warm_ruhig" in b:
            p += 6
        if klar and "klar" in b:
            p += 2
        if "jedes_wetter" in b:
            p += 1
        return p

    def zeit(z):
        f = z["fahrzeit_min"]
        return sum(f) / 2 if isinstance(f, list) else f

    moegliche = [z for z in ziele if passt(z)]
    if surftag:
        moegliche = [z for z in moegliche if z["dauer"] == "kurz"]
        if not moegliche:
            aus["hinweis"] = "Surftag: Es passt gerade kein kurzes Ziel zum Wetter."
    grund_text = {"regen": "Regen-Alternative", "nordwind": "bei Nordwind geschützt", "warm_ruhig": "warm und ruhig",
                  "klar": "bei klarem Wetter", "jedes_wetter": "bei jedem Wetter"}
    gewaehlt = sorted(moegliche, key=lambda z: (-punkte(z), zeit(z)))[:int(r["vorschlaege_pro_tag"])]
    for z in gewaehlt:
        b = set(z["bedingung"])
        if aus["modus"] in b:
            grund = grund_text[aus["modus"]]
        else:
            grund = grund_text[next((k for k in ("warm_ruhig", "klar", "jedes_wetter", "nordwind", "regen") if k in b), "jedes_wetter")]
        aus["vorschlaege"].append({"ziel": z, "grund": grund, "nachmittag": surftag})
    if not gewaehlt and not aus["hinweis"]:
        aus["hinweis"] = "Heute passt keines der eingetragenen Ziele zum Wetter."
    return aus


def abstand_zum_sektor_text(grad, sektor):
    """True, wenn grad im Bereich (von, bis) liegt (über Nord erlaubt)."""
    return grad is not None and score.abstand_zum_sektor(grad, sektor[0], sektor[1]) == 0


# ---- Hauptfunktion -----------------------------------------------------------

def auswerten(cfg, roh, jetzt):
    regeln, personen = cfg["scoring"], cfg["scoring"]["personen"]
    max_alter = cfg["quellen"]["daten"]["max_alter_stunden"]
    modelle = [m["name"] for m in cfg["quellen"]["modelle"]]
    laenge = regeln["zeitfenster"]["laenge_stunden"]
    jetzt_l = lokal(jetzt)
    heute = jetzt_l.date()
    tage = [heute + timedelta(days=i) for i in range(5)]
    alarme = []

    basen = {}
    spots = {}
    for basis in cfg["basen"]:
        ext, manuell, tide_info = tide_fuer_basis(roh, cfg, basis, jetzt, max_alter)
        basen[basis["id"]] = {"basis": basis, "ext": ext, "manuell": manuell, "tide": tide_info,
                              "ipma": ipma_infos(roh, basis, jetzt, max_alter)}
        for sid in basis.get("spots", []):
            d = lies_spot(roh, cfg, sid, jetzt, max_alter)
            spots[(basis["id"], sid)] = {"daten": d, "stunden": bewerte_stunden(
                d, cfg["spots"][sid], personen, regeln, ext, manuell)}

    cache = {}

    def tag_fuer(datum, basis):
        """Alle Spots einer Basis an einem Tag."""
        schluessel = (datum, basis["id"])
        if schluessel in cache:
            return cache[schluessel]
        tag = {"datum": datum, "basis": basis["id"], "spots": {}, "wetter": None, "bester_spot": None, "personen": {}}
        erster_mit_wetter = None
        for sid in basis.get("spots", []):
            sd = spots[(basis["id"], sid)]
            bloecke = [block_auswerten(s, laenge, sd["stunden"], personen, regeln, cfg["spots"][sid], modelle, jetzt)
                       for s in tageslicht_bloecke(datum, sd["daten"]["sonne"], laenge)]
            tag["spots"][sid] = {"bloecke": bloecke, "bester": bester_block(bloecke, nur_zukunft=(datum == heute))}
            if erster_mit_wetter is None and sd["daten"]["wetter"] and any(sd["daten"]["wetter"].values()):
                erster_mit_wetter = sd["daten"]
        if erster_mit_wetter:
            tag["wetter"] = tageswetter(datum, erster_mit_wetter)
        kand = {sid: s["bester"] for sid, s in tag["spots"].items() if s["bester"]}
        tag["bester_spot"] = waehle(kand, cfg)
        if tag["bester_spot"]:
            for pid in personen:
                werte = [b["personen"][pid]["punkte"] for b in tag["spots"][tag["bester_spot"]]["bloecke"]
                         if b and b["personen"][pid]["punkte"] is not None and not (datum == heute and b["vorbei"])]
                tag["personen"][pid] = max(werte) if werte else None
        cache[schluessel] = tag
        return tag

    # Reise-Ansicht: jeder Tag mit der Basis, die an diesem Tag gilt
    reise = []
    for datum in tage:
        basis = config.basis_fuer(cfg["basen"], datum)
        reise.append(tag_fuer(datum, basis) if basis else
                     {"datum": datum, "basis": None, "spots": {}, "wetter": None, "bester_spot": None, "personen": {}})

    # Welche Basis ist die aktuelle, welcher Tag wird gezeigt?
    aktuelle = config.basis_fuer(cfg["basen"], heute)
    if aktuelle is None:
        kommende = [b for b in cfg["basen"] if b["von"] > heute]
        aktuelle = min(kommende, key=lambda b: b["von"]) if kommende else cfg["basen"][-1]
    modus, anzeige = "heute", heute
    if jetzt_l.hour >= UMSCHALT_STUNDE:
        modus, anzeige = "morgen", heute + timedelta(days=1)
    else:
        t0 = tag_fuer(heute, aktuelle)
        if not any(s["bester"] for s in t0["spots"].values()):
            modus, anzeige = "morgen", heute + timedelta(days=1)
    label = (f"Heute · {WOCHENTAGE[anzeige.weekday()]} {anzeige.day}.{anzeige.month}." if modus == "heute"
             else f"{WOCHENTAGE_LANG[anzeige.weekday()]} früh")
    skala_cfg = regeln["skala"]

    ansichten = {}
    for basis in cfg["basen"]:
        tag_a = tag_fuer(anzeige, basis)
        gueltig = (config.basis_fuer(cfg["basen"], anzeige) or {}).get("id") == basis["id"]
        # Nur Tage, an denen ihr an dieser Basis seid (liegt keiner im Zeitraum: alle, als Vergleich)
        tage_basis = [t for t in tage if (config.basis_fuer(cfg["basen"], t) or {}).get("id") == basis["id"]]
        spaetere_tage = [t for t in (tage_basis or tage) if t > anzeige]
        # Fazit
        fazit = {"ja": None, "grund": None}
        kand = {sid: s["bester"] for sid, s in tag_a["spots"].items() if s["bester"]}
        sid = waehle(kand, cfg)
        if sid is None:
            fazit["grund"] = "Es liegen keine Wellen- oder Winddaten vor."
        else:
            b = kand[sid]
            hoechst = max(punkte_liste(b))
            fazit.update(ja=hoechst >= skala_cfg["surftag_ab_punkte"], spot=sid, block=b, hoechst=hoechst,
                         ausweich=bool(cfg["spots"][sid].get("ausweich")),
                         gut_fuer=[pid for pid, v in b["personen"].items()
                                   if v["punkte"] is not None and v["punkte"] >= skala_cfg["surftag_ab_punkte"]])
            aussicht = None
            for t in spaetere_tage:
                tg = tag_fuer(t, basis)
                k2 = {s: x["bester"] for s, x in tg["spots"].items() if x["bester"]}
                s2 = waehle(k2, cfg)
                if s2 and (aussicht is None or max(punkte_liste(k2[s2])) > aussicht["hoechst"]):
                    aussicht = {"datum": t, "spot": s2, "block": k2[s2], "hoechst": max(punkte_liste(k2[s2]))}
            fazit["aussicht"] = aussicht
        # Empfehlung je Person
        empf = {}
        for pid in personen:
            woche = None
            for t in spaetere_tage:
                kandidat = bester_fuer_person(tag_fuer(t, basis)["spots"], pid, cfg, False)
                if kandidat and (woche is None or kandidat["punkte"] > woche["punkte"]):
                    woche = dict(kandidat, datum=t)
            empf[pid] = {"anzeige": bester_fuer_person(tag_a["spots"], pid, cfg, anzeige == heute), "woche": woche}
        # Baden
        baden = None
        if basis.get("baden"):
            bi = basen[basis["id"]]
            tage_b = []
            for t in tage:
                if config.basis_fuer(cfg["basen"], t) is None or config.basis_fuer(cfg["basen"], t)["id"] != basis["id"]:
                    continue
                sd = next((spots[(basis["id"], s)]["daten"] for s in basis["spots"] if spots[(basis["id"], s)]["daten"]["wetter"]), None)
                tage_b.append({"datum": t, "ergebnis": baden_rechnen(t, sd, bi["ext"], bi["manuell"], regeln) if sd else None})
            if tage_b:
                guete = [x for x in tage_b if x["ergebnis"]]
                bester = max(guete, key=lambda x: x["ergebnis"]["prozent"]) if guete else None
                see = bi["ipma"]["see"] or {}
                erster = next(iter(see.values()), None)
                baden = {"ort": basis["baden"], "tage": tage_b,
                         "bester": bester if bester and bester["ergebnis"]["prozent"] * 100 >= regeln["baden"]["mindest_prozent"] else None,
                         "wasser_c": (erster["sstMin"], erster["sstMax"]) if erster else None,
                         "wasser_datum": next(iter(see), None)}
        # Ausflüge
        surftag = bool(fazit.get("ja"))
        ausfl = ausfluege_waehlen(cfg, basis["id"], tag_a["wetter"], surftag)
        ansichten[basis["id"]] = {"basis": basis, "tag": tag_a, "gueltig": gueltig, "fazit": fazit, "empfehlung": empf,
                                  "baden": baden, "ausfluege": ausfl}

    # Ausfälle, die oben auf der Seite stehen müssen (zusammengefasst, damit es nicht 30 Meldungen werden)
    wetter_weg, wellen_weg = {}, {}
    for (bid, sid), sd in spots.items():
        i = sd["daten"]["infos"]
        name = cfg["spots"][sid]["name"]
        if i["wetter"]["status"] == "ausgefallen":
            wetter_weg.setdefault(i["wetter"]["fehler"], []).append(name)
        for n, x in i["wellen"].items():
            if x["status"] == "ausgefallen":
                wellen_weg.setdefault((n, x["fehler"]), []).append(name)

    def spots_text(namen):
        namen = sorted(set(namen))
        return ", ".join(namen) if len(namen) <= 3 else f"{len(namen)} Spots"
    for grund, namen in wetter_weg.items():
        alarme.append(f"Wetterdaten fehlen für {spots_text(namen)} ({grund}). Wind und Scores sind dort ausgeblendet.")
    for (modell, grund), namen in wellen_weg.items():
        alarme.append(f"Wellenmodell {modell} fehlt für {spots_text(namen)} ({grund}). Es zählt dort nicht in den Score.")
    for bid, b in basen.items():
        if b["tide"]["status"]["status"] == "ausgefallen" and not b["manuell"]:
            alarme.append("Gezeitenmodell nicht erreichbar. Die Tide fließt nicht in den Score ein.")
        elif b["tide"]["hinweis"]:
            alarme.append("Gezeiten: " + b["tide"]["hinweis"])

    standard = config.basis_fuer(cfg["basen"], anzeige) or aktuelle
    return {
        "jetzt": jetzt, "jetzt_lokal": jetzt_l, "daten_stand": roh.get("abgerufen_um"), "modus": modus,
        "anzeige": anzeige, "label": label, "tage": reise, "ansichten": ansichten, "standard": standard["id"],
        "basen": basen, "spots": spots, "alarme": alarme, "laeufe": modelllaeufe(roh, cfg, jetzt, max_alter),
        "modelle": modelle,
    }
