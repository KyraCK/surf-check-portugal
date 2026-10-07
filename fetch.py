#!/usr/bin/env python3
"""Holt alle Rohdaten und speichert sie in data/rohdaten.json.

Jede Quelle bekommt einen eigenen Eintrag mit Status:
  ok        frisch abgerufen
  veraltet  Abruf fehlgeschlagen, es gibt nur noch die Daten vom letzten Erfolg
  fehler    Abruf fehlgeschlagen und keine älteren Daten vorhanden

Nichts wird geraten: Ob veraltete Daten noch angezeigt werden, entscheidet
auswerten.py anhand von config/quellen.toml (max_alter_stunden).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import quellen
from netz import AbrufFehler

DATEI = Path(__file__).resolve().parent / "data" / "rohdaten.json"


def lade_alt() -> dict:
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"quellen": {}}


def alle_aufgaben(cfg: dict, jetzt: datetime):
    """Liste von (Schlüssel-Liste, Funktion). Die Funktion liefert pro Schlüssel ein Ergebnis."""
    aufgaben = []
    modelle = cfg["quellen"]["modelle"]
    wetter_modelle = [m["wetter"] for m in modelle]
    # Orte, die in mehreren Spots vorkommen (z. B. Arrifana), nur einmal abfragen
    orte = {}
    for basis in cfg["basen"]:
        for sid in basis.get("spots", []):
            sp = cfg["spots"][sid]
            ort = (sp["lat"], sp["lon"])
            if sid not in orte.setdefault(ort, []):
                orte[ort].append(sid)
    ort_liste = list(orte)
    for i in range(0, len(ort_liste), 10):  # höchstens 10 Orte pro Anfrage
        teil = ort_liste[i:i + 10]
        sids_je_ort = [orte[o] for o in teil]

        def verteilen(ergebnisse, sids_je_ort=sids_je_ort):
            return [e for e, sids in zip(ergebnisse, sids_je_ort) for _ in sids]
        schluessel = [f"wetter:{s}" for sids in sids_je_ort for s in sids]
        aufgaben.append((schluessel, lambda t=teil, v=verteilen: v(quellen.hole_wetter_mehrere(t, wetter_modelle))))
        for m in modelle:
            schluessel = [f"welle:{s}:{m['name']}" for sids in sids_je_ort for s in sids]
            aufgaben.append((schluessel, lambda t=teil, v=verteilen, m=m: v(quellen.hole_wellen_mehrere(t, m["welle"]))))
    gesehen = set()
    for basis in cfg["basen"]:
        erster = cfg["spots"][basis["spots"][0]]
        aufgaben.append(([f"tide_modell:{basis['id']}"],
                         lambda e=erster: [quellen.hole_tide_modell(e["lat"], e["lon"])]))
        if basis.get("pegel"):
            aufgaben.append(([f"pegel:{basis['id']}"], lambda b=basis: [quellen.hole_pegel(
                b["pegel"], jetzt - timedelta(days=4), jetzt)]))
        if basis.get("ipma_stadt"):
            aufgaben.append(([f"ipma_stadt:{basis['id']}"], lambda b=basis: [quellen.hole_ipma_stadt(b["ipma_stadt"])]))
        if basis.get("ipma_see") and "see" not in gesehen:
            gesehen.add("see")
            for tag in range(3):  # IPMA liefert Meer-Vorhersagen nur für 3 Tage, die Datei gilt für alle Küstenpunkte
                aufgaben.append(([f"ipma_see:{tag}"], lambda t=tag: [quellen.hole_ipma_see(t)]))
    aufgaben.append((["ipma_warnungen"], lambda: [quellen.hole_ipma_warnungen()]))
    for m in modelle:
        aufgaben.append(([f"lauf:welle:{m['lauf_welle']}"], lambda m=m: [quellen.hole_modelllauf("marine", m["lauf_welle"])]))
        aufgaben.append(([f"lauf:wetter:{m['lauf_wetter']}"], lambda m=m: [quellen.hole_modelllauf("forecast", m["lauf_wetter"])]))
    return aufgaben


def hole_alles(cfg: dict, jetzt: datetime, alt: dict, ausgabe=print) -> dict:
    neu = {"abgerufen_um": quellen.iso(jetzt), "quellen": {}}
    for schluessel, funktion in alle_aufgaben(cfg, jetzt):
        try:
            ergebnisse = funktion()
            if any(r["daten"] is None for r in ergebnisse):
                raise AbrufFehler("Quelle liefert keine Daten (HTTP 204)")
            for k, r in zip(schluessel, ergebnisse):
                neu["quellen"][k] = {"status": "ok", "abgerufen_um": quellen.iso(jetzt), "url": r["url"], "daten": r["daten"]}
            ausgabe(f"  ok        {schluessel[0]}" + (f" (+{len(schluessel) - 1} weitere)" if len(schluessel) > 1 else ""))
        except AbrufFehler as e:
            for k in schluessel:
                vorher = alt.get("quellen", {}).get(k)
                if vorher and vorher.get("daten") is not None:
                    neu["quellen"][k] = dict(vorher, status="veraltet", fehler=str(e))
                else:
                    neu["quellen"][k] = {"status": "fehler", "abgerufen_um": None, "url": None, "daten": None, "fehler": str(e)}
            vorhanden = sum(1 for k in schluessel if neu["quellen"][k]["status"] == "veraltet")
            ausgabe(f"  {'VERALTET' if vorhanden else 'FEHLER  '}  {schluessel[0]}"
                    + (f" (+{len(schluessel) - 1} weitere)" if len(schluessel) > 1 else "") + f": {e}")
    return neu


def speichere(rohdaten: dict) -> None:
    DATEI.parent.mkdir(exist_ok=True)
    DATEI.write_text(json.dumps(rohdaten, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    try:
        cfg = config.lade()
    except config.ConfigFehler as e:
        print("Fehler in der Konfiguration:\n  " + str(e))
        return 1
    jetzt = datetime.now(timezone.utc)
    print(f"Abruf {quellen.iso(jetzt)}")
    rohdaten = hole_alles(cfg, jetzt, lade_alt())
    speichere(rohdaten)
    stati = [q["status"] for q in rohdaten["quellen"].values()]
    print(f"\n{stati.count('ok')} von {len(stati)} Quellen aktuell, {stati.count('veraltet')} veraltet, {stati.count('fehler')} ohne Daten.")
    return 0 if "fehler" not in stati else 2


if __name__ == "__main__":
    sys.exit(main())
