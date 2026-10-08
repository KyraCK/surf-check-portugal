#!/usr/bin/env python3
"""Erzeugt die fertige Seite docs/index.html aus Konfiguration und Rohdaten.

Die Seite ist eine einzige statische HTML-Datei (Stil und Symbole stecken darin),
dazu der Ordner docs/schriften/ mit den Schriftdateien. Kein Server, keine Datenbank.
Namen der Personen erscheinen nirgends: Avatare und Kürzel p1 bis p3.
"""
from __future__ import annotations

import html
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import auswerten as aw
import config
import quellen
import score
import symbole

ROOT = Path(__file__).resolve().parent
AUSGABE = ROOT / "docs"
UTC = timezone.utc
STUFEN_WORT = {"hoch": 3, "mittel": 2, "niedrig": 1}


# ---- Formatierung ------------------------------------------------------------

def esc(x) -> str:
    return html.escape(str(x), quote=True)


def zahl(x, n=1) -> str:
    return f"{x:.{n}f}".replace(".", ",")


def bereich(r, n=1, einheit="") -> str:
    """'0,9 bis 1,2 m' oder '0,9 m', wenn beide Enden gleich aussehen."""
    if not r:
        return "–"
    a, b = zahl(r[0], n), zahl(r[1], n)
    e = f" {einheit}" if einheit else ""
    return f"{a}{e}" if a == b else f"{a} bis {b}{e}"


def tagname(d) -> str:
    return aw.WOCHENTAGE[d.weekday()]


def datum_kurz(d) -> str:
    return f"{d.day}.{d.month}."


def uhr_von_bis(b, zweistellig=False) -> str:
    f = (lambda h: f"{h:02d}") if zweistellig else str
    return f"{f(b['start'].hour)} bis {f(b['ende'].hour)}"


def stand(iso_text) -> str:
    if not iso_text:
        return "–"
    t = aw.lokal(quellen.zeit(iso_text))
    return f"{t.day}.{t.month}. {t:%H:%M}"


def lauf_text(dt) -> str:
    return "–" if dt is None else f"{dt.day}.{dt.month}. {dt:%H} UTC"


# ---- kleine HTML-Bausteine -------------------------------------------------------

def icon(name, size=20, cls="", drehung=None) -> str:
    stil = f' style="transform:rotate({drehung:.0f}deg)"' if drehung is not None else ""
    return (f'<svg class="ic {cls}" width="{size}" height="{size}"{stil} aria-hidden="true">'
            f'<use href="#i-{name}"/></svg>')


def avatar(pid, personen, size=28) -> str:
    nr = pid[1:]
    return (f'<svg class="av {pid}" width="{size}" height="{size}" viewBox="0 0 64 64" role="img" '
            f'aria-label="Person {nr}"><use href="#av-{pid}"/></svg>')


def band(n) -> str:
    return "r" if n <= 3 else ("o" if n <= 6 else "g")


def segmente(n, senkrecht=False) -> str:
    reihe = range(10, 0, -1) if senkrecht else range(1, 11)
    return "".join(f'<i class="s{" on " + band(n) if (n is not None and i <= n) else ""}"></i>' for i in reihe)


def skala(pid, n, personen) -> str:
    wert = "–" if n is None else str(n)
    label = "kein Score, Daten fehlen" if n is None else f"Score {n} von 10"
    return (f'<div class="sc {pid}{" leer" if n is None else ""}">{avatar(pid, personen, 44)}'
            f'<div class="bar" role="img" aria-label="{label}">{segmente(n)}</div>'
            f'<b class="n{" leer" if n is None else ""}">{wert}</b></div>')


def mini(pid, n, personen) -> str:
    wert = "–" if n is None else str(n)
    label = "kein Score" if n is None else f"Score {n} von 10"
    return (f'<div class="mini {pid}">{avatar(pid, personen, 36)}'
            f'<div class="vbar" role="img" aria-label="{label}">{segmente(n, True)}</div><b>{wert}</b></div>')


def trio(b, personen, stapel=True) -> str:
    inner = "".join(skala(pid, b["personen"][pid]["punkte"] if b else None, personen) for pid in personen)
    return f'<div class="trio{" stack" if stapel else ""}">{inner}</div>'


def spannbalken(werte: dict, maximum: float, einheit="m") -> str:
    """Zeigt je Modell einen Punkt auf einer Linie, dazu die Spanne dazwischen."""
    if not werte:
        return ""
    pos = {n: max(0.0, min(100.0, v / maximum * 100.0)) for n, v in werte.items()}
    lo, hi = min(pos.values()), max(pos.values())
    punkte = "".join(f'<i class="pt" style="left:{p:.1f}%" title="{esc(n)}: {zahl(werte[n], 2)} {einheit}"></i>'
                     for n, p in pos.items())
    beschriftung = "".join(f"<span>{esc(n)} {zahl(v, 1)}</span>" for n, v in werte.items())
    return (f'<div class="rg" aria-hidden="true"><span class="sp" style="left:{lo:.1f}%;width:{max(hi - lo, 0.8):.1f}%"></span>{punkte}</div>'
            f'<div class="mlab">{beschriftung}</div>')


def quellzeile(text) -> str:
    return f'<p class="src">{icon("info", 13)}<span>{esc(text)}</span></p>'


# ---- Abschnitte ------------------------------------------------------------------

def sektion_kopf(e, cfg) -> str:
    personen = cfg["scoring"]["personen"]
    basen = e["basen"]
    chips = ""
    aktuell = e["standard"]
    for b in cfg["basen"]:
        an = " on" if b["id"] == aktuell else ""
        chips += (f'<button type="button" class="base{an}" data-basis="{esc(b["id"])}" aria-pressed="{"true" if an else "false"}">'
                  f'{esc(b["name"].split(" (")[0])}'
                  f'<small>{b["von"].day}.{b["von"].month}. bis {b["bis"].day}.{b["bis"].month}.</small></button>')
    probleme = len(e["alarme"])
    if probleme:
        statusicon, text = icon("warn", 15), f"{probleme} Hinweis{'e' if probleme > 1 else ''} zu den Daten"
    else:
        statusicon, text = icon("check", 15), "alle Quellen aktuell"
    wellen = ('<svg class="waves" viewBox="0 0 250 96" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">'
              '<path d="M0 30c20-14 40-14 62 0s42 14 62 0 42-14 62 0 42 14 64 0" opacity=".9"/>'
              '<path d="M0 52c20-14 40-14 62 0s42 14 62 0 42-14 62 0 42 14 64 0" opacity=".6"/>'
              '<path d="M0 74c20-14 40-14 62 0s42 14 62 0 42-14 62 0 42 14 64 0" opacity=".35"/></svg>')
    return (f'<header class="top">{wellen}<div class="brand">{icon("wave", 32, "logo")}<h1>Surf-Check <span>Portugal</span></h1></div>'
            f'<nav class="bases" aria-label="Basis">{chips}</nav>'
            f'<div class="status">{statusicon}<span>Daten von {stand(e["daten_stand"])} '
            f'(<span id="stand-alter">gerade eben</span>) · {text} · <a href="#datenlage">Details</a></span></div></header>')


