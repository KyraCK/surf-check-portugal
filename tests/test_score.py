"""Tests für Rechenlogik und Konfiguration.

Aufruf im Ordner surf-check-portugal:  python3 -m unittest discover -s tests -v

Der letzte Block ("Erwartungen") prüft Aussagen der Nutzerin über die Scores
gemacht hat, gegen die aktuell gespeicherten Zahlen. Wenn du die Regeln
absichtlich änderst, darf dort etwas rot werden. Dann ist es eine bewusste
Abweichung von den ursprünglichen Angaben.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import score  # noqa: E402


class Kennlinie(unittest.TestCase):
    P = [[0.6, 0], [1.4, 10]]

    def test_zwischen_den_punkten_gerade(self):
        self.assertAlmostEqual(score.kennlinie(self.P, 1.0), 5.0)

    def test_ausserhalb_bleibt_der_randwert(self):
        self.assertEqual(score.kennlinie(self.P, 0.1), 0)
        self.assertEqual(score.kennlinie(self.P, 3.0), 10)

    def test_reihenfolge_egal(self):
        self.assertAlmostEqual(score.kennlinie([[1.4, 10], [0.6, 0]], 1.0), 5.0)


class Richtung(unittest.TestCase):
    def test_im_sektor(self):
        self.assertEqual(score.abstand_zum_sektor(90, 36, 144), 0)

    def test_ausserhalb_naechste_kante(self):
        self.assertEqual(score.abstand_zum_sektor(180, 36, 144), 36)
        self.assertEqual(score.abstand_zum_sektor(0, 36, 144), 36)

    def test_sektor_ueber_nord(self):
        # Cabedelo: 319 bis 98 Grad läuft über Nord
        self.assertEqual(score.abstand_zum_sektor(0, 319, 98), 0)
        self.assertEqual(score.abstand_zum_sektor(350, 319, 98), 0)
        self.assertEqual(score.abstand_zum_sektor(120, 319, 98), 22)

    def test_windart(self):
        self.assertEqual(score.windart(90, [36, 144], 45), "ablandig")
        self.assertEqual(score.windart(180, [36, 144], 45), "seitlich")
        self.assertEqual(score.windart(270, [36, 144], 45), "auflandig")


class Rundung(unittest.TestCase):
    def test_kaufmaennisch(self):
        self.assertEqual(score.runde(2.5), 3)
        self.assertEqual(score.runde(4.49), 4)


class Tide(unittest.TestCase):
    def test_im_bereich_kein_abzug(self):
        self.assertEqual(score.tide_prozent(0.5, [0.3, 0.7], 15, 0.35), 100)

    def test_voller_abzug_weit_draussen(self):
        self.assertEqual(score.tide_prozent(1.0, [0.0, 0.35], 15, 0.35), 85)


class MitEchterKonfiguration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config.lade()
        cls.regeln = cls.cfg["scoring"]
        cls.moledo = cls.cfg["spots"]["moledo"]
        cls.p = cls.regeln["personen"]

    def punkte(self, person, hoehe, periode, wind, richtung, **extra):
        bed = {"hoehe_m": hoehe, "periode_s": periode, "swell_richtung": 290, "wind_kn": wind,
               "boeen_kn": wind, "wind_richtung": richtung, "tide_rel": 0.5, "tide_quelle": "modell"}
        bed.update(extra)
        return score.bewerte(bed, self.moledo, self.p[person], self.regeln)["punkte"]

    def test_fehlende_daten_ergeben_keinen_score(self):
        r = score.bewerte({"hoehe_m": 1.0, "periode_s": None, "wind_kn": 5, "wind_richtung": 90},
                          self.moledo, self.p["p1"], self.regeln)
        self.assertIsNone(r["punkte"])
        self.assertEqual(r["fehlt"], ["Periode"])

    def test_ohne_tide_und_swell_kein_abzug_aber_vermerkt(self):
        r = score.bewerte({"hoehe_m": 1.2, "periode_s": 9, "wind_kn": 6, "wind_richtung": 90},
                          self.moledo, self.p["p1"], self.regeln)
        self.assertEqual(sorted(r["luecken"]), ["Swell-Richtung", "Tide"])

    def test_score_immer_zwischen_1_und_10(self):
        for h in (0.0, 0.5, 1.0, 2.0, 5.0):
            for per in (4, 9, 14, 25):
                for w in (0, 10, 40):
                    for d in (0, 90, 180, 270):
                        for pid in self.p:
                            s = self.punkte(pid, h, per, w, d)
                            self.assertTrue(1 <= s <= 10, (pid, h, per, w, d, s))

    def test_falsche_tide_zieht_ab_manuell_staerker_als_modell(self):
        ok = self.punkte("p1", 1.5, 11, 8, 45, tide_rel=0.5)
        modell = self.punkte("p1", 1.5, 11, 8, 45, tide_rel=0.0, tide_quelle="modell")
        manuell = self.punkte("p1", 1.5, 11, 8, 45, tide_rel=0.0, tide_quelle="manuell")
        self.assertGreaterEqual(ok, modell)
        self.assertGreater(modell, manuell)

    def test_korrekturfaktor_wirkt_auf_die_hoehe(self):
        klein = dict(self.moledo, korrekturfaktor=0.7)
        bed = {"hoehe_m": 1.5, "periode_s": 11, "swell_richtung": 290, "wind_kn": 5, "wind_richtung": 90}
        normal = score.bewerte(bed, self.moledo, self.p["p1"], self.regeln)
        kleiner = score.bewerte(bed, klein, self.p["p1"], self.regeln)
        self.assertAlmostEqual(kleiner["hoehe_spot_m"], 1.05)
        self.assertLess(kleiner["punkte"], normal["punkte"])

    # --- Erwartungen aus den Angaben der Nutzerin (p1 = Brett 7'2", p2 = kleineres, p3 = längeres Brett) ---

    def test_p1_unter_1m_zu_klein_ab_1m_surfbar(self):
        self.assertLessEqual(self.punkte("p1", 0.8, 10, 5, 90), 3)
        self.assertTrue(4 <= self.punkte("p1", 1.0, 11, 5, 90) <= 6)

    def test_p2_p3_gute_werte_ab_1_2m_bei_9s_und_ablandigem_wind(self):
        for pid in ("p2", "p3"):
            self.assertGreaterEqual(self.punkte(pid, 1.2, 9, 6, 90), 7)

    def test_p2_p3_brauchen_mehr_groesse_als_p1(self):
        self.assertLessEqual(self.punkte("p2", 0.8, 10, 5, 90), self.punkte("p1", 0.8, 10, 5, 90))

    def test_p1_ist_windempfindlicher(self):
        self.assertLess(self.punkte("p1", 1.5, 11, 10, 0), self.punkte("p2", 1.5, 11, 10, 0))

    def test_auflandiger_wind_ruiniert_den_tag(self):
        self.assertLessEqual(self.punkte("p2", 1.2, 9, 12, 270), 3)

    def test_p2_p3_optimal_erst_bei_grossen_wellen(self):
        # Überkopf (etwa 1,8 m) mit langer Periode: Pflichttermin. Mittelgroß ist gut, aber noch nicht optimal.
        for pid in ("p2", "p3"):
            self.assertEqual(self.punkte(pid, 1.9, 12, 5, 90), 10)
            self.assertLess(self.punkte(pid, 1.3, 12, 5, 90), 10)
            self.assertGreaterEqual(score.optimal_ab(self.p[pid]), 1.7)

    def test_p3_mit_laengerem_brett_kommt_frueher_in_kleine_wellen(self):
        self.assertGreaterEqual(self.punkte("p3", 0.9, 10, 5, 90), self.punkte("p2", 0.9, 10, 5, 90))

    def test_kurze_periode_zieht_ab(self):
        self.assertLess(self.punkte("p2", 1.2, 7, 6, 90), self.punkte("p2", 1.2, 9, 6, 90))


class WirksameWelle(unittest.TestCase):
    """Welche Welle kommt am Spot an? Richtung zur Küste und Aufteilung in Swell und Windsee."""

    @classmethod
    def setUpClass(cls):
        cfg = config.lade()
        cls.regeln = cfg["scoring"]
        cls.moledo = cfg["spots"]["moledo"]      # Swell-Bereich 207 bis 332 Grad, Mitte West (270)

    def test_richtungsfaktor(self):
        f = lambda g: score.richtungsfaktor(g, self.moledo, self.regeln)
        self.assertAlmostEqual(f(270), 1.0, places=2)           # genau von vorn
        self.assertAlmostEqual(f(320), 0.8, places=1)           # schräg aus Nordwest
        self.assertLessEqual(f(0), 0.3)                         # aus Nord: läuft an der Küste entlang
        self.assertEqual(f(None), 1.0)                          # ohne Richtung kein Abzug

    def test_windsee_entlang_der_kueste_zaehlt_kaum(self):
        w = {"hoehe": 1.5, "swell_h": 0.3, "swell_dir": 280.0, "swell_t": 10.0,
             "wind_h": 1.47, "wind_dir": 0.0, "wind_t": 5.0, "periode": 9.0}
        r = score.teile_welle(w, self.moledo, self.regeln)
        self.assertLess(r["hoehe"], 0.6)                         # nicht 1,5 m
        self.assertEqual(r["gesamt"], 1.5)

    def test_windsee_von_vorn_zaehlt_voll_und_bestimmt_die_periode(self):
        w = {"hoehe": 1.5, "swell_h": 0.3, "swell_dir": 270.0, "swell_t": 10.0,
             "wind_h": 1.47, "wind_dir": 270.0, "wind_t": 5.0, "periode": 9.0}
        r = score.teile_welle(w, self.moledo, self.regeln)
        self.assertAlmostEqual(r["hoehe"], 1.5, places=1)
        self.assertEqual(r["art"], "Windsee")
        self.assertEqual(r["periode"], 5.0)                      # kurze Periode drückt den Score später

    def test_ohne_aufteilung_gibt_es_kein_ergebnis(self):
        self.assertIsNone(score.teile_welle({"hoehe": 1.5, "swell_h": None, "wind_h": None,
                                             "swell_dir": None, "wind_dir": None}, self.moledo, self.regeln))


class Sicherheit(unittest.TestCase):
    R = {"sicherheit": {"hoch_bis_spanne": 1, "mittel_bis_spanne": 3}}

    def test_stufen(self):
        self.assertEqual(score.sicherheit([7, 7, 8], self.R), "hoch")
        self.assertEqual(score.sicherheit([5, 7, 8], self.R), "mittel")
        self.assertEqual(score.sicherheit([2, 7, 8], self.R), "niedrig")

    def test_ein_modell_allein_ist_nie_sicher(self):
        self.assertEqual(score.sicherheit([8], self.R), "niedrig")
        self.assertEqual(score.sicherheit([8, None], self.R), "niedrig")


class Konfiguration(unittest.TestCase):
    def test_aktuelle_dateien_sind_gueltig(self):
        cfg = config.lade()
        self.assertIn("moledo", cfg["spots"])

    def test_basis_nach_datum(self):
        from datetime import date
        cfg = config.lade()
        self.assertEqual(config.basis_fuer(cfg["basen"], date(2026, 10, 8))["id"], "caminha")
        self.assertIsNone(config.basis_fuer(cfg["basen"], date(2027, 1, 1)))


if __name__ == "__main__":
    unittest.main()
