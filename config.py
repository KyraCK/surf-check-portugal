"""Lädt und prüft die Konfigurationsdateien in config/.

Fehlermeldungen sind für Menschen geschrieben, nicht für Entwickler: Sie
nennen Datei, Abschnitt und Feld und sagen, was zu tun ist.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
try:
    import tomllib as _toml  # ab Python 3.11 eingebaut
except ImportError:  # Python 3.9 und 3.10
    import tomli as _toml


class ConfigFehler(Exception):
    """Etwas in config/*.toml stimmt nicht. Der Text erklärt, was."""


def _lade(name: str) -> dict:
    pfad = ROOT / "config" / name
    try:
        with open(pfad, "rb") as f:
            return _toml.load(f)
    except FileNotFoundError:
        raise ConfigFehler(f"Die Datei config/{name} fehlt.")
    except _toml.TOMLDecodeError as e:
        raise ConfigFehler(
            f"config/{name} lässt sich nicht lesen: {e}. "
            "Meist fehlt ein Anführungszeichen oder eine Klammer, oder eine Kommazahl "
            "hat ein Komma statt eines Punkts (richtig: 1.4)."
        )


def _zahl(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _pruefe_kennlinie(wert, wo: str, y_max: float) -> None:
    ok = isinstance(wert, list) and len(wert) >= 2 and all(
        isinstance(p, list) and len(p) == 2 and _zahl(p[0]) and _zahl(p[1]) for p in wert
    )
    if not ok:
        raise ConfigFehler(
            f"{wo}: Das muss eine Kennlinie sein, also mindestens zwei Wertepaare, "
            "zum Beispiel [[0.6, 0], [1.4, 10]]."
        )
    xs = [p[0] for p in wert]
    if len(set(xs)) != len(xs):
        raise ConfigFehler(f"{wo}: Der linke Wert darf in zwei Paaren nicht gleich sein.")
    for x, y in wert:
        if not 0 <= y <= y_max:
            raise ConfigFehler(f"{wo}: Der rechte Wert {y} muss zwischen 0 und {y_max:g} liegen.")


def _pruefe_sektor(wert, wo: str) -> None:
    if not (isinstance(wert, list) and len(wert) == 2 and all(_zahl(g) and 0 <= g <= 360 for g in wert)):
        raise ConfigFehler(f"{wo}: Das muss ein Bereich aus zwei Gradzahlen zwischen 0 und 360 sein, zum Beispiel [207, 332].")


def pruefe_scoring(s: dict) -> None:
    f = "config/scoring.toml"
    for abschnitt in ("skala", "allgemein", "swell_richtung", "spot_groesse", "tide", "sicherheit", "zeitfenster", "urteile", "baden", "ausweich", "personen"):
        if abschnitt not in s:
            raise ConfigFehler(f"{f}: Der Abschnitt [{abschnitt}] fehlt.")
    _pruefe_kennlinie(s["allgemein"].get("zu_lange_periode_prozent"), f"{f} [allgemein] zu_lange_periode_prozent", 100)
    _pruefe_kennlinie(s["swell_richtung"].get("abstand_grad_prozent"), f"{f} [swell_richtung] abstand_grad_prozent", 100)
    _pruefe_kennlinie(s["spot_groesse"].get("ueber_max_m_prozent"), f"{f} [spot_groesse] ueber_max_m_prozent", 100)
    if "bereiche" not in s["tide"]:
        raise ConfigFehler(f"{f}: Der Abschnitt [tide.bereiche] fehlt.")
    for name, b in s["tide"]["bereiche"].items():
        if not (isinstance(b, list) and len(b) == 2 and all(_zahl(v) and 0 <= v <= 1 for v in b) and b[0] <= b[1]):
            raise ConfigFehler(f"{f} [tide.bereiche] {name}: Das muss [von, bis] mit Zahlen zwischen 0 und 1 sein, von kleiner als bis.")
    laenge = s["zeitfenster"].get("laenge_stunden")
    if not (isinstance(laenge, int) and not isinstance(laenge, bool) and 1 <= laenge <= 6):
        raise ConfigFehler(f"{f} [zeitfenster] laenge_stunden: Das muss eine ganze Zahl von 1 bis 6 sein.")
    for wort in ("zu_klein", "zu_gross", "kurze_periode", "windig", "swell_passt_nicht", "tide_passt_nicht", "sauber", "gut", "surfbar"):
        if not isinstance(s["urteile"].get(wort), str):
            raise ConfigFehler(f"{f} [urteile] {wort}: Das Wort fehlt oder steht nicht in Anführungszeichen.")
    b = s["baden"]
    for feld, y_max in (("temperatur_c", 100), ("wind_kn", 100), ("regen_prozent", 100), ("tide", 100)):
        _pruefe_kennlinie(b.get(feld), f"{f} [baden] {feld}", y_max)
    if not (_zahl(b.get("von_uhr")) and _zahl(b.get("bis_uhr")) and 0 <= b["von_uhr"] < b["bis_uhr"] <= 24):
        raise ConfigFehler(f"{f} [baden]: von_uhr und bis_uhr müssen Uhrzeiten zwischen 0 und 24 sein, von kleiner als bis.")
    if not _zahl(b.get("mindest_prozent")):
        raise ConfigFehler(f"{f} [baden] mindest_prozent: Das muss eine Zahl sein.")
    if not (_zahl(s["ausweich"].get("vorsprung_punkte")) and s["ausweich"]["vorsprung_punkte"] >= 0):
        raise ConfigFehler(f"{f} [ausweich] vorsprung_punkte: Das muss eine Zahl ab 0 sein.")
    if not s["personen"]:
        raise ConfigFehler(f"{f}: Es ist keine Person angelegt ([personen.p1] und so weiter).")
    for pid, p in s["personen"].items():
        wo = f"{f} [personen.{pid}]"
        for feld in ("label", "farbe_dunkel", "farbe_hell"):
            if not isinstance(p.get(feld), str):
                raise ConfigFehler(f"{wo}: Das Feld '{feld}' fehlt oder ist kein Text in Anführungszeichen.")
        for feld in ("kurz", "beschreibung"):
            if feld in p and not isinstance(p[feld], str):
                raise ConfigFehler(f"{wo}: '{feld}' muss ein Text in Anführungszeichen sein.")
        for feld in ("farbe_dunkel", "farbe_hell"):
            w = p[feld]
            if not (len(w) == 7 and w[0] == "#" and all(z in "0123456789abcdefABCDEF" for z in w[1:])):
                raise ConfigFehler(f"{wo}: '{feld}' muss eine Farbe wie \"#C09CEB\" sein (Raute, dann sechs Zeichen).")
        _pruefe_kennlinie(p.get("hoehe"), f"{wo} hoehe", 10)
        for feld in ("periode", "wind_ablandig", "wind_seitlich", "wind_auflandig"):
            _pruefe_kennlinie(p.get(feld), f"{wo} {feld}", 100)


def pruefe_spots(sp: dict, scoring: dict) -> None:
    f = "config/spots.toml"
    if not sp.get("spots"):
        raise ConfigFehler(f"{f}: Es ist kein Spot angelegt ([spots.moledo] und so weiter).")
    if not sp.get("basen"):
        raise ConfigFehler(f"{f}: Es ist keine Basis angelegt ([[basen]]).")
    tiden = set(scoring["tide"]["bereiche"])
    for sid, s in sp["spots"].items():
        wo = f"{f} [spots.{sid}]"
        if not isinstance(s.get("name"), str):
            raise ConfigFehler(f"{wo}: Das Feld 'name' fehlt.")
        for feld, lo, hi in (("lat", -90, 90), ("lon", -180, 180)):
            if not (_zahl(s.get(feld)) and lo <= s[feld] <= hi):
                raise ConfigFehler(f"{wo}: '{feld}' fehlt oder ist keine Zahl zwischen {lo} und {hi}.")
        _pruefe_sektor(s.get("swell_dir_deg"), f"{wo} swell_dir_deg")
        _pruefe_sektor(s.get("wind_dir_deg"), f"{wo} wind_dir_deg")
        if "tide" in s and s["tide"] not in tiden:
            raise ConfigFehler(f"{wo}: 'tide' muss eines von {', '.join(sorted(tiden))} sein, steht aber auf {s.get('tide')!r}. "
                               "Wenn es keine Angabe gibt, lösche die Zeile.")
        if "ausweich" in s and not isinstance(s["ausweich"], bool):
            raise ConfigFehler(f"{wo}: 'ausweich' muss true oder false sein (ohne Anführungszeichen).")
        if "fahrzeit_min" in s and not (_zahl(s["fahrzeit_min"]) and s["fahrzeit_min"] >= 0):
            raise ConfigFehler(f"{wo}: 'fahrzeit_min' muss eine Zahl ab 0 sein.")
        if not (_zahl(s.get("korrekturfaktor")) and s["korrekturfaktor"] > 0):
            raise ConfigFehler(f"{wo}: 'korrekturfaktor' fehlt oder ist nicht größer als 0 (Standard: 1.0).")
        for feld in ("groesse_min_m", "groesse_max_m"):
            if feld in s and not (_zahl(s[feld]) and s[feld] >= 0):
                raise ConfigFehler(f"{wo}: '{feld}' muss eine Zahl ab 0 sein. Wenn es keine Angabe gibt, lösche die Zeile.")
        if "groesse_min_m" in s and "groesse_max_m" in s and s["groesse_min_m"] > s["groesse_max_m"]:
            raise ConfigFehler(f"{wo}: groesse_min_m ist größer als groesse_max_m.")
    for b in sp["basen"]:
        wo = f"{f} [[basen]] {b.get('id', '?')}"
        for feld in ("id", "name"):
            if not isinstance(b.get(feld), str):
                raise ConfigFehler(f"{wo}: Das Feld '{feld}' fehlt.")
        if not (isinstance(b.get("von"), date) and isinstance(b.get("bis"), date)):
            raise ConfigFehler(f"{wo}: 'von' und 'bis' müssen Datumsangaben wie 2026-10-07 sein (ohne Anführungszeichen).")
        if b["von"] > b["bis"]:
            raise ConfigFehler(f"{wo}: 'von' liegt nach 'bis'.")
        if "pegel_test" in b and not isinstance(b["pegel_test"], str):
            raise ConfigFehler(f"{wo}: 'pegel_test' muss ein Text in Anführungszeichen sein.")
        for sid in b.get("spots", []):
            if sid not in sp["spots"]:
                raise ConfigFehler(f"{wo}: Der Spot '{sid}' steht in der Liste, ist aber nirgends als [spots.{sid}] angelegt.")


def pruefe_quellen(q: dict) -> None:
    f = "config/quellen.toml"
    alter = q.get("daten", {}).get("max_alter_stunden")
    if not (_zahl(alter) and alter > 0):
        raise ConfigFehler(f"{f} [daten] max_alter_stunden: Das muss eine Zahl größer als 0 sein.")
    if not q.get("modelle"):
        raise ConfigFehler(f"{f}: Es ist kein Modell eingetragen ([[modelle]]).")
    for m in q["modelle"]:
        for feld in ("name", "welle", "wetter", "lauf_welle", "lauf_wetter"):
            if not isinstance(m.get(feld), str):
                raise ConfigFehler(f"{f} [[modelle]] {m.get('name', '?')}: Das Feld '{feld}' fehlt.")


def pruefe_manuell(m: dict) -> None:
    f = "config/gezeiten_manuell.toml"
    for e in m.get("gezeiten", []):
        if not isinstance(e.get("datum"), date):
            raise ConfigFehler(f"{f}: 'datum' muss ein Datum wie 2026-10-08 sein (ohne Anführungszeichen).")
        for feld in ("hochwasser", "niedrigwasser"):
            for zeit in e.get(feld, []):
                ok = isinstance(zeit, str) and len(zeit) == 5 and zeit[2] == ":" and zeit[:2].isdigit() and zeit[3:].isdigit() \
                    and int(zeit[:2]) < 24 and int(zeit[3:]) < 60
                if not ok:
                    raise ConfigFehler(f"{f} {e['datum']} {feld}: '{zeit}' ist keine Uhrzeit. Richtig: \"02:11\" (mit Anführungszeichen).")
        if not (e.get("hochwasser") or e.get("niedrigwasser")):
            raise ConfigFehler(f"{f} {e['datum']}: Es fehlen Hoch- und Niedrigwasser.")


def pruefe_ausfluege(a: dict, basen: list) -> None:
    f = "config/ausfluege.toml"
    r = a.get("regeln", {})
    for feld in ("nordwind_ab_kn", "regen_ab_prozent", "starkregen_ab_prozent", "warm_ab_c", "ruhig_bis_kn",
                 "klar_regen_unter_prozent", "klar_wolken_unter_prozent", "vorschlaege_pro_tag"):
        if not _zahl(r.get(feld)):
            raise ConfigFehler(f"{f} [regeln] {feld}: Das fehlt oder ist keine Zahl.")
    _pruefe_sektor(r.get("nordwind_sektor_grad"), f"{f} [regeln] nordwind_sektor_grad")
    ids = {b["id"] for b in basen}
    erlaubt = {"jedes_wetter", "nordwind", "regen", "warm_ruhig", "klar"}
    for z in a.get("ausfluege", []):
        wo = f"{f} {z.get('name', '?')}"
        if z.get("basis") not in ids:
            raise ConfigFehler(f"{wo}: 'basis' muss eine id aus spots.toml sein ({', '.join(sorted(ids))}), steht aber auf {z.get('basis')!r}.")
        for feld in ("name", "beschreibung"):
            if not isinstance(z.get(feld), str):
                raise ConfigFehler(f"{wo}: Das Feld '{feld}' fehlt.")
        if z.get("symbol") not in {"mountain", "castle", "swim", "trail", "tree", "lighthouse", "city"}:
            raise ConfigFehler(f"{wo}: 'symbol' muss eines von mountain, castle, swim, trail, tree, lighthouse, city sein.")
        fz = z.get("fahrzeit_min")
        ok = _zahl(fz) or (isinstance(fz, list) and len(fz) == 2 and all(_zahl(x) for x in fz) and fz[0] <= fz[1])
        if not ok:
            raise ConfigFehler(f"{wo}: 'fahrzeit_min' muss eine Zahl (30) oder ein Bereich ([30, 40]) sein.")
        bed = z.get("bedingung")
        if not (isinstance(bed, list) and bed and all(b in erlaubt for b in bed)):
            raise ConfigFehler(f"{wo}: 'bedingung' muss eine Liste aus {', '.join(sorted(erlaubt))} sein.")
        if z.get("dauer") not in ("kurz", "halbtag", "ganztag"):
            raise ConfigFehler(f"{wo}: 'dauer' muss kurz, halbtag oder ganztag sein.")
        if z.get("hund") not in ("erlaubt_leine", "unklar"):
            raise ConfigFehler(f"{wo}: 'hund' muss erlaubt_leine oder unklar sein.")


def lade() -> dict:
    """Liest alle Konfigurationsdateien, prüft sie und gibt sie zusammen zurück."""
    scoring = _lade("scoring.toml")
    pruefe_scoring(scoring)
    spots = _lade("spots.toml")
    pruefe_spots(spots, scoring)
    quellen = _lade("quellen.toml")
    pruefe_quellen(quellen)
    manuell = _lade("gezeiten_manuell.toml")
    pruefe_manuell(manuell)
    ausfluege = _lade("ausfluege.toml")
    pruefe_ausfluege(ausfluege, spots["basen"])
    return {"scoring": scoring, "spots": spots["spots"], "basen": spots["basen"],
            "quellen": quellen, "manuell": manuell.get("gezeiten", []),
            "ausfluege": ausfluege["ausfluege"], "ausflug_regeln": ausfluege["regeln"]}


def basis_fuer(basen: list, tag: date) -> dict | None:
    """Die Basis, die an diesem Tag gilt (None, wenn keine passt)."""
    for b in basen:
        if b["von"] <= tag <= b["bis"]:
            return b
    return None