def sektion_alarme(e, cfg) -> str:
    teile = []
    teile.append('<div class="alert" id="veraltet" hidden>' + icon("warn", 20) +
                 '<div><b>Diese Seite ist veraltet</b>Der letzte Lauf liegt etwa <span class="alt"></span> Stunden zurück. '
                 'Die Zahlen unten sind nicht mehr aktuell. Bitte nicht darauf verlassen.</div></div>')
    for a in e["alarme"]:
        teile.append(f'<div class="alert">{icon("warn", 20)}<div><b>Datenproblem</b>{esc(a)}</div></div>')
    return f'<div class="alerts">{"".join(teile)}</div>'


def warum(b) -> str:
    if len(b["modelle"]) < 2:
        return f"Nur {len(b['modelle'])} Modell liefert Daten, deshalb ist die Aussage unsicher."
    teile = []
    if b["welle_m"] and b["welle_m"][1] - b["welle_m"][0] >= 0.1:
        teile.append(f"bei der Wellenhöhe um {zahl(b['welle_m'][1] - b['welle_m'][0])} m")
    pid = b["bester_pid"]
    je = [p for p in b["personen"][pid]["je_modell"].values() if p is not None]
    if je and max(je) - min(je) >= 2:
        teile.append(f"beim Score um {max(je) - min(je)} Punkte")
    return ("Die Modelle weichen " + " und ".join(teile) + " ab.") if teile else "Die Modelle liegen eng beieinander."


def sektion_hinweise(e, v, cfg) -> str:
    """IPMA-Warnungen der Basis und der Vergleichs-Hinweis, wenn die Basis erst später gilt."""
    teile = []
    for w in e["basen"][v["basis"]["id"]]["ipma"]["warnungen"]:
        teile.append(f'<div class="alert">{icon("warn", 20)}<div><b>IPMA-Warnung {esc(w["stufe"])}: {esc(w["art"])}</b>'
                     f'gilt bis {w["bis"].day}.{w["bis"].month}. {w["bis"]:%H:%M} Uhr. Bitte vor Ort prüfen.</div></div>')
    nicht = {}
    for sid in v["basis"]["spots"]:
        for n, info in e["spots"][(v["basis"]["id"], sid)]["daten"]["infos"]["wellen"].items():
            if info["status"] == "nicht_verfuegbar":
                nicht.setdefault(n, []).append(cfg["spots"][sid]["name"])
    for n, namen in nicht.items():
        teile.append(f'<div class="note-card">{icon("info", 20)}<span><b>Wellenmodell {esc(n)}:</b> Für '
                     f'{esc(", ".join(namen) if len(namen) <= 3 else str(len(namen)) + " Spots hier")} liefert es keine Werte, '
                     f'der Modellpunkt liegt an Land. Dort zählen nur die anderen Modelle.</span></div>')
    if not v["gueltig"]:
        b = v["basis"]
        teile.append(f'<div class="note-card">{icon("info", 20)}<span><b>Zum Vergleich.</b> Die Basis {esc(b["name"])} gilt '
                     f'vom {b["von"].day}.{b["von"].month}. bis {b["bis"].day}.{b["bis"].month}. Die Zahlen zeigen, '
                     f'wie es dort am {datum_kurz(e["anzeige"])} wäre.</span></div>')
    return f'<div class="alerts">{"".join(teile)}</div>' if teile else ""


def sektion_fazit(e, v, cfg) -> str:
    personen = cfg["scoring"]["personen"]
    f = v["fazit"]
    kopf = f'<p class="eyebrow">Zeigt: {esc(e["label"])}</p>'
    if f.get("spot") is None:
        return (f'<section class="card fazit">{kopf}<h2 class="verdict">Keine<br>Aussage</h2>'
                f'<p class="why">{esc(f.get("grund") or "Es liegen keine Daten vor.")}</p></section>')
    b = f["block"]
    spot = cfg["spots"][f["spot"]]["name"]
    ausweich_hinweis = '<p class="why">Ausweichspot, liegt weiter weg.</p>' if f.get("ausweich") else ""
    wort_tag = "Heute" if e["modus"] == "heute" else aw.WOCHENTAGE_LANG[e["anzeige"].weekday()]
    if f["ja"]:
        # In der großen Überschrift nur der Kurzname ("Cabedelo" statt "Cabedelo (Viana do Castelo)")
        titel = f'Ja, {esc(spot.split(" (")[0])}<br>{uhr_von_bis(b)} Uhr'
        zeile = ""
    else:
        titel = f'{esc(wort_tag)}<br>nicht'
        zeile = f'<p class="why">Bestes Fenster trotzdem: {esc(spot)}, {uhr_von_bis(b)} Uhr, höchster Score {f["hoechst"]}.</p>'
    s = b["sicherheit"] or "niedrig"
    pips = "".join(f'<i class="{"on" if i < STUFEN_WORT[s] else ""}"></i>' for i in range(3))
    aussicht = ""
    if not f["ja"] and f.get("aussicht"):
        a = f["aussicht"]
        if a["hoechst"] >= cfg["scoring"]["skala"]["surftag_ab_punkte"]:
            aussicht = (f'<p class="why" style="margin-top:-6px">Beste Aussicht: {tagname(a["datum"])} {datum_kurz(a["datum"])}, '
                        f'{esc(cfg["spots"][a["spot"]]["name"])}, {uhr_von_bis(a["block"])} Uhr, Score {a["hoechst"]}.</p>')
    zeiten = [x for v in e["laeufe"].values() for x in v.values() if x]
    lauf_von = f"Läufe {lauf_text(min(zeiten))} bis {lauf_text(max(zeiten))}" if zeiten else "Modellläufe unbekannt"
    quelle = f'Open-Meteo, {len(b["modelle"])} Modelle ({", ".join(b["modelle"])}) · {lauf_von}'
    return (f'<section class="card fazit">{kopf}<h2 class="verdict">{titel}</h2>{zeile}'
            f'{ausweich_hinweis}<div class="conf"><span>Sicherheit</span><span class="pips">{pips}</span><b>{esc(s)}</b></div>'
            f'<p class="why">{esc(warum(b))}</p>{aussicht}'
            f'<div class="win">{trio(b, personen)}</div>{quellzeile(quelle)}</section>')


def wind_pfeil(grad) -> str:
    return icon("arrow", 15, drehung=None if grad is None else (grad + 180) % 360)


