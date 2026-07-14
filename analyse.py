#!/usr/bin/env python3
"""Phase 1 — Historische Kite-Wind-Analyse für den Sempachersee.

Lädt stündliche Modelldaten (Open-Meteo Historical API) ab 2005, erkennt
Kite-Fenster/-Tage pro Schwelle (foil/twintip), validiert gegen die
MeteoSwiss-Messstation Egolzwil und exportiert alles als stats.json
für das Dashboard.

Aufruf:
    python analyse.py                  # Sempachersee inkl. Validierung
    python analyse.py --spot comer     # Comersee (ohne Validierung)
    python analyse.py --skip-validation
    python analyse.py --start-year 2010 --output stats.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests

import config
import core
from core import Hour, SECTORS_16

log = logging.getLogger("analyse")

CACHE = Path(config.CACHE_DIR)


# --------------------------------------------------------------------------
# Datenbeschaffung (mit lokalem Cache, damit nicht bei jedem Lauf neu geladen)
# --------------------------------------------------------------------------


def _get_json(url: str, params: dict, retries: int = 4) -> dict:
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=120)
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == retries:
                raise
            log.warning("Anfrage fehlgeschlagen, neuer Versuch in %.0f s", delay)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def _cache_paths(spot_key: str, spot: dict, year: int) -> tuple[Path, Path]:
    # Sempach behält die alten Dateinamen, damit bestehende Caches gültig
    # bleiben; sonst gehört das Quellmodell in den Namen, damit ein
    # Quellenwechsel alte Cache-Dateien automatisch ungültig macht.
    if spot_key == "sempach":
        prefix = "openmeteo"
    else:
        prefix = f"openmeteo_{spot_key}_{spot.get('history_models') or 'best'}"
    return (
        CACHE / f"{prefix}_hourly_{year}.parquet",
        CACHE / f"{prefix}_daily_{year}.parquet",
    )


def _read_cache(path: Path) -> pd.DataFrame | None:
    for p in (path, path.with_suffix(".csv")):
        if p.exists():
            try:
                if p.suffix == ".parquet":
                    return pd.read_parquet(p)
                return pd.read_csv(p, parse_dates=["time"])
            except Exception as e:  # defekter Cache -> neu laden
                log.warning("Cache %s unlesbar (%s), lade neu", p, e)
    return None


def _write_cache(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
    except Exception:  # pyarrow fehlt -> CSV-Fallback
        df.to_csv(path.with_suffix(".csv"), index=False)


def fetch_openmeteo_year(
    spot_key: str, spot: dict, year: int, today: dt.date
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stunden- und Tageswerte (Sonnenauf-/-untergang) eines Jahres,
    Wind direkt in Knoten, Zeiten lokal (Europe/Zurich)."""
    hourly_path, daily_path = _cache_paths(spot_key, spot, year)
    cached_h, cached_d = _read_cache(hourly_path), _read_cache(daily_path)
    is_past_year = year < today.year
    if cached_h is not None and cached_d is not None:
        # Vergangene Jahre sind final; das laufende Jahr nur 1x pro Tag laden
        fresh = dt.date.fromtimestamp(hourly_path.stat().st_mtime) == today
        if is_past_year or fresh:
            return cached_h, cached_d

    start = f"{year}-01-01"
    # Archive-API hinkt ~5 Tage hinterher
    end_date = min(dt.date(year, 12, 31), today - dt.timedelta(days=6))
    if end_date < dt.date(year, 1, 1):
        return pd.DataFrame(), pd.DataFrame()
    log.info("Lade Open-Meteo %s bis %s", start, end_date)
    params = {
        "latitude": spot["latitude"],
        "longitude": spot["longitude"],
        "start_date": start,
        "end_date": end_date.isoformat(),
        "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
        "daily": "sunrise,sunset",
        "timezone": config.TIMEZONE,
        "wind_speed_unit": "kn",
    }
    if spot.get("history_models"):
        params["models"] = spot["history_models"]
    data = _get_json(spot["history_url"], params)
    h = data["hourly"]
    hourly = pd.DataFrame(
        {
            "time": pd.to_datetime(h["time"]),
            "speed_kn": h["wind_speed_10m"],
            "gust_kn": h["wind_gusts_10m"],
            "dir_deg": h["wind_direction_10m"],
        }
    )
    # Modellarchive liefern vor Archivbeginn Null-Werte -> verwerfen, damit
    # die Monats-Abdeckung (covered months) nicht verfälscht wird
    hourly = hourly.dropna(subset=["speed_kn"]).reset_index(drop=True)
    d = data["daily"]
    daily = pd.DataFrame(
        {
            "date": pd.to_datetime(d["time"]),
            "sunrise": pd.to_datetime(d["sunrise"]),
            "sunset": pd.to_datetime(d["sunset"]),
        }
    )
    _write_cache(hourly, hourly_path)
    _write_cache(daily, daily_path)
    return hourly, daily


