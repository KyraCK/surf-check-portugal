"""Tests für Auswertung, Seite, Basen, Ausflüge und Ausfälle mit erfundenen Rohdaten (kein Netzwerk)."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import auswerten  # noqa: E402
import build  # noqa: E402
import config  # noqa: E402
import fetch  # noqa: E402
import fixtures  # noqa: E402
from netz import AbrufFehler  # noqa: E402

UTC = timezone.utc
# 8:00 Uhr portugiesische Zeit (Sommerzeit), Mittwoch 7.10.2026
MORGENS = datetime(2026, 10, 7, 7, 0, tzinfo=UTC)


def standard(e):
    """Ansicht der Basis, die gerade gilt."""
    return e["ansichten"][e["standard"]]


class Basis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config.lade()

    def erg(self, roh=None, jetzt=MORGENS, **kw):
        roh = roh or fixtures.rohdaten(self.cfg, jetzt, **kw)
        return auswerten.auswerten(self.cfg, roh, jetzt)


class GuteBedingungen(Basis):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.e = auswerten.auswerten(cls.cfg, fixtures.rohdaten(cls.cfg, MORGENS), MORGENS)

    def test_ja_und_hohe_scores(self):
        f = standard(self.e)["fazit"]
        self.assertTrue(f["ja"])
        self.assertGreaterEqual(f["hoechst"], 8)
        self.assertEqual(f["block"]["sicherheit"], "hoch")  # alle Modelle sagen dasselbe

    def test_zeitfenster_liegen_im_hellen(self):
        for b in standard(self.e)["tag"]["spots"]["moledo"]["bloecke"]:
            self.assertGreaterEqual(b["start"].hour, 8)       # Sonnenaufgang 7:38 Ortszeit
            self.assertLessEqual(b["ende"].hour, 19)          # Sonnenuntergang 19:06 Ortszeit

    def test_tide_wird_mit_dem_pegel_korrigiert(self):
        info = self.e["basen"]["caminha"]["tide"]
        self.assertEqual(info["quelle"], "modell_korrigiert")
        self.assertAlmostEqual(info["versatz_min"], -30, delta=3)

    def test_fuenf_tage_jeder_mit_der_passenden_basis(self):
        self.assertEqual([t["basis"] for t in self.e["tage"]], ["caminha"] * 4 + ["vagueira"])

    def test_drei_ansichten_standard_ist_die_aktuelle_basis(self):
        self.assertEqual(set(self.e["ansichten"]), {"caminha", "vagueira", "bordeira"})
        self.assertEqual(self.e["standard"], "caminha")
        self.assertTrue(self.e["ansichten"]["caminha"]["gueltig"])
        self.assertFalse(self.e["ansichten"]["bordeira"]["gueltig"])

    def test_zukunft_ist_nur_ein_vergleich(self):
        v = self.e["ansichten"]["bordeira"]
        self.assertFalse(v["gueltig"])
        seite = build.baue_seite(self.cfg, self.e)
        self.assertIn("Zum Vergleich", seite)

    def test_aussicht_nennt_nur_tage_der_basis(self):
        # Caminha gilt bis 10.10.: der 11.10. (Vagueira) darf dort nie als Aussicht auftauchen
        a = self.e["ansichten"]["caminha"]["fazit"].get("aussicht")
        if a:
            self.assertLessEqual(a["datum"], datetime(2026, 10, 10).date())


class BasisWechsel(Basis):
    def test_am_11_oktober_gilt_vagueira(self):
        e = self.erg(jetzt=datetime(2026, 10, 11, 7, 0, tzinfo=UTC))
        self.assertEqual(e["standard"], "vagueira")
        self.assertEqual(e["tage"][0]["basis"], "vagueira")

    def test_nach_dem_letzten_tag_gilt_die_letzte_basis(self):
        e = self.erg(jetzt=datetime(2026, 11, 2, 7, 0, tzinfo=UTC))
        self.assertEqual(e["standard"], "bordeira")

    def test_vor_der_reise_gilt_die_naechste_basis(self):
        e = self.erg(jetzt=datetime(2026, 9, 20, 7, 0, tzinfo=UTC))
        self.assertEqual(e["standard"], "caminha")


class Zeitumschaltung(Basis):
    def test_nach_18_uhr_zeigt_der_naechste_morgen(self):
        e = self.erg(jetzt=datetime(2026, 10, 7, 17, 30, tzinfo=UTC))   # 18:30 Ortszeit
        self.assertEqual(e["modus"], "morgen")
        self.assertEqual(e["label"], "Donnerstag früh")

    def test_morgens_zeigt_heute(self):
        e = self.erg()
        self.assertEqual(e["modus"], "heute")
        self.assertIn("Heute", e["label"])

    def test_vergangene_fenster_sind_markiert(self):
        e = self.erg(jetzt=datetime(2026, 10, 7, 12, 0, tzinfo=UTC))    # 13:00 Ortszeit
        bloecke = standard(e)["tag"]["spots"]["moledo"]["bloecke"]
        self.assertTrue(bloecke[0]["vorbei"])
        self.assertFalse(bloecke[-1]["vorbei"])


class SwellUndWindsee(Basis):
    """Heute-Fall: Die Modelle melden viel Welle, aber fast alles ist Windsee bei Nordwind."""

    def hoechst(self, e):
        b = standard(e)["tag"]["spots"]["moledo"]["bester"]
        return max(v["punkte"] for v in b["personen"].values()), b

    def test_windsee_bei_nordwind_ergibt_keinen_surftag(self):
        e = self.erg(swell_h=0.4, wind_h=1.5, wind=14.0, wind_richtung=10.0, periode=9.0)
        punkte, b = self.hoechst(e)
        self.assertLessEqual(punkte, 3)
        self.assertGreater(b["welle_gesamt_m"][0], 1.4)           # das Modell meldet viel
        self.assertLess(b["welle_m"][1], 0.9)                      # am Spot kommt wenig an

    def test_gleiche_gesamthoehe_als_reiner_swell_ist_ein_guter_tag(self):
        e = self.erg(swell_h=1.55, wind_h=0.0, wind=5.0, wind_richtung=90.0, periode=11.0, swell_dir=270.0)
        punkte, b = self.hoechst(e)
        self.assertGreaterEqual(punkte, 7)

    def test_ecmwf_bekommt_den_anteil_der_anderen_modelle(self):
        e = self.erg(swell_h=0.4, wind_h=1.5, wind=14.0, wind_richtung=10.0)
        b = standard(e)["tag"]["spots"]["moledo"]["bester"]
        self.assertEqual(b["periode_art"]["ECMWF"], "übernommen")
        # ECMWF-Gesamthöhe (1,55 m) wird wie bei den anderen Modellen verkleinert, nicht ungefiltert übernommen
        self.assertLess(b["je_modell"]["ECMWF"]["welle"], 0.9)

    def test_seite_erklaert_den_unterschied(self):
        e = self.erg(swell_h=0.4, wind_h=1.5, wind=14.0, wind_richtung=10.0)
        seite = build.baue_seite(self.cfg, e)
        self.assertIn("Die Modelle melden insgesamt", seite)
        self.assertIn("Windsee", seite)


class AusweichSpots(Basis):
    def test_gleich_gut_gewinnt_der_normale_spot(self):
        e = self.erg(hoehe=1.5)
        f = standard(e)["fazit"]
        self.assertFalse(f["ausweich"])

    def test_deutlich_besser_gewinnt_der_ausweichspot(self):
        # normale Spots klein, Matosinhos (Ausweich) mit Überkopf-Welle
        haupt = {s: 0.7 for s in ("moledo", "afife", "vila_praia_de_ancora", "cabedelo", "ofir")}
        e = self.erg(hoehe_je_spot=dict(haupt, matosinhos=2.0))
        f = standard(e)["fazit"]
        self.assertEqual(f["spot"], "matosinhos")
        self.assertTrue(f["ausweich"])
        self.assertIn("Ausweichspot", build.baue_seite(self.cfg, e))

    def test_knapp_besser_reicht_nicht(self):
        # Matosinhos nur einen Punkt besser: Fazit bleibt bei den normalen Spots
        haupt = {s: 1.1 for s in ("moledo", "afife", "vila_praia_de_ancora", "cabedelo", "ofir")}
        e = self.erg(hoehe_je_spot=dict(haupt, matosinhos=1.25), periode=10)
        f = standard(e)["fazit"]
        self.assertFalse(f["ausweich"])


class Ausfluege(Basis):
    def namen(self, e, bid="caminha"):
        return [x["ziel"]["name"] for x in e["ansichten"][bid]["ausfluege"]["vorschlaege"]]

    def test_regentag_nur_regenziele(self):
        e = self.erg(regen_wk=80, hoehe=0.5)
        a = e["ansichten"]["caminha"]["ausfluege"]
        self.assertEqual(a["modus"], "regen")
        self.assertEqual(self.namen(e), ["Valença, Festung"])

    def test_starker_nordwind_nur_geschuetzte_ziele(self):
        e = self.erg(wind=20.0, wind_richtung=0.0, hoehe=0.5)
        a = e["ansichten"]["caminha"]["ausfluege"]
        self.assertEqual(a["modus"], "nordwind")
        for x in a["vorschlaege"]:
            self.assertIn("nordwind", x["ziel"]["bedingung"])

    def test_warm_und_ruhig_baden_und_wandern_zuerst(self):
        e = self.erg(hoehe=0.5, wind=3.0, temperatur=22.0)
        a = e["ansichten"]["caminha"]["ausfluege"]
        self.assertEqual(a["modus"], "warm_ruhig")
        for x in a["vorschlaege"]:
            self.assertIn("warm_ruhig", x["ziel"]["bedingung"])

    def test_surftag_nur_kurze_ziele_am_nachmittag(self):
        e = self.erg(hoehe=1.8, periode=12.0, wind=3.0, temperatur=22.0)
        a = e["ansichten"]["caminha"]["ausfluege"]
        self.assertTrue(a["surftag"])
        self.assertTrue(a["vorschlaege"])
        for x in a["vorschlaege"]:
            self.assertEqual(x["ziel"]["dauer"], "kurz")
            self.assertTrue(x["nachmittag"])

    def test_hoechstens_zwei_vorschlaege(self):
        e = self.erg(hoehe=0.5, wind=3.0, temperatur=22.0)
        self.assertLessEqual(len(self.namen(e)), 2)

    def test_jede_basis_hat_eigene_ziele(self):
        e = self.erg(hoehe=0.5, wind=3.0, temperatur=22.0)
        for bid in ("caminha", "vagueira", "bordeira"):
            for x in e["ansichten"][bid]["ausfluege"]["vorschlaege"]:
                self.assertEqual(x["ziel"]["basis"], bid)

    def test_ohne_wetterdaten_keine_tipps(self):
        roh = fixtures.rohdaten(self.cfg, MORGENS)
        for k in list(roh["quellen"]):
            if k.startswith("wetter:"):
                fixtures.ausfall(roh, k)
        e = self.erg(roh)
        a = e["ansichten"]["caminha"]["ausfluege"]
        self.assertEqual(a["vorschlaege"], [])
        self.assertIn("Wetterdaten", a["hinweis"])


class Ausfaelle(Basis):
    def test_ein_modell_faellt_aus(self):
        roh = fixtures.rohdaten(self.cfg, MORGENS)
        fixtures.ausfall(roh, "welle:moledo:ICON")
        e = self.erg(roh)
        b = standard(e)["tag"]["spots"]["moledo"]["bester"]
        self.assertEqual(b["modelle"], ["GFS", "ECMWF"])
        self.assertTrue(any("ICON" in a for a in e["alarme"]))

    def test_nur_ein_modell_ist_nie_sicher(self):
        roh = fixtures.rohdaten(self.cfg, MORGENS)
        fixtures.ausfall(roh, "welle:moledo:ICON")
        fixtures.ausfall(roh, "welle:moledo:ECMWF")
        e = self.erg(roh)
        self.assertEqual(standard(e)["tag"]["spots"]["moledo"]["bester"]["sicherheit"], "niedrig")

    def test_ausfaelle_vieler_spots_werden_zusammengefasst(self):
        roh = fixtures.rohdaten(self.cfg, MORGENS)
        for k in list(roh["quellen"]):
            if k.startswith("welle:") and k.endswith(":GFS"):
                fixtures.ausfall(roh, k, "HTTP 500")
        e = self.erg(roh)
        gfs = [a for a in e["alarme"] if "GFS" in a]
        self.assertEqual(len(gfs), 1)
        self.assertIn("29 Spots", gfs[0])

    def test_alle_wellendaten_fehlen_keine_scores_keine_erfundenen_zahlen(self):
        roh = fixtures.rohdaten(self.cfg, MORGENS)
        for k in list(roh["quellen"]):
            if k.startswith("welle:"):
                fixtures.ausfall(roh, k)
        e = self.erg(roh)
        self.assertIsNone(standard(e)["fazit"].get("spot"))
        seite = build.baue_seite(self.cfg, e)
        self.assertIn("Keine<br>Aussage", seite)
        self.assertIn("Wellenmodell", seite)

    def test_zu_alte_daten_zaehlen_nicht_als_aktuell(self):
        roh = fixtures.rohdaten(self.cfg, MORGENS)
        alt = (MORGENS - timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for k in list(roh["quellen"]):
            if k.startswith("welle:moledo"):
                roh["quellen"][k]["abgerufen_um"] = alt
                roh["quellen"][k]["status"] = "veraltet"
        e = self.erg(roh)
        self.assertTrue(any("Moledo" in a for a in e["alarme"]))
        self.assertIsNone(standard(e)["tag"]["spots"]["moledo"]["bester"])

    def test_pegel_faellt_aus_tide_bleibt_aber_wird_als_unkorrigiert_gezeigt(self):
        roh = fixtures.rohdaten(self.cfg, MORGENS)
        fixtures.ausfall(roh, "pegel:caminha")
        e = self.erg(roh)
        self.assertEqual(e["basen"]["caminha"]["tide"]["quelle"], "modell")
        self.assertIn("30 Minuten", e["basen"]["caminha"]["tide"]["hinweis"])

    def test_tide_modell_faellt_aus_kein_abzug_fuer_tide(self):
        roh = fixtures.rohdaten(self.cfg, MORGENS)
        fixtures.ausfall(roh, "tide_modell:caminha")
        e = self.erg(roh)
        self.assertIsNone(standard(e)["tag"]["spots"]["moledo"]["bloecke"][0]["tide"])
        self.assertTrue(any("Gezeiten" in a for a in e["alarme"]))


class LandPunkte(Basis):
    """GFS-Wave meldet für Gitterpunkte an Land 0,0 m und 0 s. Das ist keine Welle, sondern keine Daten."""

    def roh_mit_landpunkt(self, spot="moledo"):
        roh = fixtures.rohdaten(self.cfg, MORGENS)
        h = roh["quellen"][f"welle:{spot}:GFS"]["daten"]["hourly"]
        n = len(h["time"])
        h["wave_height"], h["wave_period"], h["wave_peak_period"] = [0.0] * n, [0.0] * n, [None] * n
        return roh

    def test_nullen_zaehlen_nicht_als_flaute(self):
        e = self.erg(self.roh_mit_landpunkt())
        info = e["spots"][("caminha", "moledo")]["daten"]["infos"]["wellen"]["GFS"]
        self.assertEqual(info["status"], "nicht_verfuegbar")
        b = standard(e)["tag"]["spots"]["moledo"]["bester"]
        self.assertEqual(b["modelle"], ["ECMWF", "ICON"])
        self.assertGreaterEqual(max(v["punkte"] for v in b["personen"].values()), 8)  # nicht durch Nullen gedrückt

    def test_kein_globaler_alarm_aber_hinweis_in_der_ansicht_und_der_datenlage(self):
        e = self.erg(self.roh_mit_landpunkt())
        self.assertEqual(e["alarme"], [])
        seite = build.baue_seite(self.cfg, e)
        self.assertIn("der Modellpunkt liegt an Land", seite)
        self.assertIn("an einigen Orten ohne Werte", seite)


class Seite(Basis):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.e = auswerten.auswerten(cls.cfg, fixtures.rohdaten(cls.cfg, MORGENS), MORGENS)
        cls.seite = build.baue_seite(cls.cfg, cls.e)

    def test_keine_namen_im_seitenquelltext(self):
        for p in self.cfg["scoring"]["personen"].values():
            self.assertNotIn(p["label"].lower(), self.seite.lower())

    def test_seite_braucht_keine_fremden_server(self):
        # Nichts wird von fremden Servern nachgeladen (Links zum Anklicken sind etwas anderes)
        for fremd in ("fonts.googleapis", "fonts.gstatic", "<script src", "@import", "url(http", "<img src=\"http",
                      "rel=\"stylesheet\""):
            self.assertNotIn(fremd, self.seite)

    def test_jede_gezeigte_zahl_hat_eine_quelle(self):
        self.assertIn("Open-Meteo", self.seite)
        self.assertIn("Läufe", self.seite)
        self.assertIn("Datenlage", self.seite)

    def test_basis_umschalter_und_alle_ansichten_stehen_in_der_seite(self):
        for bid in ("caminha", "vagueira", "bordeira"):
            self.assertIn(f'data-basis="{bid}"', self.seite)
        # nur die aktuelle Basis ist sichtbar
        self.assertEqual(self.seite.count('class="ansicht" data-basis="caminha"'), 2)
        self.assertEqual(self.seite.count('class="ansicht" data-basis="vagueira" hidden'), 2)

    def test_legende_und_ausfluege_sind_da(self):
        self.assertIn("Wer ist wer, und wie wird bewertet?", self.seite)
        self.assertIn("Abseits vom Wasser", self.seite)

    def test_seitengroesse_bleibt_im_rahmen(self):
        import gzip
        self.assertLess(len(gzip.compress(self.seite.encode("utf-8"))), 120_000)


class AbrufRueckfall(unittest.TestCase):
    def test_fehlschlag_mit_alten_daten_wird_veraltet(self):
        def kaputt():
            raise AbrufFehler("HTTP 503")
        alt = {"quellen": {"a": {"status": "ok", "abgerufen_um": "2026-10-07T05:00:00Z", "url": "u", "daten": {"x": 1}}}}
        orig = fetch.alle_aufgaben
        fetch.alle_aufgaben = lambda cfg, jetzt: [(["a", "b"], kaputt)]
        try:
            neu = fetch.hole_alles({}, MORGENS, alt, ausgabe=lambda *_: None)
        finally:
            fetch.alle_aufgaben = orig
        self.assertEqual(neu["quellen"]["a"]["status"], "veraltet")
        self.assertEqual(neu["quellen"]["a"]["daten"], {"x": 1})
        self.assertEqual(neu["quellen"]["a"]["abgerufen_um"], "2026-10-07T05:00:00Z")  # bleibt der alte Zeitpunkt
        self.assertEqual(neu["quellen"]["b"]["status"], "fehler")
        self.assertIsNone(neu["quellen"]["b"]["daten"])

    def test_gemeinsame_anfragen_fuer_mehrere_orte(self):
        cfg = config.lade()
        aufgaben = fetch.alle_aufgaben(cfg, MORGENS)
        wetter = [k for ks, _ in aufgaben for k in ks if k.startswith("wetter:")]
        self.assertEqual(len(wetter), 29)                     # ein Eintrag je Spot
        anfragen = [ks for ks, _ in aufgaben if ks[0].startswith("wetter:")]
        self.assertLessEqual(len(anfragen), 4)                # aber nur wenige Netzabrufe
        self.assertTrue(all(len(ks) <= 11 for ks in anfragen))


if __name__ == "__main__":
    unittest.main()