def sektion_tage(e, cfg) -> str:
    personen = cfg["scoring"]["personen"]
    karten = []
    vorher = None
    for t in e["tage"]:
        basis = t["basis"]
        d = t["datum"]
        kopf = f'<div class="dh"><b>{tagname(d)}</b><span>{datum_kurz(d)}</span></div>'
        gezeigt = " gezeigt" if d == e["anzeige"] else ""
        if not basis:
            karten.append(f'<div class="day keine{gezeigt}">{kopf}<p class="hinweis">Keine Basis eingetragen. Spots für diesen Tag fehlen in der Konfiguration.</p></div>')
            vorher = basis
            continue
        tag_basis = ""
        if basis != vorher and vorher is not None:
            name = next(b["name"] for b in cfg["basen"] if b["id"] == basis).split(" (")[0]
            tag_basis = f'<span class="tag">Basis {esc(name)}</span>'
        vorher = basis
        w = t["wetter"] or {}
        if w.get("symbol"):
            wx = (f'<div class="wx">{icon(w["symbol"], 32)}<div class="tp">{zahl(w["tmax"], 0)}°'
                  f'<small>{zahl(w["tmin"], 0)}°</small></div></div>')
        else:
            wx = '<div class="wx"><div class="tp strich">–</div></div>'
        if w.get("wind_kn") is not None:
            wd = f'<div class="wd">{wind_pfeil(w["wind_richtung"])}{aw.kompass(w["wind_richtung"])} {zahl(w["wind_kn"], 0)} kn</div>'
        else:
            wd = '<div class="wd strich">Wind –</div>'
        if t["bester_spot"]:
            spot = esc(cfg["spots"][t["bester_spot"]]["name"])
            minis = "".join(mini(pid, t["personen"].get(pid), personen) for pid in personen)
            unten = f'<div><div class="bs">Bester Spot</div><b>{spot}</b></div><div class="minis">{minis}</div>'
        else:
            unten = '<p class="hinweis">Keine Scores, Daten fehlen.</p>'
        karten.append(f'<div class="day{gezeigt}">{kopf}{tag_basis}{wx}{wd}{unten}</div>')
    return (f'<div class="sec-h"><h2>Fünf Tage</h2><small>seitlich wischen</small></div><div class="days">{"".join(karten)}</div>')


def tide_zeile(b, ext, tide_info):
    """(Symbol, Hauptzeile, Kleintext) für die Tide eines Fensters."""
    if not b["tide"]:
        return "tidehigh", "–", "keine Tide-Daten"
    steigend = b["tide"]["richtung"] == "steigend"
    art = "HW" if steigend else "NW"
    start = b["start"].astimezone(UTC)
    nxt = next((t for a, t, _ in ext if a == art and t >= start), None)
    wort = "Hochwasser" if steigend else "Niedrigwasser"
    zeit = f"{wort} ca. {aw.lokal(nxt):%H:%M}" if nxt else wort
    if b["tide"]["quelle"] == "manuell":
        quelle = "eigener Eintrag"
    elif tide_info["quelle"] == "modell_korrigiert":
        quelle = "Modell, mit Pegel korrigiert"
    else:
        quelle = "Modell, unkorrigiert (±30 Min.)"
    return ("tidehigh" if steigend else "tidelow"), ("steigend" if steigend else "fallend"), f"{zeit}\n{quelle}"


def periode_hinweis(b) -> str:
    """Welche Periode wird gezeigt? Bei Swell und Windsee zählt die des größeren Anteils."""
    arten = set(b["periode_art"].values()) - {"übernommen"}
    if arten == {"Swell"}:
        return "Swell-Periode"
    if arten == {"Windsee"}:
        return "Windsee-Periode, also kurz und unruhig"
    if arten <= {"Swell", "Windsee"} and arten:
        return "Swell- oder Windsee-Periode, je nachdem was überwiegt"
    if arten == {"Spitze"}:
        return "Spitzenperiode"
    if arten == {"mittlere"}:
        return "mittlere Periode"
    return "Periode des größeren Anteils (Swell oder Windsee), sonst Spitzenperiode"


def faktor_text(fi) -> str:
    """' · Faktor 0,85 (gelernt aus 3 Beobachtungen)' oder nichts, wenn der Faktor kaum von 1 abweicht."""
    if not fi or abs(fi["gesamt"] - 1) < 0.03:
        return ""
    if fi["quelle"] == "eigene Beobachtungen":
        woher = f" (gelernt aus {fi['n']} Beobachtung{'en' if fi['n'] != 1 else ''})"
    elif fi["quelle"] == "andere Spots der Basis":
        woher = " (von den anderen Spots der Basis gelernt)"
    else:
        woher = " (von Hand eingestellt)"
    return f" · Faktor {zahl(fi['gesamt'], 2)}{woher}"


def metriken(b, spot, ext, tide_info, fi=None) -> str:
    modell = {n: v["welle"] for n, v in b["je_modell"].items()}
    maxwert = max(2.0, max(modell.values(), default=0) * 1.25)
    faktor_text_ = faktor_text(fi)
    gesamt = (f'<small>Die Modelle melden insgesamt {bereich(b["welle_gesamt_m"], 1)} m, '
              f'am Spot kommt davon weniger an (Richtung zur Küste, Windsee).</small>') if b.get("welle_gesamt_m") else ""
    welle = (f'<div class="m">{icon("wave")}<div><b>{bereich(b["welle_m"], 1, "m")}</b>'
             f'<small>Welle am Spot{faktor_text_}</small>{spannbalken(modell, maxwert)}{gesamt}</div></div>')
    periode = (f'<div class="m">{icon("period")}<div><b>{bereich(b["periode_s"], 0, "s")}</b>'
               f'<small>{esc(periode_hinweis(b))}</small></div></div>')
    wk = b["wind_kn"]
    if wk is not None:
        if wk[1] < 6:
            wind_t, wind_k = f"schwach, {bereich(wk, 0, 'kn')}", f"aus {aw.kompass(b['wind_richtung'])}"
        else:
            wind_t = f"{aw.kompass(b['wind_richtung'])} {bereich(wk, 0, 'kn')}"
            wind_k = f"{b['windart'] or ''}" + (f" · Böen {zahl(b['boeen_kn'], 0)} kn" if b["boeen_kn"] is not None else "")
    else:
        wind_t, wind_k = "–", "keine Winddaten"
    wind = (f'<div class="m">{wind_pfeil(b["wind_richtung"])}<div><b>{esc(wind_t)}</b><small>{esc(wind_k)}</small></div></div>')
    sym, haupt, klein = tide_zeile(b, ext, tide_info)
    tide = (f'<div class="m tide">{icon(sym)}<div><b>{esc(haupt)}</b><small>{esc(klein).replace(chr(10), "<br>")}</small></div></div>')
    return f'<div class="metrics">{welle}{periode}{wind}{tide}</div>'


