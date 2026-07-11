# 🪁 Kite-Wind-Analyse & Dashboard Sempachersee (+ Comersee)

Wann sind die besten Kite-Tage am Sempachersee (Spot Sempach LU)?
Dieses Projekt beantwortet das mit historischen Winddaten seit 2005,
zeigt Live-Wind und 48-h-Prognose in einem Web-Dashboard und schickt
morgens eine Telegram-Nachricht, wenn kitebare Bedingungen prognostiziert
sind.

**Ehrlichkeit vorab:** Der Sempachersee ist ein Leichtwindrevier — erwarte
wenige gute Tage pro Monat, mit Schwerpunkt Frühling sowie West-/Föhn-/
Bisenlagen. Die Analyse weist das aus, sie färbt nichts schön.

## Fachliche Definitionen

| Begriff | Definition |
|---|---|
| Schwelle `foil` | mittlerer Wind ≥ 10 kn |
| Schwelle `twintip` | mittlerer Wind ≥ 12 kn |
| Kite-Fenster | Schwelle während ≥ 2 zusammenhängenden Stunden erreicht, innerhalb Tageslicht (Sonnenauf- bis -untergang) |
| Kite-Tag | Tag mit mindestens einem Kite-Fenster |
| böig | Fenster mit mittlerem Faktor Böe/Mittelwind > 2 (fahrbar, aber unangenehm) |

Windrichtung wird immer miterfasst (16 Sektoren), Anzeige durchgehend in
Knoten, alle Zeiten in Europe/Zürich. Konstanten (Koordinaten, Schwellen,
Mindestdauer, Stations-ID) stehen zentral in [`config.py`](config.py) bzw.
im `CONFIG`-Block von [`index.html`](index.html).

## Datenquellen (alle gratis)

1. **Open-Meteo Historical Weather API** — stündliche Modelldaten für den
   Punkt Sempach ab 2005 (`wind_speed_10m`, `wind_gusts_10m`,
   `wind_direction_10m`). Kein API-Key, nicht-kommerzielle Nutzung.
2. **Open-Meteo Forecast API** mit MeteoSwiss **ICON-CH1** — 48-h-Prognose,
   stündlich (Fallback auf Standardmodell, falls ICON-CH1 nicht verfügbar).
3. **MeteoSwiss Open Data (OGD)** — Messstation **Egolzwil (EGO)** via
   STAC-API auf data.geo.admin.ch. Dient zur Validierung der Modelldaten
   (Stundenwerte) und als Live-Anzeige (10-Minuten-Werte).
   Doku: <https://opendatadocs.meteoswiss.ch>

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Phase 1 — Historische Analyse

```bash
python analyse.py                # Sempachersee, inkl. Validierung gegen Egolzwil
python analyse.py --spot comer   # Comersee -> stats_comer.json
python analyse.py --skip-validation
```

Die Spots sind in `config.py` (`SPOTS`) definiert. Der **Comersee**-Spot
liegt in der Seemitte zwischen Domaso und Colico (Boot-Revier, Alto
Lario); für Italien gibt es keine freie Messstation, deshalb entfällt
dort Validierung und Live-Messung — die «Jetzt»-Karte zeigt die aktuelle
Modellstunde (klar beschriftet). Telegram-Benachrichtigungen gibt es nur
für den Sempachersee.

Lädt die Stundendaten jahresweise und cached sie als Parquet unter
`data/cache/` (beim nächsten Lauf kein erneuter Download; das laufende Jahr
wird höchstens einmal pro Tag neu geladen). Ergebnis ist **`stats.json`**
mit, je Schwelle:

- Kite-Tage pro Monat (Mittel, Streuung, Min/Max über die Jahre)
- Kalendertag-Wahrscheinlichkeit eines Kite-Tags (±3 Tage geglättet) → Heatmap
- Verteilung der Fensterstunden nach Tageszeit (Thermik-Muster)
- Windrose der Kite-Fenster (16 Sektoren)
- Trend: Kite-Tage pro Jahr
- Validierung: Messung vs. Modell (Korrekturfaktor, Kite-Tage pro Jahr beider
  Quellen)

Die Unit-Tests der Kernlogik laufen ohne Abhängigkeiten:

```bash
python -m unittest discover -s tests
```

### Phase 2 & 3 — Kite-Kalender & Dashboard

`index.html` ist eine einzelne statische Seite (Vanilla JS, mobile-first,
deutsch) mit einem **Reiter pro Revier** (Sempachersee / Comersee).
Pro Reiter zeigt sie:

- **Jetzt**: Live-Wind Egolzwil (10-Minuten-Werte) mit Ampel
  kitebar / vielleicht / nein
- **Prognose**: 48 h stündlich, Kite-Fenster grün hervorgehoben,
  Nachtstunden abgedunkelt
- **Kalender**: Jahres-Heatmap (12 Monate × 31 Tage) der
  Kite-Tag-Wahrscheinlichkeit, umschaltbar foil/twintip
