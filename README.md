# Surf-Check Portugal

Eine kleine Seite, die morgens zeigt, ob und wo sich das Surfen lohnt: Score von 1 bis 10 für drei Personen, Zeitfenster, Wetter für fünf Tage, Tide, Ausflugstipps und Badehinweis. Die Daten kommen von Open-Meteo (drei Wettermodelle), IPMA und gemessenen Pegeln des Instituto Hidrográfico. Jede Zahl auf der Seite nennt ihre Quelle.

## 1. Die Seite am Mac neu erzeugen und ansehen

Terminal öffnen, in den Ordner wechseln und den Befehl starten:

    cd ~/Desktop/Privat/surf-check-portugal
    python3 aktualisieren.py

Das holt frische Daten, rechnet alles aus und schreibt die Seite nach `docs/index.html`. Diese Datei öffnest du per Doppelklick im Browser.

Wenn du nur etwas an den Regeln geändert hast und keine neuen Daten brauchst:

    python3 aktualisieren.py --ohne-abruf

## 2. Etwas ändern

Alles, was du ändern darfst, steht in `config/`. Jede Datei erklärt sich oben selbst. Öffnen kannst du sie mit TextEdit, zum Beispiel so:

    open -e config/spots.toml

**Wichtig bei TextEdit:** Unter *Bearbeiten > Ersetzungen* die „Intelligenten Anführungszeichen“ ausschalten, sonst werden aus `"` krumme Zeichen und die Datei lässt sich nicht mehr lesen. Besser ist ein Editor für Programmtext, zum Beispiel das kostenlose Visual Studio Code.

Nach dem Speichern `python3 aktualisieren.py --ohne-abruf` ausführen. Macht du einen Fehler (etwa ein Anführungszeichen vergessen), sagt dir das Programm auf Deutsch, in welcher Datei und welchem Abschnitt.

### Einen Spot ändern oder hinzufügen (`config/spots.toml`)

- Ändern: Suche den Block `[spots.moledo]` und ändere die Werte, zum Beispiel `wind_dir_deg = [36, 144]`.
- Hinzufügen: Block kopieren, neuen Namen geben (`[spots.mein_spot]`), Werte anpassen und den Namen (`"mein_spot"`) in die Liste `spots` der passenden Basis eintragen. Mehr steht ganz oben in der Datei.

### Den Korrekturfaktor eines Spots ändern

Die Modelle messen draußen auf dem Meer. Am Strand sieht die brechende Welle oft anders aus. Der Faktor gleicht das aus. Beispiel: Das Modell sagt 1,0 m, du siehst am Spot etwa 0,8 m. Dann in `[spots.moledo]` die Zeile

    korrekturfaktor = 1.0

auf `0.8` ändern (mit Punkt, nicht Komma). Ein einzelner Blick reicht nicht, nimm lieber zwei oder drei Vergleiche. Die Seite erinnert dich im Abschnitt „Heute im Detail“ daran.

### Hoch- und Niedrigwasser selbst eintragen (`config/gezeiten_manuell.toml`)

Wenn du die Zeiten aus einer Tabelle kennst, trage sie für den Tag ein. Dann gilt für diesen Tag deine Angabe statt der Modellrechnung, und die Tide wirkt stärker auf den Score:

    [[gezeiten]]
    datum         = 2026-10-08
    hochwasser    = ["02:11", "14:24"]
    niedrigwasser = ["08:12", "20:35"]

Uhrzeiten sind portugiesische Ortszeit, in Anführungszeichen.

### Eine Score-Regel ändern (`config/scoring.toml`)

Ganz oben steht, wie die Datei zu lesen ist. Zahlenreihen wie `[[0.6, 0], [1.4, 10]]` sind Kennlinien: „bei 0,6 gibt es 0, bei 1,4 gibt es 10, dazwischen eine Gerade“. Danach zeigt dir

    python3 probe.py

an Beispieltagen, wie sich die Scores verschieben, ohne dass du auf neue Daten warten musst.