def kurzzeile(b) -> str:
    teile = [f'<span>{icon("wave", 14)}{bereich(b["welle_m"], 1, "m")}</span>',
             f'<span>{icon("period", 14)}{bereich(b["periode_s"], 0, "s")}</span>']
    if b["wind_kn"] is not None:
        teile.append(f'<span>{wind_pfeil(b["wind_richtung"])}{aw.kompass(b["wind_richtung"])} {bereich(b["wind_kn"], 0, "kn")}</span>')
    return f'<div class="kurz">{"".join(teile)}</div>'


def fenster_karte(b, personen, spot, ext, tide_info, bester, e, fi=None) -> str:
    if b is None:
        return ""
    urteil = b["urteil"] or "–"
    offen = " open" if bester else ""
    klassen = "win card" + (" beste" if bester else "") + (" vorbei" if b["vorbei"] else "")
    beste_marke = '<em class="bl">bestes Fenster</em>' if bester else ""
    return (f'<details class="{klassen}"{offen} data-ende="{b["ende"].isoformat()}">'
            f'<summary><div class="win-h"><span class="wl"><span class="t">{uhr_von_bis(b, True)}<small>Uhr</small></span>{beste_marke}</span>'
            f'<span><span class="pill zeit">vorbei</span><span class="pill">{esc(urteil)}</span></span></div>'
            f'{trio(b, personen)}{kurzzeile(b)}<div class="mehr"><span class="zu">weniger</span><span class="auf">Details</span></div></summary>'
            f'{metriken(b, spot, ext, tide_info, fi)}</details>')


def spot_info(spot) -> str:
    z = []
    for label, key in (("Boden", "boden"), ("Welle", "wellentyp"), ("Niveau", "niveau")):
        if spot.get(key):
            z.append(f"<dt>{label}</dt><dd>{esc(spot[key])}</dd>")
    if spot.get("tide"):
        z.append(f'<dt>Tide</dt><dd>{esc(spot["tide"].replace("_", " bis "))}</dd>')
    if "groesse_min_m" in spot:
        z.append(f'<dt>Läuft ab</dt><dd>{zahl(spot["groesse_min_m"], 1)} m</dd>')
    if "groesse_max_m" in spot:
        z.append(f'<dt>Bis</dt><dd>{zahl(spot["groesse_max_m"], 1)} m</dd>')
    text = f'<dl>{"".join(z)}</dl>'
    for key, titel in (("notizen", None), ("unsicher", "Die Quellen widersprechen sich")):
        if spot.get(key):
            absaetze = "".join(f"{esc(zeile)}<br>" for zeile in spot[key].strip().splitlines() if zeile.strip())
            text += f'<p>{"<b>" + titel + ":</b><br>" if titel else ""}{absaetze}</p>'
    links = ([(u, "Webcams") for u in spot.get("webcams", [])] + [(u, "Vergleich") for u in spot.get("vergleich", [])]
             + [(u, "Spot-Guide") for u in spot.get("quellen", [])])
    ls = "".join(f'<a class="link" href="{esc(u)}" target="_blank" rel="noopener">{esc(t)}{icon("ext", 13)}</a>' for u, t in links)
    return (f'<details class="spotinfo"><summary>Über den Spot{icon("info", 16)}</summary>{text}'
            f'<div class="links" style="padding-bottom:12px">{ls}</div></details>')


def beobachtungs_link(cfg) -> str:
    repo = cfg.get("seite", {}).get("github_repo")
    if not repo:
        return "in <code>config/beobachtungen.toml</code>"
    return (f'<a href="https://github.com/{esc(repo)}/edit/main/config/beobachtungen.toml" target="_blank" rel="noopener">'
            f'Beobachtung eintragen</a>, GitHub-Anmeldung nötig')


def sektion_detail(e, v, cfg) -> str:
    personen = cfg["scoring"]["personen"]
    t = v["tag"]
    if not t["basis"]:
        return ""
    bi = e["basen"][t["basis"]]
    kopf = f'<div class="sec-h"><h2>Heute im Detail</h2><small>{tagname(e["anzeige"])} {datum_kurz(e["anzeige"])}</small></div>'
    if e["modus"] == "morgen":
        kopf = f'<div class="sec-h"><h2>{aw.WOCHENTAGE_LANG[e["anzeige"].weekday()]} früh</h2><small>{datum_kurz(e["anzeige"])}</small></div>'
    spot_ids = list(t["spots"])
    chips = "".join(f'<button type="button" class="chip{" on" if i == 0 else ""}" data-spot="{esc(sid)}">'
                    f'{esc(cfg["spots"][sid]["name"])}'
                    f'{"<small>Ausweich</small>" if cfg["spots"][sid].get("ausweich") else ""}</button>'
                    for i, sid in enumerate(spot_ids))
    panels = []
    for i, sid in enumerate(spot_ids):
        spot = cfg["spots"][sid]
        s = t["spots"][sid]
        beste = s["bester"]
        fi = e["lernen"]["faktoren"][sid]
        karten = "".join(fenster_karte(b, personen, spot, bi["ext"], bi["tide"], b is beste, e, fi) for b in s["bloecke"])
        if not karten:
            karten = f'<div class="note-card">{icon("info", 20)}<span>Für diesen Spot gibt es keine auswertbaren Zeitfenster (Daten fehlen).</span></div>'
        kal = ""
        if beste and beste["welle_modell_m"]:
            kal = (f'<div class="note-card kal">{icon("ruler", 20)}<span><b>Stimmt das?</b> Am Spot erwartet das Tool '
                   f'{bereich(beste["welle_modell_m"], 1)} m. Siehst du etwas anderes, trag es als Beobachtung ein, '
                   f'das Tool lernt daraus ({beobachtungs_link(cfg)}).</span></div>')
        panels.append(f'<div class="panel" data-panel="{esc(sid)}"{"" if i == 0 else " hidden"}>{karten}{kal}{spot_info(spot)}</div>')
    return f'{kopf}<div class="chips" role="tablist">{chips}</div>{"".join(panels)}'


def punkte_text(werte) -> str:
    """'3' oder '3 bis 4'."""
    lo, hi = min(werte), max(werte)
    return str(lo) if lo == hi else f"{lo} bis {hi}"


def empfehlung_signatur(emp, cfg):
    """Zwei Personen mit gleicher Signatur bekommen einen gemeinsamen Text."""
    skala_cfg = cfg["scoring"]["skala"]
    a, w = emp["anzeige"], emp["woche"]
    besser = bool(w and w["punkte"] >= skala_cfg["surftag_ab_punkte"] and (a is None or w["punkte"] > a["punkte"]))
    return (
        (a["spot"], a["block"]["start"], a["punkte"] >= skala_cfg["surftag_ab_punkte"]) if a else None,
        (w["datum"], w["spot"], w["block"]["start"]) if besser else None,
    )


