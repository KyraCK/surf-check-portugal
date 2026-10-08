"""Tests für das Lernen aus Beobachtungen (kein Netzwerk, erfundene Daten)."""
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import auswerten  # noqa: E402
import build  # noqa: E402
import config  # noqa: E402
import fetch  # noqa: E402
import fixtures  # noqa: E402
import lernen  # noqa: E402

UTC = timezone.utc
JETZT = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)   # 13:00 Ortszeit am 8.10.


def beob(tag, uhr, spot, hoehe, **extra):
    return dict({"datum": date(2026, 10, tag), "uhr": uhr, "spot": spot, "hoehe_m": hoehe, "quelle": "test"}, **extra)


class Rechnung(unittest.TestCase):
    G = [0.4, 1.6]

    def test_eine_beobachtung_zaehlt_vorsichtig(self):
        # Verhältnis 0,5, n = 1, vorsicht 2: 1 + (0,5 - 1) x 1/3
        self.assertAlmostEqual(lernen._gelernt([0.5], 2, self.G), 1 - 0.5 / 3, places=4)

    def test_mehr_beobachtungen_zaehlen_staerker(self):
        a = lernen._gelernt([0.5], 2, self.G)
        b = lernen._gelernt([0.5, 0.5, 0.5], 2, self.G)
        c = lernen._gelernt([0.5] * 20, 2, self.G)
        self.assertLess(b, a)
        self.assertLess(c, b)
        self.assertAlmostEqual(b, 0.7, places=4)

    def test_median_schuetzt_vor_ausreissern(self):
        self.assertAlmostEqual(lernen._gelernt([0.8, 0.8, 3.0], 2, self.G), 1 + (0.8 - 1) * 3 / 5, places=4)

    def test_grenzen(self):
        self.assertEqual(lernen._gelernt([0.05] * 100, 2, self.G), 0.4)
        self.assertEqual(lernen._gelernt([9.0] * 100, 2, self.G), 1.6)