### Ausflüge ändern (`config/ausfluege.toml`)

Pro Ziel ein Block mit Fahrzeit, Bedingung (wann es passt), Dauer und Hund. Die Regeln für die Auswahl (Regen, Nordwind, warm und ruhig, Surftag) stehen oben in der Datei.

## 3. Im Internet veröffentlichen (einmalig)

Die Seite läuft kostenlos auf GitHub Pages. GitHub baut sie jeden Tag dreimal neu (kurz nach 6:00, 9:00 und 18:00 Uhr portugiesischer Zeit) und holt dabei frische Daten. Der Lauf um 9:00 ist dafür da, dass die Seite auch den Wettermodell-Lauf von heute früh nutzt, der erst gegen 8:45 Uhr fertig ist. Du schickst deinen Freunden nur den Link.

1. **Konto anlegen** auf github.com (kostenlos), falls noch nicht geschehen.
2. **Neues Repository** anlegen (grünes Plus oben rechts > *New repository*). Name `surf-check-portugal`, Sichtbarkeit **Public**. Die Haken für README, .gitignore und Lizenz leer lassen.
3. **Ordner hochladen.** Am einfachsten mit der kostenlosen App *GitHub Desktop* (desktop.github.com): anmelden, *File > Add Local Repository*, den Ordner `surf-check-portugal` wählen, auf *create a repository* klicken, *Commit to main*, dann *Publish repository* und dabei das Häkchen bei „Keep this code private“ entfernen.
4. **Pages einschalten:** Im Repository auf GitHub *Settings > Pages*, bei *Source* **GitHub Actions** wählen.
5. **Ersten Lauf starten:** Reiter *Actions > Seite aktualisieren > Run workflow*. Nach etwa zwei Minuten steht die Adresse unter *Settings > Pages*, sie sieht so aus: `https://DEIN-NAME.github.io/surf-check-portugal/`. Diesen Link schickst du weiter. Mit `#vagueira` oder `#bordeira` am Ende öffnet die Seite gleich die jeweilige Basis.

Danach läuft alles von selbst. Änderst du etwas in `config/` und lädst es mit GitHub Desktop hoch (*Commit*, dann *Push origin*), baut GitHub die Seite sofort neu.

**Gut zu wissen**

- Die Seite und das Repository sind öffentlich: Jeder, der den Link kennt, kann sie sehen. Es stehen keine Namen darin, die Personen sind nur über ihre Avatare erkennbar.
- GitHub startet geplante Läufe manchmal 10 bis 30 Minuten später.
- Die Zeitumstellung am 25.10.2026 ist eingebaut.
- Ohne Änderungen im Repository pausiert GitHub den Zeitplan nach 60 Tagen. Bis zum Reiseende ist das kein Thema. Danach unter *Actions* einmal auf *Enable* klicken.
- Fällt eine Datenquelle aus, zeigt die Seite einen Hinweis und blendet die betroffenen Zahlen aus. Ist ein ganzer Lauf gescheitert, warnt die Seite im Browser, dass sie veraltet ist (nach 14 Stunden).

## 4. Prüfen, ob alles zusammenpasst

    python3 -m unittest discover -s tests     (dauert etwa 40 Sekunden)
    python3 tools/links_pruefen.py            (prüft alle Links in den Konfigurationsdateien)
    python3 tools/gezeiten_rueckwaertstest.py (prüft die Tide-Korrektur gegen den Pegel)

## Quellen und Lizenzen

Wetter und Wellen: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0, nicht kommerziell). Warnungen, Temperatur und Wassertemperatur: IPMA. Gemessene Pegel: Instituto Hidrográfico (CC BY-NC 4.0). Schriften: Bricolage Grotesque und IBM Plex Sans (SIL Open Font License, Lizenztexte in `vorlage/schriften/`). TOML-Leser `tomli` (MIT, `vendor/`). Die Spot-Angaben stammen aus surf-forecast.com, mondo.surf und thesurfatlas.com, jeweils mit Link am Spot.