def satz_gruppe(pids, empf, cfg, e) -> str:
    """Empfehlungstext für eine oder mehrere Personen mit gleicher Lage."""
    skala_cfg = cfg["scoring"]["skala"]
    erste = empf[pids[0]]
    a, w = erste["anzeige"], erste["woche"]
    wort = "Heute" if e["modus"] == "heute" else aw.WOCHENTAGE_LANG[e["anzeige"].weekday()]
    teile = []
    if a is None:
        teile.append(f"{wort} gibt es keine auswertbaren Zeitfenster.")
    else:
        b, spot = a["block"], cfg["spots"][a["spot"]]["name"]
        pkt = punkte_text([empf[p]["anzeige"]["punkte"] for p in pids])
        urteile = {b["urteile"].get(p) for p in pids if b["urteile"].get(p)}
        urteil_text = f", {esc(sorted(urteile)[0])}" if len(urteile) == 1 else ""
        wind = ""
        if b["wind_kn"] is not None:
            wind = ("schwachem Wind" if b["wind_kn"][1] < 6 else f"{aw.kompass_lang(b['wind_richtung'])}wind {bereich(b['wind_kn'], 0, 'kn')}")
        if a["punkte"] >= skala_cfg["surftag_ab_punkte"]:
            stufen = {score.stufe(empf[p]["anzeige"]["punkte"], skala_cfg) for p in pids}
            stufe = f" ({sorted(stufen)[0]})" if len(stufen) == 1 else ""
            teile.append(f"{esc(spot)}, {uhr_von_bis(b)} Uhr: Score {pkt}{stufe}.")
            # Die Bedingungen nennen wir nur, wenn es sich lohnt. An schlechten Tagen steht alles in den Details.
            if b["welle_m"] and wind:
                teile.append(f"{bereich(b['welle_m'], 1, 'm')} Welle bei {bereich(b['periode_s'], 0, 's')} Periode, dazu {wind}.")
        else:
            teile.append(f"{wort} lohnt es kaum: Das beste Fenster ist {esc(spot)}, {uhr_von_bis(b)} Uhr, nur Score {pkt}{urteil_text}.")
    if w and w["punkte"] >= skala_cfg["surftag_ab_punkte"] and (a is None or w["punkte"] > a["punkte"]):
        pkt_w = punkte_text([empf[p]["woche"]["punkte"] for p in pids])
        teile.append(f"Besser wird es {tagname(w['datum'])} {datum_kurz(w['datum'])}: {esc(cfg['spots'][w['spot']]['name'])}, "
                     f"{uhr_von_bis(w['block'])} Uhr, Score {pkt_w}.")
    return " ".join(teile)


def sektion_empfehlung(e, v, cfg) -> str:
    personen = cfg["scoring"]["personen"]
    empf = v["empfehlung"]
    gruppen = []  # (Signatur, [pids])
    for pid in personen:
        sig = empfehlung_signatur(empf[pid], cfg)
        for g in gruppen:
            if g[0] == sig:
                punkte = [empf[p]["anzeige"]["punkte"] for p in g[1] + [pid] if empf[p]["anzeige"]]
                if not punkte or max(punkte) - min(punkte) <= 1:
                    g[1].append(pid)
                    break
        else:
            gruppen.append((sig, [pid]))
    zeilen = ""
    for _, pids in gruppen:
        avs = "".join(avatar(p, personen, 44 if len(pids) > 1 else 52) for p in pids)
        zeilen += f'<div class="rec"><div class="avs">{avs}</div><p>{satz_gruppe(pids, empf, cfg, e)}</p></div>'
    return f'<div class="sec-h"><h2>Für euch drei</h2><small>aus den Scores</small></div><div class="card">{zeilen}</div>'


def hoehe_text(h) -> str:
    """Höhe auf eine Dezimalstelle, kaufmännisch gerundet (0,95 wird 1,0)."""
    return "–" if h is None else zahl(score.runde(h * 10) / 10.0, 1)


def fahrzeit_text(z) -> str:
    f = z["fahrzeit_min"]
    if isinstance(f, list):
        return f"{f[0]} bis {f[1]} min" if f[0] else f"bis {f[1]} min"
    return "ohne Anfahrt" if f == 0 else f"ca. {f} min"


def sektion_ausfluege(e, v, cfg) -> str:
    a = v["ausfluege"]
    if not a["vorschlaege"] and not a["hinweis"]:
        return ""
    unterzeile = {"regen": "Regentag", "nordwind": "starker Nordwind", "warm_ruhig": "warm und ruhig",
                  "normal": "Tagestipp", None: ""}[a["modus"]]
    if a["surftag"]:
        unterzeile = "Surftag: Nachmittag, kurz"
    kopf = f'<div class="sec-h"><h2>Abseits vom Wasser</h2><small>{esc(unterzeile)}</small></div>'
    labels = {"kurz": "kurz", "halbtag": "Halbtag", "ganztag": "ganzer Tag"}
    teile = ""
    for x in a["vorschlaege"]:
        z = x["ziel"]
        hund = "Hund: an der Leine" if z["hund"] == "erlaubt_leine" else "Hund: unklar"
        quelle = (f' <a href="{esc(z["quelle"])}" target="_blank" rel="noopener">Quelle</a>' if z.get("quelle") else "")
        teile += (f'<div class="trip"><div class="ico-box">{icon(z["symbol"], 24)}</div><div><b>{esc(z["name"])}</b>'
                  f'<p>{esc(z["beschreibung"])}{quelle}</p><div class="tags"><span class="pill">{esc(x["grund"])}</span>'
                  f'<span class="pill">{esc(fahrzeit_text(z))} (geschätzt)</span><span class="pill">{esc(labels[z["dauer"]])}</span>'
                  f'<span class="pill">{hund}</span></div></div></div>')
    if a["hinweis"]:
        teile += f'<div class="note-card">{icon("info", 20)}<span>{esc(a["hinweis"])}</span></div>'
    return f'{kopf}<div class="card">{teile}</div>'


def ansicht_html(e, v, cfg, teil) -> str:
    """Die Abschnitte, die zu einer Basis gehören. `teil` ist 'vorn' (vor der Fünf-Tage-Leiste) oder 'hinten'."""
    bid = v["basis"]["id"]
    if teil == "vorn":
        inhalt = sektion_hinweise(e, v, cfg) + sektion_fazit(e, v, cfg)
    else:
        inhalt = (sektion_detail(e, v, cfg) + sektion_empfehlung(e, v, cfg) + sektion_ausfluege(e, v, cfg)
                  + sektion_baden(e, v, cfg))
    versteckt = "" if bid == e["standard"] else " hidden"
    return f'<div class="ansicht" data-basis="{esc(bid)}"{versteckt}>{inhalt}</div>'


