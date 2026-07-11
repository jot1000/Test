"""Zugriff auf MeteoSwiss Open Data (OGD) für die SwissMetNet-Station.

Datenquelle: https://data.geo.admin.ch, Collection ch.meteoschweiz.ogd-smn.
Die CSV-Dateien pro Station sind nach Granularität und Zeitraum aufgeteilt,
z.B. ogd-smn_ego_h_historical_2020-2029.csv (Stundenwerte) oder
ogd-smn_ego_t_now.csv (10-Minuten-Werte, live).

Die Parameter-Kurznamen sind je nach Einheit unterschiedlich benannt
(fu3* = km/h, fkl* = m/s); wir suchen deshalb über Kandidatenlisten und
rechnen entsprechend nach Knoten um. Doku: https://opendatadocs.meteoswiss.ch
"""

from __future__ import annotations

import io
import logging

import pandas as pd
import requests

import config
from core import kmh_to_kn, ms_to_kn

log = logging.getLogger(__name__)

# Kandidaten (in Präferenz-Reihenfolge) für die Stundenwerte.
# Suffix h0/h1 = Stundenaggregat, z0/z1 = 10-Minuten-Wert.
SPEED_CANDIDATES_H = ["fu3010h0", "fkl010h0", "fu3010h1", "fkl010h1"]
GUST_CANDIDATES_H = ["fu3010h3", "fkl010h3", "fu3010h1", "fkl010h1"]
DIR_CANDIDATES_H = ["dkl010h0"]

# Kandidaten für die 10-Minuten-Werte (Live-Anzeige, im Dashboard genutzt).
SPEED_CANDIDATES_T = ["fu3010z0", "fkl010z0"]
GUST_CANDIDATES_T = ["fu3010z1", "fkl010z1"]
DIR_CANDIDATES_T = ["dkl010z0"]


def _to_kn(series: pd.Series, shortname: str) -> pd.Series:
    """Parameterwert -> Knoten anhand des Kurznamen-Präfixes (fu3=km/h, fkl=m/s)."""
    values = pd.to_numeric(series, errors="coerce")
    if shortname.startswith("fu3"):
        return values.map(lambda v: kmh_to_kn(v) if pd.notna(v) else None)
    if shortname.startswith("fkl"):
        return values.map(lambda v: ms_to_kn(v) if pd.notna(v) else None)
    raise ValueError(f"Unbekanntes Einheiten-Präfix für Parameter {shortname!r}")


def _pick(columns, candidates, what: str) -> str:
    for c in candidates:
        if c in columns:
            return c
    raise KeyError(
        f"Kein Parameter für {what} gefunden. Kandidaten: {candidates}, "
        f"vorhandene Spalten: {sorted(columns)}"
    )


def _station_asset_hrefs(station: str, session: requests.Session) -> list[str]:
    """Alle Asset-URLs des Stations-Items aus der STAC-API."""
    url = f"{config.METEOSWISS_STAC_COLLECTION}/items/{station.lower()}"
    r = session.get(url, timeout=60)
    r.raise_for_status()
    assets = r.json().get("assets", {})
    return [a["href"] for a in assets.values() if "href" in a]


def _read_ogd_csv(url: str, session: requests.Session) -> pd.DataFrame:
    r = session.get(url, timeout=300)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), sep=";")
    df.columns = [c.strip().lower() for c in df.columns]
    ts_col = "reference_timestamp"
    if ts_col not in df.columns:
        raise KeyError(f"Spalte {ts_col!r} fehlt in {url} (Spalten: {list(df.columns)})")
    # OGD-Zeitstempel sind UTC im Format TT.MM.JJJJ HH:MM
    df["time_utc"] = pd.to_datetime(df[ts_col], format="%d.%m.%Y %H:%M", utc=True)
    return df


def load_hourly(station: str, start_year: int, end_year: int) -> pd.DataFrame:
    """Stundenwerte der Station als DataFrame mit Spalten
    time (Lokalzeit Europe/Zurich, Stundenbeginn), speed_kn, gust_kn, dir_deg.
    """
    session = requests.Session()
    hrefs = _station_asset_hrefs(station, session)
    hourly = [
        h
        for h in hrefs
        if "_h_" in h and ("historical" in h or "recent" in h) and h.endswith(".csv")
    ]
    if not hourly:
        raise RuntimeError(
            f"Keine Stunden-CSVs für Station {station} gefunden (Assets: {hrefs})"
        )

    frames = []
    for href in sorted(hourly):
        # Dekaden-Dateien ausserhalb des Zeitraums gar nicht erst laden
        decade = [int(p) for p in href.replace(".csv", "").split("_")[-1].split("-") if p.isdigit()]
        if len(decade) == 2 and (decade[1] < start_year or decade[0] > end_year):
            continue
        log.info("Lade %s", href)
        frames.append(_read_ogd_csv(href, session))
    df = pd.concat(frames, ignore_index=True)

    speed_col = _pick(df.columns, SPEED_CANDIDATES_H, "Windgeschwindigkeit (h)")
    gust_col = None
    try:
        gust_col = _pick(df.columns, GUST_CANDIDATES_H, "Böenspitze (h)")
        if gust_col == speed_col:
            gust_col = None
    except KeyError:
        log.warning("Keine Böen-Spalte gefunden — Böigkeit ohne Messdaten")
    dir_col = None
    try:
        dir_col = _pick(df.columns, DIR_CANDIDATES_H, "Windrichtung (h)")
    except KeyError:
        log.warning("Keine Richtungs-Spalte gefunden")

    out = pd.DataFrame(
        {
            "time": df["time_utc"].dt.tz_convert(config.TIMEZONE).dt.tz_localize(None),
            "speed_kn": _to_kn(df[speed_col], speed_col),
            "gust_kn": _to_kn(df[gust_col], gust_col) if gust_col else None,
            "dir_deg": pd.to_numeric(df[dir_col], errors="coerce") if dir_col else None,
        }
    )
    out = out[(out["time"].dt.year >= start_year) & (out["time"].dt.year <= end_year)]
    return out.sort_values("time").drop_duplicates(subset="time").reset_index(drop=True)