def load_history(
    spot_key: str, spot: dict, start_year: int, today: dt.date
) -> tuple[pd.DataFrame, pd.DataFrame]:
    hs, ds = [], []
    for year in range(start_year, today.year + 1):
        h, d = fetch_openmeteo_year(spot_key, spot, year, today)
        if not h.empty:
            hs.append(h)
            ds.append(d)
    hourly = pd.concat(hs, ignore_index=True).sort_values("time")
    daily = pd.concat(ds, ignore_index=True).sort_values("date")
    return hourly, daily


# --------------------------------------------------------------------------
# Aufbereitung & Statistik
# --------------------------------------------------------------------------


def daylight_table(daily: pd.DataFrame) -> dict:
    """date -> (sunrise, sunset) als naive Lokalzeit-Datetimes."""
    return {
        row.date.date(): (row.sunrise.to_pydatetime(), row.sunset.to_pydatetime())
        for row in daily.itertuples()
    }


def build_hours(hourly: pd.DataFrame, daylight: dict) -> list[Hour]:
    hours = []
    for row in hourly.itertuples():
        t = row.time.to_pydatetime()
        sun = daylight.get(t.date())
        is_day = core.hour_is_daylight(t, sun[0], sun[1]) if sun else False
        hours.append(
            Hour(
                time=t,
                speed=None if pd.isna(row.speed_kn) else float(row.speed_kn),
                gust=None if pd.isna(row.gust_kn) else float(row.gust_kn),
                direction=None if pd.isna(row.dir_deg) else float(row.dir_deg),
                daylight=is_day,
            )
        )
    return hours


def _covered_months(hours: list[Hour]) -> set[tuple[int, int]]:
    """(Jahr, Monat)-Paare, die vollständig im Datenbereich liegen."""
    if not hours:
        return set()
    first, last = hours[0].time.date(), hours[-1].time.date()
    covered = set()
    y, m = first.year, first.month
    if first.day > 1:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    while (y, m) <= (last.year, last.month):
        next_start = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
        if next_start - dt.timedelta(days=1) <= last:
            covered.add((y, m))
        y, m = next_start.year, next_start.month
    return covered


