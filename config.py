"""Zentrale Konfiguration für die Kite-Wind-Analyse Sempachersee.

Alle fachlichen Konstanten an einem Ort — analyse.py, notify.py und die
Tests importieren von hier. Das Dashboard (index.html) hat einen eigenen,
gleichlautenden CONFIG-Block im <script>-Teil.
"""

# --- Spots ----------------------------------------------------------------
# Mehrere Reviere; analyse.py wird pro Spot aufgerufen (--spot <key>).
# validation_station: MeteoSwiss-SMN-Kürzel oder None (keine Validierung).
SPOTS = {
    "sempach": {
        "name": "Sempachersee (Sempach LU)",
        "latitude": 47.136,
        "longitude": 8.192,
        "stats_file": "stats.json",
        "validation_station": "EGO",
    },
    "comer": {
        "name": "Comersee (Seemitte Domaso–Colico)",
        "latitude": 46.1445,
        "longitude": 9.3505,
        "stats_file": "stats_comer.json",
        "validation_station": None,  # keine freie Messstation in Italien
    },
}

# Haupt-Spot (Benachrichtigung & Standardwerte)
SPOT_NAME = SPOTS["sempach"]["name"]
LATITUDE = SPOTS["sempach"]["latitude"]
LONGITUDE = SPOTS["sempach"]["longitude"]
TIMEZONE = "Europe/Zurich"

# --- Kite-Schwellen (mittlerer Wind in Knoten) ---------------------------
THRESHOLDS_KN = {
    "foil": 10.0,
    "twintip": 12.0,
}

# Mindestdauer eines Kite-Fensters in zusammenhängenden Stunden
MIN_WINDOW_HOURS = 2

# Böigkeits-Faktor (Böe / Mittelwind), ab dem ein Fenster als "böig" gilt
GUSTY_FACTOR = 2.0

# --- Historische Daten (Open-Meteo Archive API) --------------------------
HISTORY_START_YEAR = 2005
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# --- Prognose (Open-Meteo, MeteoSwiss-ICON) ------------------------------
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# ICON-CH1 (1 km, 33 h) mit Fallback auf ICON-CH2 / best_match, s. notify.py
FORECAST_MODELS = "meteoswiss_icon_ch1"
FORECAST_HOURS = 48

# --- MeteoSwiss Open Data (Messstation für Validierung & Live) -----------
# Egolzwil (EGO), nächste SwissMetNet-Station am Sempachersee
METEOSWISS_STATION = "EGO"
METEOSWISS_STAC_COLLECTION = (
    "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-smn"
)
METEOSWISS_DATA_BASE = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn"
# Anzahl Jahre Messdaten für die Modell-Validierung
VALIDATION_YEARS = 5

# --- Dateien --------------------------------------------------------------
CACHE_DIR = "data/cache"
STATS_FILE = "stats.json"

# --- Benachrichtigung ------------------------------------------------------
# Standard-Link zum Dashboard; per Umgebungsvariable DASHBOARD_URL übersteuerbar
DASHBOARD_URL_DEFAULT = "https://example.github.io/kite-sempachersee/"