class MitDaten(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config.lade()
        cls.roh = fixtures.mit_beobachtungsdaten(fixtures.rohdaten(cls.cfg, JETZT, hoehe=1.5, periode=11.0))

    def cfg_mit(self, beobachtungen, **spot_aenderung):
        spots = {k: dict(v) for k, v in self.cfg["spots"].items()}
        for sid, aenderung in spot_aenderung.items():
            spots[sid].update(aenderung)
        return dict(self.cfg, beobachtungen=beobachtungen, spots=spots)

    def test_zu_hohe_vorhersage_wird_nach_unten_gelernt(self):
        cfg = self.cfg_mit([beob(7, 12, "moledo", 0.5)])
        erg = lernen.berechne(cfg, self.roh, JETZT)
        z = erg["zeilen"][0]
        self.assertEqual(z["status"], "ok")
        self.assertLess(z["verhaeltnis"], 0.4)                    # gesehen 0,5 m, Tool erwartete etwa 1,5 m
        f = erg["faktoren"]["moledo"]
        self.assertEqual(f["quelle"], "eigene Beobachtungen")
        self.assertLess(f["lern"], 0.8)
        self.assertGreater(f["lern"], 0.7)

    def test_nachbarspots_bekommen_die_halbe_korrektur(self):
        cfg = self.cfg_mit([beob(7, 12, "moledo", 0.5)])
        f = lernen.berechne(cfg, self.roh, JETZT)["faktoren"]
        eigen = f["moledo"]["lern"]
        self.assertEqual(f["afife"]["quelle"], "andere Spots der Basis")
        self.assertAlmostEqual(f["afife"]["lern"], 1 + (eigen - 1) * 0.5, places=4)
        self.assertEqual(f["mira"]["quelle"], "keine")             # andere Basis: unverändert
        self.assertEqual(f["mira"]["lern"], 1.0)

    def test_manueller_faktor_bleibt_erhalten_und_wird_eingerechnet(self):
        cfg = self.cfg_mit([beob(7, 12, "moledo", 0.5)], moledo={"korrekturfaktor": 0.5})
        z = lernen.berechne(cfg, self.roh, JETZT)
        # Das Tool rechnet schon mit 0,5: Es war nur noch 0,75 m erwartet, gesehen 0,5 m
        self.assertGreater(z["zeilen"][0]["verhaeltnis"], 0.6)
        self.assertAlmostEqual(z["faktoren"]["moledo"]["gesamt"], 0.5 * z["faktoren"]["moledo"]["lern"], places=4)

    def test_zukunft_und_zu_alte_beobachtungen_zaehlen_nicht(self):
        cfg = self.cfg_mit([beob(9, 12, "moledo", 0.5), dict(beob(7, 12, "moledo", 0.5), datum=date(2026, 6, 1))])
        erg = lernen.berechne(cfg, self.roh, JETZT)
        self.assertEqual(erg["zeilen"], [])
        self.assertEqual(erg["faktoren"]["moledo"]["quelle"], "keine")

    def test_zu_kleine_modellhoehe_wird_nicht_verglichen(self):
        roh = fixtures.mit_beobachtungsdaten(fixtures.rohdaten(self.cfg, JETZT, hoehe=0.1))
        erg = lernen.berechne(self.cfg_mit([beob(7, 12, "moledo", 0.5)]), roh, JETZT)
        self.assertIn("zu klein", erg["zeilen"][0]["status"])
        self.assertEqual(erg["faktoren"]["moledo"]["lern"], 1.0)

    def test_ohne_modelldaten_aendert_sich_nichts(self):
        roh = fixtures.rohdaten(self.cfg, JETZT)               # ohne 'beob:'-Daten
        erg = lernen.berechne(self.cfg_mit([beob(7, 12, "moledo", 0.5)]), roh, JETZT)
        self.assertIn("keine Modelldaten", erg["zeilen"][0]["status"])
        self.assertEqual(erg["faktoren"]["moledo"]["lern"], 1.0)

    def test_test_ohne_mogeln_ab_drei_beobachtungen(self):
        cfg = self.cfg_mit([beob(6, 12, "moledo", 0.5), beob(7, 10, "moledo", 0.55), beob(7, 14, "moledo", 0.45)])
        erg = lernen.berechne(cfg, self.roh, JETZT)
        p = erg["pruefung"]
        self.assertEqual(p["n"], 3)
        self.assertLess(p["fehler_nachher_m"], p["fehler_vorher_m"])    # Lernen hilft bei gleichmäßiger Abweichung
        self.assertIsNone(lernen.berechne(self.cfg_mit([beob(7, 12, "moledo", 0.5)]), self.roh, JETZT)["pruefung"])


class InDerAuswertung(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config.lade()
        cls.roh = fixtures.mit_beobachtungsdaten(fixtures.rohdaten(cls.cfg, JETZT, hoehe=1.5, periode=11.0))

    def test_gelernter_faktor_senkt_die_welle_am_spot_und_den_score(self):
        ohne = auswerten.auswerten(dict(self.cfg, beobachtungen=[]), self.roh, JETZT)
        mit = auswerten.auswerten(dict(self.cfg, beobachtungen=[beob(7, 12, "moledo", 0.5)]), self.roh, JETZT)

        def block(e):
            return e["ansichten"]["caminha"]["tag"]["spots"]["moledo"]["bloecke"][-1]
        self.assertLess(block(mit)["welle_m"][1], block(ohne)["welle_m"][1])
        self.assertLessEqual(max(v["punkte"] for v in block(mit)["personen"].values()),
                             max(v["punkte"] for v in block(ohne)["personen"].values()))

    def test_ohne_beobachtungen_aendert_sich_nichts(self):
        e = auswerten.auswerten(dict(self.cfg, beobachtungen=[]), self.roh, JETZT)
        for f in e["lernen"]["faktoren"].values():
            self.assertEqual(f["lern"], 1.0)

    def test_seite_zeigt_was_gelernt_wurde_und_wie_man_etwas_eintraegt(self):
        cfg = dict(self.cfg, beobachtungen=[beob(7, 12, "moledo", 0.5)])
        e = auswerten.auswerten(cfg, self.roh, JETZT)
        seite = build.baue_seite(cfg, e)
        self.assertIn("Lernen aus Beobachtungen", seite)
        self.assertIn("gelernt aus 1 Beobachtung", seite)
        self.assertIn("edit/main/config/beobachtungen.toml", seite)
        self.assertNotIn("Webcam, Schätzung", seite)                      # Freitext der Beobachtungen gehört nicht auf die Seite

    def test_abruf_der_vergangenheit_nur_fuer_beobachtete_spots(self):
        ohne = fetch.alle_aufgaben(dict(self.cfg, beobachtungen=[]), JETZT)
        mit = fetch.alle_aufgaben(dict(self.cfg, beobachtungen=[beob(7, 12, "moledo", 0.5)]), JETZT)
        schluessel = lambda a: [k for ks, _ in a for k in ks if k.startswith("beob:")]
        self.assertEqual(schluessel(ohne), [])
        self.assertEqual(sorted(schluessel(mit)), ["beob:moledo:ECMWF", "beob:moledo:GFS", "beob:moledo:ICON"])

    def test_eintragen_prueft_die_eingabe(self):
        schlecht = {"beobachtung": [{"datum": date(2026, 10, 8), "uhr": 12, "spot": "gibt_es_nicht", "hoehe_m": 0.5}]}
        with self.assertRaises(config.ConfigFehler):
            config.pruefe_beobachtungen(schlecht, self.cfg["spots"])
        with self.assertRaises(config.ConfigFehler):
            config.pruefe_beobachtungen({"beobachtung": [{"datum": date(2026, 10, 8), "uhr": 25, "spot": "moledo", "hoehe_m": 0.5}]}, self.cfg["spots"])
        with self.assertRaises(config.ConfigFehler):
            config.pruefe_beobachtungen({"beobachtung": [{"datum": date(2026, 10, 8), "uhr": 12, "spot": "moledo", "hoehe_m": "klein"}]}, self.cfg["spots"])


if __name__ == "__main__":
    unittest.main()