def threshold_stats(hours: list[Hour], threshold_kn: float) -> dict:
    """Alle Auswertungen für eine Schwelle."""
    windows = core.find_windows(
        hours, threshold_kn, config.MIN_WINDOW_HOURS, config.GUSTY_FACTOR
    )
    days = core.kite_days(windows)
    covered = _covered_months(hours)
    years_covered = sorted({y for y, _ in covered})
    full_years = [y for y in years_covered if sum(1 for yy, _ in covered if yy == y) == 12]

    # Kite-Tage pro (Jahr, Monat)
    per_ym = defaultdict(int)
    for d in days:
        per_ym[(d.year, d.month)] += 1

    months = []
    for m in range(1, 13):
        years_for_month = sorted(y for (y, mm) in covered if mm == m)
        counts = [per_ym.get((y, m), 0) for y in years_for_month]
        mean, std = core.mean_std(counts)
        months.append(
            {
                "month": m,
                "mean": round(mean, 2),
                "std": round(std, 2),
                "min": min(counts) if counts else 0,
                "max": max(counts) if counts else 0,
                "n_years": len(counts),
            }
        )

    # Kalender: P(Kite-Tag) pro Kalendertag, gemittelt über Jahre, geglättet ±3 Tage
    day_keys = core.calendar_days()
    kite_md = defaultdict(int)
    for d in days:
        kite_md[(d.month, d.day)] += 1
    sample_md = defaultdict(int)
    for h in hours:
        if h.time.hour == 12:  # 1 Zählung pro vorhandenem Datentag
            d = h.time.date()
            sample_md[(d.month, d.day)] += 1
    raw = [
        kite_md[k] / sample_md[k] if sample_md.get(k) else 0.0 for k in day_keys
    ]
    smoothed = core.smooth_circular(raw, radius=3)
    calendar = [
        {"m": k[0], "d": k[1], "p": round(p, 4)} for k, p in zip(day_keys, smoothed)
    ]

    # Tageszeit-Verteilung der Fensterstunden (Thermik-Muster)
    hour_counts = [0] * 24
    sector_counts = [0] * 16
    for w in windows:
        t = w.start
        while t < w.end:
            hour_counts[t.hour] += 1
            t += dt.timedelta(hours=1)
        if w.direction is not None:
            sector_counts[core.direction_to_sector(w.direction)] += w.n_hours

    # Trend: Kite-Tage pro vollständigem Jahr
    per_year = defaultdict(int)
    for d in days:
        per_year[d.year] += 1
    years = [{"year": y, "days": per_year.get(y, 0)} for y in full_years]

    gusty_windows = sum(1 for w in windows if w.gusty)
    return {
        "threshold_kn": threshold_kn,
        "n_windows": len(windows),
        "n_kite_days": len(days),
        "gusty_share": round(gusty_windows / len(windows), 3) if windows else 0.0,
        "mean_window_hours": round(
            sum(w.n_hours for w in windows) / len(windows), 2
        ) if windows else 0.0,
        "months": months,
        "calendar": calendar,
        "hours_of_day": hour_counts,
        "windrose": sector_counts,
        "sectors": SECTORS_16,
        "years": years,
    }


# --------------------------------------------------------------------------
# Validierung gegen Messstation Egolzwil
# --------------------------------------------------------------------------


def validate_against_station(
    model_hourly: pd.DataFrame, daylight: dict, today: dt.date,
    station_id: str = config.METEOSWISS_STATION,
    trend_start_year: int = config.HISTORY_START_YEAR,
) -> tuple[dict, list[Hour]]:
    """Vergleich Modell vs. Messstation.

    Korrekturfaktoren aus den letzten VALIDATION_YEARS (aktuelle Sensorik),
    Kite-Tage pro Jahr dagegen über die volle Periode ab trend_start_year —
    als Gegenprobe, ob Trends im Modell auch in den Messdaten stecken.
    Gibt zusätzlich die Stations-Stundenreihe zurück (für die
    Messdaten-Statistik).
    """
    import meteoswiss

    end_year = today.year - 1
    factor_start = end_year - config.VALIDATION_YEARS + 1
    station = meteoswiss.load_hourly(station_id, trend_start_year, end_year)

    model = model_hourly[
        (model_hourly["time"].dt.year >= trend_start_year)
        & (model_hourly["time"].dt.year <= end_year)
    ]
    merged = model.merge(station, on="time", suffixes=("_model", "_station")).dropna(
        subset=["speed_kn_model", "speed_kn_station"]
    )
    if merged.empty:
        raise RuntimeError("Keine überlappenden Stunden Modell/Station")

    recent = merged[merged["time"].dt.year >= factor_start]
    mean_model = float(recent["speed_kn_model"].mean())
    mean_station = float(recent["speed_kn_station"].mean())
    # Für Kite-Fragen relevanter: Verhältnis bei nennenswertem Wind
    windy = recent[recent["speed_kn_model"] >= 8.0]
    ratio_windy = (
        float(windy["speed_kn_station"].mean() / windy["speed_kn_model"].mean())
        if len(windy)
        else None
    )

    result = {
        "station": station_id,
        "period": f"{factor_start}-{end_year}",
        "trend_period": f"{int(station['time'].dt.year.min())}-{end_year}",
        "n_hours_matched": int(len(merged)),
        "mean_wind_model_kn": round(mean_model, 2),
        "mean_wind_station_kn": round(mean_station, 2),
        "correction_factor": round(mean_station / mean_model, 3),
        "correction_factor_windy": round(ratio_windy, 3) if ratio_windy else None,
        "kite_days_per_year": {},
    }

    # Kite-Tage pro Jahr über die volle Periode, Modell vs. Messung
    first_station_year = int(station["time"].dt.year.min())
    station_hours = build_hours(station, daylight)
    model_hours = build_hours(model, daylight)
    for name, thr in config.THRESHOLDS_KN.items():
        per_year = {}
        for label, hrs in (("model", model_hours), ("station", station_hours)):
            days = core.kite_days(
                core.find_windows(hrs, thr, config.MIN_WINDOW_HOURS)
            )
            counts = defaultdict(int)
            for d in days:
                counts[d.year] += 1
            per_year[label] = {
                str(y): counts.get(y, 0)
                for y in range(max(trend_start_year, first_station_year), end_year + 1)
            }
        result["kite_days_per_year"][name] = per_year
    return result, station_hours


