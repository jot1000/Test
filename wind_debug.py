#!/usr/bin/env python3
"""Diagnose: Welche Open-Meteo-Quelle bildet den Wind am Comersee ab?

Vergleicht für den Como-Spot (Seemitte Domaso–Colico) mehrere Quellen/
Modelle über einen Testmonat (Juli 2024, Hochsaison der Breva) und gibt
Kennzahlen aus. Hintergrund: Die Standard-Archiv-API (ERA5-basiert,
~10-25 km Raster) löst thermische Talwinde vermutlich nicht auf ->
0 Kite-Tage. Kandidat für die Lösung: Historical-Forecast-API mit
ICON-CH1/CH2 (1-2 km), Archiv beginnt allerdings erst ~2022-2024.
"""

from __future__ import annotations

import statistics

import requests

import config

SPOT = config.SPOTS["comer"]
TESTS = [
    # (Beschriftung, URL, Zusatzparameter)
    ("Archiv best_match 07/2024", "https://archive-api.open-meteo.com/v1/archive", {}),
    ("Archiv era5_land 07/2024", "https://archive-api.open-meteo.com/v1/archive",
     {"models": "era5_land"}),
    ("Hist-Forecast icon_ch1 07/2024", "https://historical-forecast-api.open-meteo.com/v1/forecast",
     {"models": "meteoswiss_icon_ch1"}),
    ("Hist-Forecast icon_ch2 07/2024", "https://historical-forecast-api.open-meteo.com/v1/forecast",
     {"models": "meteoswiss_icon_ch2"}),
    ("Hist-Forecast icon_d2 07/2024", "https://historical-forecast-api.open-meteo.com/v1/forecast",
     {"models": "icon_d2"}),
    ("Hist-Forecast icon_ch2 07/2022", "https://historical-forecast-api.open-meteo.com/v1/forecast",
     {"models": "meteoswiss_icon_ch2", "start_date": "2022-07-01", "end_date": "2022-07-31"}),
    ("Hist-Forecast icon_d2 07/2022", "https://historical-forecast-api.open-meteo.com/v1/forecast",
     {"models": "icon_d2", "start_date": "2022-07-01", "end_date": "2022-07-31"}),
]


def describe(label: str, url: str, extra: dict) -> None:
    params = {
        "latitude": SPOT["latitude"],
        "longitude": SPOT["longitude"],
        "start_date": "2024-07-01",
        "end_date": "2024-07-31",
        "hourly": "wind_speed_10m",
        "timezone": config.TIMEZONE,
        "wind_speed_unit": "kn",
    }
    params.update(extra)
    try:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()["hourly"]
        pairs = [(t, v) for t, v in zip(data["time"], data["wind_speed_10m"]) if v is not None]
        if not pairs:
            print(f"{label:35s} keine Werte")
            return
        values = [v for _, v in pairs]
        noon = [v for t, v in pairs if 12 <= int(t[11:13]) <= 17]
        print(f"{label:35s} n={len(values):4d}  Mittel={statistics.mean(values):4.1f} kn  "
              f"Max={max(values):4.1f}  Nachmittag-Mittel={statistics.mean(noon):4.1f}  "
              f"Std>=10kn={sum(1 for v in values if v >= 10):3d}")
    except Exception as e:
        print(f"{label:35s} FEHLER: {e}")


def main() -> None:
    print(f"Spot: {SPOT['name']} ({SPOT['latitude']}, {SPOT['longitude']})\n")
    for label, url, extra in TESTS:
        describe(label, url, extra)
    print("\nZum Vergleich Sempachersee (Archiv best_match 07/2024):")
    sem = config.SPOTS["sempach"]
    old_lat, old_lon = SPOT["latitude"], SPOT["longitude"]
    SPOT.update(latitude=sem["latitude"], longitude=sem["longitude"])
    describe("Sempach Archiv 07/2024", "https://archive-api.open-meteo.com/v1/archive", {})
    SPOT.update(latitude=old_lat, longitude=old_lon)


if __name__ == "__main__":
    main()