def sektion_legende(cfg) -> str:
    """Wer ist wer, und worauf beruht der Score? Ohne Namen, nur Avatare, Brett und Vorlieben."""
    regeln = cfg["scoring"]
    personen = regeln["personen"]
    skala_cfg = regeln["skala"]
    kopfzeile, koerper = "", ""
    for pid, p in personen.items():
        sw = score.schwellen(p, regeln)
        kopfzeile += (f'<div class="lp">{avatar(pid, personen, 56)}<b>{esc(p.get("kurz", ""))}</b>'
                      f'<small>surfbar ab {hoehe_text(sw["surfbar"])} m</small></div>')
        koerper += (f'<div class="rec">{avatar(pid, personen, 52)}<p>{esc(p.get("beschreibung", ""))}'
                    f'<br><small>Bei 10 s Periode und schwachem ablandigem Wind: surfbar (Score {skala_cfg["lohnt_kaum_bis"] + 1}) '
                    f'ab etwa {hoehe_text(sw["surfbar"])} m, gut (Score {skala_cfg["surfbar_bis"] + 1}) ab etwa {hoehe_text(sw["gut"])} m. '
                    f'Die vollen Grundpunkte gibt es ab etwa {hoehe_text(score.optimal_ab(p))} m.</small></p></div>')
    modelle = ", ".join(m["name"] for m in cfg["quellen"]["modelle"])
    farben = (f'<span class="fk"><i class="s on r"></i>1 bis {skala_cfg["lohnt_kaum_bis"]} lohnt kaum</span>'
              f'<span class="fk"><i class="s on o"></i>{skala_cfg["lohnt_kaum_bis"] + 1} bis {skala_cfg["surfbar_bis"]} surfbar</span>'
              f'<span class="fk"><i class="s on g"></i>{skala_cfg["surfbar_bis"] + 1} bis {skala_cfg["gut_bis"]} gut, {skala_cfg["gut_bis"] + 1} Pflichttermin</span>')
    return (f'<section class="card legende"><details><summary><div class="lps">{kopfzeile}</div>'
            f'<span class="leg-mehr">Wer ist wer, und wie wird bewertet?{icon("info", 15)}</span></summary>'
            f'<div class="leg-body"><p>Jede Skala gehört zu einer Person. Der Score von 1 bis 10 wird für jede einzeln gerechnet, '
            f'weil Brett und passende Wellengröße verschieden sind. Die leeren Segmente haben die Farbe der Person.</p>{koerper}'
            f'<h3>So entsteht der Score</h3><ol>'
            f'<li>Die Wellenhöhe am Spot gibt die Grundpunkte von 0 bis 10. Das ist die brechende Welle, nicht die Höhe draußen auf dem Meer: '
            f'Swell und Windsee werden getrennt betrachtet, und jede Welle zählt nur so weit, wie sie auf die Küste zuläuft. '
            f'Windsee, die bei Nordwind entlang der Küste läuft, bricht dort nicht.</li>'
            f'<li>Periode, Richtung des Swells, Wind (ablandig, seitlich, auflandig) und Tide ziehen davon Prozente ab. '
            f'Auflandiger Wind und kurze Perioden kosten am meisten.</li>'
            f'<li>Das wird mit {len(cfg["quellen"]["modelle"])} Wettermodellen einzeln gerechnet ({esc(modelle)}). '
            f'Der Score ist der Mittelwert. Die Sicherheit sagt, wie einig sich die Modelle waren.</li>'
            f'<li>Wer am Spot etwas anderes sieht als das Tool, kann es als Beobachtung eintragen. Das Tool lernt daraus pro Spot, '
            f'wie viel Welle wirklich ankommt, und rechnet ab dem nächsten Lauf damit.</li></ol>'
            f'<div class="fkr">{farben}</div>'
            f'<p class="src">{icon("info", 13)}<span>Das sind Prognosen aus Wettermodellen, keine Messungen. Quellen und Modellläufe stehen unten unter Datenlage.</span></p>'
            f'</div></details></section>')


def sektion_baden(e, v, cfg) -> str:
    bd = v["baden"]
    if not bd:
        return ""
    ring = []
    bester_datum = bd["bester"]["datum"] if bd["bester"] else None
    for x in bd["tage"]:
        r = x["ergebnis"]
        p = 0 if not r else round(r["prozent"] * 100)
        ring.append(f'<div class="wk{" best" if x["datum"] == bester_datum else ""}"><span>{tagname(x["datum"])}</span>'
                    f'<i class="ring" style="--p:{p}" title="{p} %"></i></div>')
    spalten = f'style="grid-template-columns:repeat({max(len(ring), 1)},1fr)"'
    if bd["bester"]:
        r = bd["bester"]["ergebnis"]
        det = r["details"]
        zeile = (f'Luft {zahl(det["temp"], 0)} °C, Wind {zahl(det["wind"], 0)} kn, Regen {zahl(det["regen"], 0)} %'
                 + (", nahe Hochwasser" if det["tide"] is not None and det["tide"] >= 0.7 else "")
                 + ("" if r["mit_tide"] else ", ohne Tide gerechnet"))
        haupt = f'Bester Tag: {tagname(bd["bester"]["datum"])} {datum_kurz(bd["bester"]["datum"])}, ab {r["ab_uhr"]} Uhr'
    else:
        haupt, zeile = "Kein guter Badetag in den nächsten Tagen", "zu kühl, zu windig oder zu nass"
    wasser = ""
    if bd["wasser_c"]:
        wasser = (f'<p class="src" style="margin-top:6px">{icon("info", 13)}<span>Meer vor Viana: {zahl(float(bd["wasser_c"][0]), 1)} '
                  f'bis {zahl(float(bd["wasser_c"][1]), 1)} °C (IPMA, {datum_kurz(datetime.fromisoformat(bd["wasser_datum"]))})</span></p>')
    return (f'<div class="sec-h"><h2>Baden im Minho</h2><small>{esc(bd["ort"])}</small></div><div class="card">'
            f'<div class="week" {spalten}>{"".join(ring)}</div>'
            f'<div class="bad-line">{icon("tidehigh", 24)}<div><b>{esc(haupt)}</b><small>{esc(zeile)}</small></div></div>'
            f'{wasser}{quellzeile("Open-Meteo, IPMA, Gezeiten wie oben")}</div>')


def status_zeile(name, detail, info, zeit_text=None, ok=None) -> str:
    ok = (info["status"] == "aktuell") if ok is None else ok
    sym = "check" if ok else "warn"
    zusatz = {"aktuell": "", "veraltet": " (veraltet)", "ausgefallen": " (ausgefallen)",
              "nicht_verfuegbar": " (an einigen Orten ohne Werte)"}[info["status"]]
    zeit = zeit_text if zeit_text is not None else stand(info.get("stand"))
    fehler = f' · {esc(info["fehler"])}' if info.get("fehler") and not ok else ""
    return (f'<div class="srow{"" if ok else " warn"}">{icon(sym, 16)}<div>{esc(name)}{zusatz}'
            f'<small>{detail}{fehler}</small></div><time>{esc(zeit)}</time></div>')