- **Statistik**: Monatsbalken mit Min/Max-Spanne + Windrose auf einer
  stilisierten Grundrisskarte des Sempachersees — zentriert am Spot
  Sempach, mit Ortsnamen, Nordpfeil, Massstab, Hinweis auf die
  Messstation Egolzwil und einer auflandig/sideshore/ablandig-
  Klassifikation pro Windsektor (ablandige Sektoren sind mit einem
  gestrichelten Warnbogen markiert; anpassbar über `SPOT_EXPOSURE`
  in `index.html`)

Lokal ansehen (fetch braucht einen HTTP-Server, `file://` genügt nicht):

```bash
python -m http.server 8000   # dann http://localhost:8000
```

**GitHub Pages:** Repo-Settings → Pages → "Deploy from a branch" →
Branch `main`, Ordner `/ (root)`. Da `stats.json` und `index.html` im
Root liegen, ist das Dashboard danach direkt online. Der Workflow
[`update-stats.yml`](.github/workflows/update-stats.yml) erneuert
`stats.json` monatlich (oder manuell via "Run workflow").

### Phase 4 — Tägliche Telegram-Benachrichtigung

1. **Bot anlegen:** In Telegram [@BotFather](https://t.me/BotFather)
   anschreiben → `/newbot` → Namen vergeben → das **Token** notieren.
2. **Chat-ID herausfinden:** Dem neuen Bot eine Nachricht schicken, dann
   `https://api.telegram.org/bot<TOKEN>/getUpdates` im Browser öffnen —
   die `chat.id` aus der Antwort ist die **Chat-ID**.
3. **Secrets setzen:** Repo-Settings → Secrets and variables → Actions:
   - Secret `TELEGRAM_BOT_TOKEN`
   - Secret `TELEGRAM_CHAT_ID`
   - optional Variable `DASHBOARD_URL` (Link in der Nachricht)
4. Fertig — der Workflow
   [`kite-notify.yml`](.github/workflows/kite-notify.yml) prüft täglich um
   **06:30 Europe/Zurich** die Prognose für heute und morgen. Gibt es ein
   Kite-Fenster, kommt eine Nachricht mit Zeitfenster, Wind/Böen in kn,
   Richtung und Schwelle (twintip-Fenster werden nicht doppelt als foil
   gemeldet). Kein Fenster → keine Nachricht.

   Da GitHub-Crons in UTC laufen, sind zwei Cron-Einträge hinterlegt
   (Sommer-/Winterzeit); `--guard-hour 6` sorgt dafür, dass nur der
   passende sendet.

   **Bot testen:** Wird der Workflow manuell gestartet (Actions →
   „Kite-Benachrichtigung" → „Run workflow"), kommt **immer** eine
   Nachricht — ohne Kite-Fenster eine Statusmeldung mit dem höchsten
   prognostizierten Wind (`notify.py --always`). Der tägliche
   6:30-Lauf bleibt spamfrei.

Lokal testen:

```bash
python notify.py --dry-run
```

## Projektstruktur

```
config.py      zentrale Konstanten (Spot, Schwellen, Station, URLs)
core.py        Kernlogik: Fenster-Erkennung, Sektoren, Glättung (nur stdlib)
analyse.py     Phase 1: Download + Cache + Auswertung → stats.json
meteoswiss.py  MeteoSwiss-OGD-Zugriff (STAC-Assets, CSV-Parsing, Einheiten)
notify.py      Phase 4: Prognose prüfen, Telegram senden
index.html     Phase 2+3: Dashboard (eine Datei, Vanilla JS)
tests/         Unit-Tests der Kernlogik
```

## Hinweise & bekannte Punkte

- Die MeteoSwiss-Parameterkurznamen (`fu3010*` = km/h, `fkl010*` = m/s,
  `dkl010*` = Richtung) werden über Kandidatenlisten gesucht
  (`meteoswiss.py`). Sollte MeteoSwiss die Spaltennamen ändern, bricht die
  Validierung mit einer klaren Fehlermeldung ab, die die vorhandenen
  Spalten auflistet — Kandidaten dann dort ergänzen. Die Analyse selbst
  läuft auch ohne Validierung durch (`--skip-validation` bzw. automatischer
  Fallback).
- Die Open-Meteo-Archive-API hinkt der Gegenwart ~5 Tage hinterher.
- Der Korrekturfaktor Messung/Modell steht in `stats.json → validation` und
  wird bewusst nur dokumentiert, nicht automatisch angewendet.

## Offene Punkte / später

- Spot-Ausrichtung: erste Version umgesetzt (Sektor-Klassifikation
  `SPOT_EXPOSURE` in `index.html`, Warnbogen in der Windrose-Karte) —
  Feintuning mit Ortskenntnis offen.
- Optional zweite Schwelle für Starkwind (≥ 16 kn).
- MeteoSwiss plant individuelle API-Abfragen ab ca. Q2 2026 — könnte den
  STAC-Datei-Download vereinfachen.
