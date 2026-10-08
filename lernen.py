#!/usr/bin/env python3
"""Lernen aus Beobachtungen: Wie viel von der Modellwelle kommt an einem Spot wirklich an?

Für jede Beobachtung in config/beobachtungen.toml werden die Modellwerte der Stunden um die
Uhrzeit herum (wirksame Höhe am Spot, wie sie auch die Bewertung nutzt, aber ohne jeden Faktor)
mit der gesehenen Höhe verglichen. Daraus entsteht pro Spot ein vorsichtiger Faktor, der bei
jedem Lauf zum manuellen Korrekturfaktor aus spots.toml dazukommt.

Aufruf zum Nachsehen:  python3 lernen.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from statistics import mean, median
from zoneinfo import ZoneInfo

import wellen

TZ = ZoneInfo("Europe/Lisbon")
UTC = timezone.utc
MAX_VERGANGENE_TAGE = 92  # so weit zurück liefert Open-Meteo Daten


def aktive_beobachtungen(cfg: dict, jetzt: datetime) -> list:
    """Beobachtungen, die schon stattgefunden haben und noch nicht zu alt sind (mit Zeitpunkt in Ortszeit)."""
    max_alter = timedelta(days=cfg["scoring"]["lernen"]["max_alter_tage"])
    aus = []
    for b in cfg.get("beobachtungen", []):
        zeit = datetime(b["datum"].year, b["datum"].month, b["datum"].day, b["uhr"], tzinfo=TZ)
        if zeit > jetzt or jetzt - zeit > max_alter:
            continue
        aus.append(dict(b, zeit=zeit))
    return sorted(aus, key=lambda x: x["zeit"])


def noetige_tage(cfg: dict, jetzt: datetime) -> dict:
    """Für welche Spots werden Modelldaten aus der Vergangenheit gebraucht, und wie viele Tage zurück?"""
    tage = {}
    for b in aktive_beobachtungen(cfg, jetzt):
        zurueck = min(MAX_VERGANGENE_TAGE, (jetzt - b["zeit"]).days + 2)
        tage[b["spot"]] = max(tage.get(b["spot"], 0), zurueck)
    return tage


def _modellhoehe(daten: dict, spot: dict, regeln: dict, zeit: datetime):
    """Mittlere am Spot wirksame Modellhöhe (m) in den drei Stunden um `zeit`, ohne Faktor."""
    hoehen = []
    for k in (-1, 0, 1):
        t = (zeit + timedelta(hours=k)).astimezone(UTC)
        kombis = {n: {"welle": w[t]} for n, w in daten.items() if t in w}
        if kombis:
            hoehen += [x["hoehe"] for x in wellen.wirksame_wellen(kombis, spot, regeln).values()]
    return mean(hoehen) if hoehen else None


def _gelernt(verhaeltnisse: list, vorsicht: float, grenzen: list) -> float:
    """Vorsichtiger Faktor aus den Verhältnissen: 1 + (Median - 1) x n / (n + vorsicht), begrenzt."""
    n = len(verhaeltnisse)
    f = 1 + (median(verhaeltnisse) - 1) * n / (n + vorsicht)
    return max(grenzen[0], min(grenzen[1], f))


def berechne(cfg: dict, roh: dict, jetzt: datetime) -> dict:
    """Gelernte Faktoren je Spot und die Vergleichszeilen für die Anzeige."""
    le = cfg["scoring"]["lernen"]
    regeln = cfg["scoring"]
    vorsicht, grenzen = le["vorsicht"], le["faktor_grenzen"]
    anteil = le["anteil_andere_spots_prozent"] / 100.0
    max_alter = cfg["quellen"]["daten"]["max_alter_stunden"]

    cache = {}
    zeilen = []
    for b in aktive_beobachtungen(cfg, jetzt):
        sid = b["spot"]
        spot = cfg["spots"][sid]
        if sid not in cache:
            cache[sid] = wellen.lies_wellen(roh, cfg, sid, jetzt, max_alter, praefix="beob")[0]
        modell = _modellhoehe(cache[sid], spot, regeln, b["zeit"])
        manuell = spot["korrekturfaktor"]
        z = {"beobachtung": b, "spot": sid, "modell_m": modell, "manuell": manuell, "verhaeltnis": None, "status": "ok"}
        if modell is None:
            z["status"] = "keine Modelldaten für diese Zeit"
        elif modell * manuell < le["mindest_modellhoehe_m"]:
            z["status"] = "Modell zu klein für einen Vergleich"
        else:
            z["verhaeltnis"] = b["hoehe_m"] / (modell * manuell)
        zeilen.append(z)

    je_spot = {}
    for z in zeilen:
        if z["verhaeltnis"] is not None:
            je_spot.setdefault(z["spot"], []).append(z["verhaeltnis"])

    # Verhältnisse je Basis: Beobachtungen an einem Spot sagen auch etwas über die Nachbarn
    je_basis = {}
    for basis in cfg["basen"]:
        werte = [v for sid in basis.get("spots", []) for v in je_spot.get(sid, [])]
        if werte:
            je_basis[basis["id"]] = werte

    faktoren = {}
    for sid, spot in cfg["spots"].items():
        manuell = spot["korrekturfaktor"]
        eigene = je_spot.get(sid)
        if eigene:
            lern, n, quelle = _gelernt(eigene, vorsicht, grenzen), len(eigene), "eigene Beobachtungen"
        else:
            lern, n, quelle = 1.0, 0, "keine"
            for basis in cfg["basen"]:
                if sid in basis.get("spots", []) and basis["id"] in je_basis:
                    andere = je_basis[basis["id"]]
                    lern = 1 + (_gelernt(andere, vorsicht, grenzen) - 1) * anteil
                    n, quelle = len(andere), "andere Spots der Basis"
                    break
        faktoren[sid] = {"manuell": manuell, "lern": lern, "gesamt": manuell * lern, "n": n, "quelle": quelle}

    gueltig = [z for z in zeilen if z["verhaeltnis"] is not None]
    pruefung = None
    if len(gueltig) >= 3:
        # Ehrlicher Test: Wie gut hätte der Faktor eine Beobachtung vorhergesagt, die er nicht kannte?
        vorher, nachher = [], []
        for i, z in enumerate(gueltig):
            rest = [y["verhaeltnis"] for j, y in enumerate(gueltig) if j != i and y["spot"] == z["spot"]]
            l = _gelernt(rest, vorsicht, grenzen) if rest else 1.0
            basis_modell = z["modell_m"] * z["manuell"]
            vorher.append(abs(basis_modell - z["beobachtung"]["hoehe_m"]))
            nachher.append(abs(basis_modell * l - z["beobachtung"]["hoehe_m"]))
        pruefung = {"n": len(gueltig), "fehler_vorher_m": mean(vorher), "fehler_nachher_m": mean(nachher)}
    return {
        "faktoren": faktoren, "zeilen": zeilen, "anzahl": len(gueltig), "pruefung": pruefung,
        "median_verhaeltnis": median([z["verhaeltnis"] for z in gueltig]) if gueltig else None,
    }


def main() -> int:
    import json
    from pathlib import Path

    import config
    try:
        cfg = config.lade()
    except config.ConfigFehler as e:
        print("Fehler in der Konfiguration:\n  " + str(e))
        return 1
    datei = Path(__file__).resolve().parent / "data" / "rohdaten.json"
    if not datei.exists():
        print("Es gibt noch keine Daten. Zuerst  python3 fetch.py  ausführen.")
        return 1
    roh = json.loads(datei.read_text(encoding="utf-8"))
    jetzt = datetime.now(UTC)
    erg = berechne(cfg, roh, jetzt)
    print(f"Beobachtungen in config/beobachtungen.toml: {len(cfg['beobachtungen'])}, davon nutzbar: {erg['anzahl']}\n")
    if erg["zeilen"]:
        print(f"{'Datum':<11}{'Uhr':>4}  {'Spot':<22}{'gesehen':>8}{'Modell':>8}{'Verhältnis':>12}  Hinweis")
        for z in erg["zeilen"]:
            b = z["beobachtung"]
            modell = "-" if z["modell_m"] is None else f"{z['modell_m'] * z['manuell']:.2f}"
            verh = "-" if z["verhaeltnis"] is None else f"{z['verhaeltnis']:.2f}"
            name = cfg["spots"][z["spot"]]["name"][:21]
            print(f"{b['datum']:%d.%m.%Y} {b['uhr']:>3}  {name:<22}{b['hoehe_m']:>8.2f}{modell:>8}{verh:>12}  {'' if z['status'] == 'ok' else z['status']}")
        print("\n(gesehen und Modell in Metern, Modell = am Spot wirksame Höhe vor dem Lernfaktor)\n")
    print(f"{'Spot':<28}{'gelernt':>8}{'manuell':>9}{'gesamt':>8}  Grundlage")
    for sid, f in erg["faktoren"].items():
        if f["quelle"] != "keine":
            print(f"{cfg['spots'][sid]['name'][:27]:<28}{f['lern']:>8.2f}{f['manuell']:>9.2f}{f['gesamt']:>8.2f}  {f['quelle']} ({f['n']})")
    if erg["pruefung"]:
        p = erg["pruefung"]
        print(f"\nTest ohne Mogeln ({p['n']} Beobachtungen): mittlere Abweichung {p['fehler_vorher_m']:.2f} m ohne Lernen, {p['fehler_nachher_m']:.2f} m mit Lernen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