def lernen_zeile(e, cfg) -> str:
    """Was hat das Tool aus den Beobachtungen gelernt?"""
    l = e["lernen"]
    link = beobachtungs_link(cfg)
    if not l["anzahl"]:
        text = f"Noch keine nutzbaren Beobachtungen. Siehst du am Spot etwas anderes als das Tool, trag es ein ({link}). Das Tool lernt daraus, wie viel Welle an jedem Spot wirklich ankommt."
    else:
        eigene = [(sid, f) for sid, f in l["faktoren"].items() if f["quelle"] == "eigene Beobachtungen"]
        liste = ", ".join(f'{esc(cfg["spots"][sid]["name"].split(" (")[0])} {zahl(f["lern"], 2)} ({f["n"]} Beob.)' for sid, f in eigene)
        text = (f'{l["anzahl"]} Beobachtung{"en" if l["anzahl"] != 1 else ""} genutzt. Gesehene Höhe geteilt durch die Höhe des Tools '
                f'im Schnitt {zahl(l["median_verhaeltnis"], 2)} (1,00 wäre genau richtig). Gelernte Faktoren: {liste}. '
                f'Die anderen Spots der Basis übernehmen die Hälfte der Korrektur. Wenige Beobachtungen verschieben den Faktor nur vorsichtig.')
        if l["pruefung"]:
            p = l["pruefung"]
            text += (f' Test ohne Mogeln: Das Tool lag im Schnitt {zahl(p["fehler_vorher_m"], 2)} m daneben ohne Lernen '
                     f'und {zahl(p["fehler_nachher_m"], 2)} m mit Lernen.')
        text += f' Weitere Beobachtung: {link}.'
    return status_zeile("Lernen aus Beobachtungen", text, {"status": "aktuell", "stand": None}, zeit_text="", ok=True)


def sektion_datenlage(e, cfg) -> str:
    zeilen = []
    modelle = cfg["quellen"]["modelle"]
    alle_spots = [(k, v) for k, v in e["spots"].items()]
    lauf = e["laeufe"]
    # Wetter
    inf = aw.schlechtester_status(v["daten"]["infos"]["wetter"] for _, v in alle_spots)
    laeufe = ", ".join(f'{esc(n)} {lauf_text(l["wetter"])}' for n, l in lauf.items())
    zeilen.append(status_zeile("Open-Meteo Wetter", f"Wind, Temperatur, Regen. Läufe: {laeufe}", inf))
    # Wellen
    for_info = [i for _, v in alle_spots for i in v["daten"]["infos"]["wellen"].values()]
    inf = aw.schlechtester_status(for_info)
    erster = alle_spots[0][1]["daten"]["infos"]["wellen"] if alle_spots else {}
    punkte = ", ".join(f'{esc(n)} {zahl(i["punkt"][0], 2)}/{zahl(i["punkt"][1], 2)}' for n, i in erster.items() if i.get("punkt"))
    laeufe_w = ", ".join(f'{esc(n)} {lauf_text(l["welle"])}' for n, l in lauf.items())
    zeilen.append(status_zeile("Open-Meteo Wellen", f"Läufe: {laeufe_w}. GFS und Météo-France trennen Swell und Windsee, ECMWF liefert nur die Gesamthöhe. "
                               f"Dort wird der Swell-Anteil der anderen beiden übernommen. "
                               f"Modellpunkte auf dem Meer (Breite/Länge): {punkte}.", inf))
    # Tide
    for bid, b in e["basen"].items():
        ti = b["tide"]
        if ti["quelle"] == "modell_korrigiert":
            text = (f'Modellkurve, mit dem gemessenen Pegel {esc(ti["pegel"])} (Viana do Castelo, Instituto Hidrográfico) korrigiert: '
                    f'Versatz {zahl(ti["versatz_min"], 0)} Min. aus {ti["paare"]} Hoch-/Niedrigwassern. '
                    + esc(next((x.get("pegel_test", "") for x in cfg["basen"] if x["id"] == bid), "")))
        elif ti["quelle"] == "modell":
            text = esc(ti["hinweis"] or "Modellkurve ohne Korrektur.")
        else:
            text = "Keine Tide-Daten, die Tide fließt nicht in den Score ein."
        if ti["manuelle_tage"]:
            text += " Eigene Einträge für: " + ", ".join(datum_kurz(d) for d in ti["manuelle_tage"]) + "."
        else:
            text += " Eigene Einträge: keine (config/gezeiten_manuell.toml)."
        name = next(x["name"] for x in cfg["basen"] if x["id"] == bid).split(" (")[0]
        ok = ti["quelle"] == "modell_korrigiert" and ti["status"]["status"] == "aktuell"
        zeilen.append(status_zeile(f"Gezeiten {name}", text, ti["status"], ok=ok))
    # IPMA
    for bid, b in e["basen"].items():
        ip = b["ipma"]
        if ip["status"]:
            inf = aw.schlechtester_status(ip["status"].values())
            teile = []
            if ip["warnungen"]:
                teile.append("Warnungen: " + ", ".join(f'{esc(w["art"])} ({esc(w["stufe"])})' for w in ip["warnungen"]))
            else:
                teile.append("keine Warnungen (alle grün)")
            sd = ip["stadt"].get(e["anzeige"].isoformat())
            if sd:
                teile.append(f'Viana heute {zahl(float(sd["tMin"]), 0)} bis {zahl(float(sd["tMax"]), 0)} °C, Regenwahrscheinlichkeit {zahl(float(sd["precipitaProb"]), 0)} %')
            zeilen.append(status_zeile("IPMA", " · ".join(teile) + ". Wassertemperatur und Warnungen kommen von dort.", inf))
    zeilen.append(lernen_zeile(e, cfg))
    # Modell-Uneinigkeit
    v0 = e["ansichten"][e["standard"]]
    f = v0["fazit"]
    if f.get("block"):
        b = f["block"]
        wellen = {n: v["welle"] for n, v in b["je_modell"].items()}
        zeilen_u = ""
        if len(wellen) >= 2:
            d = max(wellen.values()) - min(wellen.values())
            unein = d >= 0.1
            text = ", ".join(f'{esc(n)} {zahl(v, 2)} m' for n, v in wellen.items())
            balken = spannbalken(wellen, max(2.0, max(wellen.values()) * 1.25))
            kopf = "Modelle uneinig: Wellenhöhe" if unein else "Modelle einig: Wellenhöhe"
            zeilen_u = (f'<div class="srow{" warn" if unein else ""}">{icon("warn" if unein else "check", 16)}'
                        f'<div>{kopf}<small>Bestes Fenster {esc(cfg["spots"][f["spot"]]["name"])} {uhr_von_bis(b)} Uhr: {text}</small>{balken}</div><time></time></div>')
        zeilen.append(zeilen_u)
    links = []
    for b in cfg["basen"]:
        for l in b.get("links", []):
            links.append((l["text"], l["url"]))
    for sid in v0["tag"]["spots"]:
        sp = cfg["spots"][sid]
        for u in sp.get("vergleich", []):
            host = u.split("/")[2].replace("www.", "")
            links.append((f'{host.split(".")[0].capitalize()} {sp["name"]}', u))
    gesehen, ls = set(), ""
    for text, u in links:
        if u in gesehen:
            continue
        gesehen.add(u)
        ls += f'<a class="link" href="{esc(u)}" target="_blank" rel="noopener">{esc(text)}{icon("ext", 13)}</a>'
    return (f'<div class="sec-h" id="datenlage"><h2>Datenlage</h2><small>jede Zahl mit Quelle</small></div>'
            f'<div class="card">{"".join(zeilen)}</div>'
            f'<div class="sec-h" style="margin-top:18px"><h2 style="font-size:16px">Vergleich und Webcams</h2><small>nur Links</small></div>'
            f'<div class="links">{ls}</div>')