def corrected_stats(hours: list[Hour], factor: float) -> dict:
    """Statistik-Variante mit messkorrigiertem Modellwind (Wind und Böen
    mit dem Validierungsfaktor skaliert, Fenster neu gezählt)."""
    scaled = [
        Hour(
            time=h.time,
            speed=None if h.speed is None else h.speed * factor,
            gust=None if h.gust is None else h.gust * factor,
            direction=h.direction,
            daylight=h.daylight,
        )
        for h in hours
    ]
    out = {"factor": round(factor, 3)}
    for name, thr in config.THRESHOLDS_KN.items():
        out[name] = threshold_stats(scaled, thr)
    return out


# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spot", choices=sorted(config.SPOTS), default="sempach")
    parser.add_argument("--start-year", type=int, default=None,
                        help="Startjahr (Standard: history_start des Spots)")
    parser.add_argument("--output", default=None,
                        help="Zieldatei (Standard: stats_file des Spots)")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    spot = config.SPOTS[args.spot]
    output = args.output or spot["stats_file"]
    log.info("Spot: %s", spot["name"])

    today = dt.date.today()
    start_year = args.start_year or spot["history_start"]
    hourly, daily = load_history(args.spot, spot, start_year, today)
    daylight = daylight_table(daily)
    hours = build_hours(hourly, daylight)
    log.info("%d Stundenwerte von %s bis %s", len(hours), hours[0].time, hours[-1].time)

    station = spot["validation_station"]
    stats = {
        "meta": {
            "spot": spot["name"],
            "latitude": spot["latitude"],
            "longitude": spot["longitude"],
            "timezone": config.TIMEZONE,
            "period": f"{hours[0].time.date()} – {hours[-1].time.date()}",
            "min_window_hours": config.MIN_WINDOW_HOURS,
            "gusty_factor": config.GUSTY_FACTOR,
            "unit": "kn",
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "source": spot["history_source"]
            + (f", MeteoSwiss OGD {station} (Validierung)" if station else ""),
        },
        "thresholds": config.THRESHOLDS_KN,
    }
    for name, thr in config.THRESHOLDS_KN.items():
        log.info("Auswertung Schwelle %s (>= %.0f kn)", name, thr)
        stats[name] = threshold_stats(hours, thr)

    if station and not args.skip_validation:
        try:
            stats["validation"], station_hours = validate_against_station(
                hourly, daylight, today, station, trend_start_year=start_year
            )
            factor = (
                stats["validation"].get("correction_factor_windy")
                or stats["validation"].get("correction_factor")
            )
            if factor:
                log.info("Rechne messkorrigierte Variante (Faktor %.3f)", factor)
                stats["corrected"] = corrected_stats(hours, factor)
            # Dritte Ansicht: Statistik direkt aus den Messdaten der Station
            log.info("Rechne Messdaten-Statistik (%d Stationsstunden)", len(station_hours))
            measured = {
                "station": station,
                "period": f"{station_hours[0].time.date()} – {station_hours[-1].time.date()}",
            }
            for name, thr in config.THRESHOLDS_KN.items():
                measured[name] = threshold_stats(station_hours, thr)
            stats["measured"] = measured
        except Exception as e:
            log.warning("Validierung fehlgeschlagen (%s) — Ausgabe ohne Validierung", e)
            stats["validation"] = {"error": str(e)}

    Path(output).write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log.info("Geschrieben: %s", output)
    for name in config.THRESHOLDS_KN:
        s = stats[name]
        log.info(
            "%s: %d Kite-Tage in %d Fenstern (Ø %.1f h, %d%% böig)",
            name, s["n_kite_days"], s["n_windows"],
            s["mean_window_hours"], round(s["gusty_share"] * 100),
        )


if __name__ == "__main__":
    main()
