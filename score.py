"""Bewertet Surf-Bedingungen nach den Regeln in config/scoring.toml.

Reine Rechenfunktionen: kein Netzwerk, keine Dateien. Was hier gerechnet wird,
steht in config/scoring.toml oben ausführlich erklärt.
"""
from __future__ import annotations

import math


def kennlinie(punkte: list, x: float) -> float:
    """Verbindet die Wertepaare mit geraden Linien. Außerhalb bleibt der erste/letzte Wert."""
    pts = sorted(punkte)
    if x <= pts[0][0]:
        return float(pts[0][1])
    if x >= pts[-1][0]:
        return float(pts[-1][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise AssertionError("unerreichbar")


def abstand_zum_sektor(grad: float, von: float, bis: float) -> float:
    """Wie viele Grad `grad` außerhalb des Bereichs von..bis liegt (0 = drin).

    Der Bereich läuft im Uhrzeigersinn und darf über Nord (0/360) gehen.
    """
    breite = (bis - von) % 360
    pos = (grad - von) % 360
    if pos <= breite:
        return 0.0
    return min(pos - breite, 360 - pos)


def windart(wind_richtung: float, ablandig: list, seitlich_bis_grad: float) -> str:
    """'ablandig', 'seitlich' oder 'auflandig' für Wind aus `wind_richtung`."""
    d = abstand_zum_sektor(wind_richtung, ablandig[0], ablandig[1])
    if d == 0:
        return "ablandig"
    return "seitlich" if d <= seitlich_bis_grad else "auflandig"


def tide_prozent(tide_rel: float, bereich: list, abzug_prozent: float, voller_abzug_ab: float) -> float:
    """Anteil der Punkte (in %) nach der Tide. 100 = Tide liegt im gewünschten Bereich."""
    von, bis = bereich
    abstand = 0.0 if von <= tide_rel <= bis else min(abs(tide_rel - von), abs(tide_rel - bis))
    return 100.0 - abzug_prozent * min(1.0, abstand / voller_abzug_ab)


def runde(x: float) -> int:
    """Kaufmännisch runden (2,5 wird 3), nicht auf gerade Zahlen wie Python."""
    return int(math.floor(x + 0.5))


def bewerte(bed: dict, spot: dict, person: dict, regeln: dict) -> dict:
    """Score einer Person für einen Spot und eine Stunde.

    bed (Bedingungen), alle Zahlen oder None, wenn die Quelle nichts liefert:
      hoehe_m         Wellenhöhe laut Modell (vor dem Korrekturfaktor)
      periode_s       Periode in Sekunden
      swell_richtung  Grad, aus der der Swell kommt
      wind_kn         Windstärke in Knoten
      boeen_kn        Böen in Knoten
      wind_richtung   Grad, aus der der Wind kommt
      tide_rel        0 = Niedrigwasser, 1 = Hochwasser
      tide_quelle     'modell' oder 'manuell'

    Fehlt Höhe, Periode, Windstärke oder Windrichtung, gibt es keinen Score
    (punkte = None): Es wird nichts geraten. Fehlen Swell-Richtung oder Tide,
    gibt es keinen Abzug dafür, das steht dann in "luecken".
    """
    fehlt = [name for name, wert in (
        ("Wellenhöhe", bed.get("hoehe_m")), ("Periode", bed.get("periode_s")),
        ("Windstärke", bed.get("wind_kn")), ("Windrichtung", bed.get("wind_richtung")),
    ) if wert is None]
    if fehlt:
        return {"punkte": None, "fehlt": fehlt}

    allg = regeln["allgemein"]
    luecken = []

    h = bed["hoehe_m"] * spot["korrekturfaktor"]
    grund = kennlinie(person["hoehe"], h)
    if "groesse_min_m" in spot and h < spot["groesse_min_m"]:
        grund = 0.0

    anteile = {}  # Name -> Prozent der Punkte, die bleiben

    p = bed["periode_s"]
    anteile["periode"] = kennlinie(person["periode"], p) * kennlinie(allg["zu_lange_periode_prozent"], p) / 100.0

    if bed.get("swell_richtung") is None:
        anteile["swell"] = 100.0
        luecken.append("Swell-Richtung")
    else:
        d = abstand_zum_sektor(bed["swell_richtung"], *spot["swell_dir_deg"])
        anteile["swell"] = kennlinie(regeln["swell_richtung"]["abstand_grad_prozent"], d)

    wind = bed["wind_kn"]
    if bed.get("boeen_kn") is not None:
        wind = wind + allg["boeen_anteil"] * max(0.0, bed["boeen_kn"] - wind)
    art = windart(bed["wind_richtung"], spot["wind_dir_deg"], allg["seitlich_bis_grad"])
    anteile["wind"] = kennlinie(person["wind_" + art], wind)

    t = regeln["tide"]
    if "tide" not in spot:
        anteile["tide"] = 100.0   # für diesen Spot gibt es keine Tide-Angabe: keine Wirkung
    elif bed.get("tide_rel") is None:
        anteile["tide"] = 100.0
        luecken.append("Tide")
    else:
        abzug = t["abzug_manuell_prozent"] if bed.get("tide_quelle") == "manuell" else t["abzug_modell_prozent"]
        anteile["tide"] = tide_prozent(bed["tide_rel"], t["bereiche"][spot["tide"]], abzug, t["voller_abzug_ab_abstand"])

    if "groesse_max_m" in spot:
        anteile["groesse"] = kennlinie(regeln["spot_groesse"]["ueber_max_m_prozent"], max(0.0, h - spot["groesse_max_m"]))
    else:
        anteile["groesse"] = 100.0

    roh = grund
    for a in anteile.values():
        roh *= a / 100.0
    punkte = max(1, min(10, runde(roh)))

    # Was drückt den Score am stärksten? (für das Urteil in der Tabelle)
    kandidaten = dict(anteile)
    kandidaten["hoehe"] = grund * 10.0
    schwach = min(kandidaten, key=kandidaten.get)

    return {
        "punkte": punkte, "roh": roh, "hoehe_spot_m": h, "grundpunkte": grund,
        "anteile": anteile, "windart": art, "wind_effektiv_kn": wind,
        "schwachpunkt": schwach, "luecken": luecken,
    }


def stufe(punkte: int, skala: dict) -> str:
    """Wort zum Score: lohnt kaum / surfbar / gut / Pflichttermin."""
    if punkte <= skala["lohnt_kaum_bis"]:
        return "lohnt kaum"
    if punkte <= skala["surfbar_bis"]:
        return "surfbar"
    if punkte <= skala["gut_bis"]:
        return "gut"
    return "Pflichttermin"


def sicherheit(punkte_je_modell: list, regeln: dict) -> str:
    """'hoch', 'mittel' oder 'niedrig', je nachdem wie weit die Modelle auseinanderliegen."""
    werte = [p for p in punkte_je_modell if p is not None]
    if len(werte) < 2:
        return "niedrig"  # ein einzelnes Modell bestätigt sich selbst nicht
    spanne = max(werte) - min(werte)
    s = regeln["sicherheit"]
    if spanne <= s["hoch_bis_spanne"]:
        return "hoch"
    return "mittel" if spanne <= s["mittel_bis_spanne"] else "niedrig"


def schwellen(person: dict, regeln: dict, periode_s: float = 10.0) -> dict:
    """Ab welcher Wellenhöhe (Meter) wird es 'surfbar' und 'gut', wenn sonst alles passt?

    Rechnet mit einem Spot ohne Besonderheiten, `periode_s` Sekunden Periode, 3 kn ablandigem Wind
    und passender Swell-Richtung. So stehen auf der Seite immer die Zahlen, die wirklich in den Regeln stecken.
    """
    spot = {"korrekturfaktor": 1.0, "swell_dir_deg": [200, 340], "wind_dir_deg": [60, 120], "tide": "alle"}
    ziele = {"surfbar": regeln["skala"]["lohnt_kaum_bis"] + 1, "gut": regeln["skala"]["surfbar_bis"] + 1}
    gefunden = {"surfbar": None, "gut": None}
    for h100 in range(30, 401, 5):
        h = h100 / 100.0
        r = bewerte({"hoehe_m": h, "periode_s": periode_s, "swell_richtung": 270, "wind_kn": 3, "boeen_kn": 3,
                     "wind_richtung": 90}, spot, person, regeln)
        for name, ziel in ziele.items():
            if gefunden[name] is None and r["punkte"] >= ziel:
                gefunden[name] = h
    return gefunden


def optimal_ab(person: dict):
    """Wellenhöhe (Meter), ab der die Höhenlinie der Person die vollen 10 Grundpunkte erreicht."""
    for x, y in sorted(person["hoehe"]):
        if y >= 10:
            return x
    return None


# ---- Welche Welle kommt am Spot an? ------------------------------------------

def mitte_des_fensters(von: float, bis: float) -> float:
    """Mitte eines Richtungsbereichs von..bis (im Uhrzeigersinn, darf über Nord gehen)."""
    return (von + ((bis - von) % 360) / 2.0) % 360


def winkel_abstand(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def richtungsfaktor(grad, spot: dict, regeln: dict) -> float:
    """Anteil (0 bis 1) der Wellenhöhe, der bei dieser Richtung am Spot ankommt."""
    if grad is None:
        return 1.0
    mitte = mitte_des_fensters(*spot["swell_dir_deg"])
    return kennlinie(regeln["swell_richtung"]["hoehe_nach_winkel_prozent"], winkel_abstand(grad, mitte)) / 100.0


def teile_welle(w: dict, spot: dict, regeln: dict):
    """Wirksame Höhe aus Swell und Windsee getrennt, jeweils nach Richtung zur Küste.

    w: Wellen-Eintrag eines Modells (hoehe, swell_h/t/dir, wind_h/t/dir). Gibt None zurück,
    wenn das Modell keine Aufteilung in Swell und Windsee liefert (zum Beispiel ECMWF bei Open-Meteo).
    """
    if any(w.get(k) is None for k in ("swell_h", "wind_h", "swell_dir", "wind_dir")):
        return None
    es = w["swell_h"] * richtungsfaktor(w["swell_dir"], spot, regeln)
    ew = w["wind_h"] * richtungsfaktor(w["wind_dir"], spot, regeln)
    eff = math.hypot(es, ew)
    swell_vorn = es >= ew
    periode = w.get("swell_t") if swell_vorn else w.get("wind_t")
    return {
        "hoehe": eff, "gesamt": w["hoehe"], "swell_wirksam": es, "windsee_wirksam": ew,
        "periode": periode if periode else w.get("periode"),
        "richtung": w["swell_dir"] if swell_vorn else w["wind_dir"],
        "art": "Swell" if swell_vorn else "Windsee",
    }