SKRIPT = """
(function () {
  var d = document.body.dataset, jetzt = new Date(), erzeugt = new Date(d.erzeugt), max = Number(d.maxalter);
  var alter = (jetzt - erzeugt) / 36e5;
  var s = document.getElementById('stand-alter');
  if (s) s.textContent = alter < 1 ? 'vor weniger als 1 Std.' : 'vor ' + Math.round(alter) + ' Std.';
  var v = document.getElementById('veraltet');
  if (v && alter > max) { v.hidden = false; v.querySelector('.alt').textContent = Math.round(alter); }
  document.querySelectorAll('[data-ende]').forEach(function (el) {
    if (new Date(el.dataset.ende) < jetzt) el.classList.add('vorbei');
  });
  document.querySelectorAll('.ansicht').forEach(function (a) {
    var chips = a.querySelectorAll('.chip[data-spot]');
    chips.forEach(function (c) {
      c.addEventListener('click', function () {
        chips.forEach(function (x) { x.classList.toggle('on', x === c); });
        a.querySelectorAll('.panel').forEach(function (p) { p.hidden = p.dataset.panel !== c.dataset.spot; });
      });
    });
  });
  var basen = document.querySelectorAll('.base[data-basis]');
  function waehle(id) {
    basen.forEach(function (b) { var an = b.dataset.basis === id; b.classList.toggle('on', an); b.setAttribute('aria-pressed', an); });
    document.querySelectorAll('.ansicht').forEach(function (a) { a.hidden = a.dataset.basis !== id; });
  }
  basen.forEach(function (b) {
    b.addEventListener('click', function () { waehle(b.dataset.basis); try { history.replaceState(null, '', '#' + b.dataset.basis); } catch (e) {} });
  });
  var h = location.hash.slice(1);
  basen.forEach(function (b) { if (b.dataset.basis === h) waehle(h); });
})();
"""


def farben_css(personen) -> str:
    dunkel = ";".join(f"--c-{pid}:{p['farbe_dunkel']}" for pid, p in personen.items())
    hell = ";".join(f"--c-{pid}:{p['farbe_hell']}" for pid, p in personen.items())
    return f":root{{{dunkel}}}@media (prefers-color-scheme: light){{:root{{{hell}}}}}"


def baue_seite(cfg, e) -> str:
    personen = cfg["scoring"]["personen"]
    stil = (ROOT / "vorlage" / "stil.css").read_text(encoding="utf-8")
    avatare = (ROOT / "vorlage" / "avatare.svg").read_text(encoding="utf-8")
    favicon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23F3CB7A' "
               "stroke-width='2' stroke-linecap='round'%3E%3Cpath d='M2 9c2.200-3 4.400-3 6.600 0s4.400 3 6.600 0 4.400-3 6.800 0'/%3E%3Cpath d='M2 15c2.200-3 4.400-3 6.600 0s4.400 3 6.600 0 4.400-3 6.800 0'/%3E%3C/svg%3E")
    vorn = "".join(ansicht_html(e, v, cfg, "vorn") for v in e["ansichten"].values())
    hinten = "".join(ansicht_html(e, v, cfg, "hinten") for v in e["ansichten"].values())
    teile = [sektion_kopf(e, cfg), sektion_alarme(e, cfg), sektion_legende(cfg), vorn, sektion_tage(e, cfg),
             hinten, sektion_datenlage(e, cfg)]
    fuss = ('<p class="foot">Daten: <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a> (CC BY 4.0), '
            'IPMA, gemessene Pegel des Instituto Hidrográfico (CC BY-NC 4.0). Modelle sind Prognosen und ersetzen keinen Blick aufs Wasser '
            'und keine Warnungen vor Ort.</p>')
    return (f'<!doctype html><html lang="de"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark light">'
            f'<title>Surf-Check Portugal</title><meta name="description" content="Lohnt sich heute das Surfen? Wellen, Wind, Tide und Wetter für die portugiesische Küste.">'
            f'<link rel="icon" href="{favicon}"><style>{stil}{farben_css(personen)}</style></head>'
            f'<body data-erzeugt="{e["daten_stand"]}" data-maxalter="{cfg["quellen"]["daten"]["max_alter_stunden"]}">'
            f'{avatare}{symbole.icon_definitionen()}<div class="app">{"".join(teile)}{fuss}</div>'
            f'<script>{SKRIPT}</script></body></html>')


def schreibe(htmltext: str) -> Path:
    AUSGABE.mkdir(exist_ok=True)
    ziel = AUSGABE / "index.html"
    ziel.write_text(htmltext, encoding="utf-8")
    quelle_schriften = ROOT / "vorlage" / "schriften"
    if quelle_schriften.exists():
        shutil.copytree(quelle_schriften, AUSGABE / "schriften", dirs_exist_ok=True)
    (AUSGABE / ".nojekyll").write_text("", encoding="utf-8")
    return ziel


def main(jetzt=None) -> int:
    try:
        cfg = config.lade()
    except config.ConfigFehler as err:
        print("Fehler in der Konfiguration:\n  " + str(err))
        return 1
    datei = ROOT / "data" / "rohdaten.json"
    if not datei.exists():
        print("Es gibt noch keine Daten. Zuerst  python3 fetch.py  ausführen (oder  python3 aktualisieren.py).")
        return 1
    roh = json.loads(datei.read_text(encoding="utf-8"))
    jetzt = jetzt or datetime.now(UTC)
    ergebnis = aw.auswerten(cfg, roh, jetzt)
    ziel = schreibe(baue_seite(cfg, ergebnis))
    print(f"Seite geschrieben: {ziel.relative_to(ROOT)} ({ziel.stat().st_size // 1024} KB), Zeigt: {ergebnis['label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
