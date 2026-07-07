#!/usr/bin/env python3
"""Phase 4 — Tägliche Kite-Benachrichtigung via Telegram.

Prüft die ICON-CH1-Prognose (Open-Meteo) für heute und morgen auf
Kite-Fenster und schickt bei Treffern eine Telegram-Nachricht.
Kein Fenster -> keine Nachricht (kein Spam).

Umgebungsvariablen:
    TELEGRAM_BOT_TOKEN   Bot-Token von @BotFather
    TELEGRAM_CHAT_ID     Ziel-Chat (eigene User-ID oder Gruppen-ID)
    DASHBOARD_URL        optional, Link ans Ende der Nachricht

Aufruf:
    python notify.py                 # prüfen und ggf. senden
    python notify.py --dry-run       # nur ausgeben, nichts senden
    python notify.py --guard-hour 6  # nur ausführen, wenn es lokal 6 Uhr ist
                                     # (für den doppelten UTC-Cron in der Action)
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

import requests

import config
import core
from core import Hour

TZ = ZoneInfo(config.TIMEZONE)


def fetch_forecast() -> dict:
    params = {
        "latitude": config.LATITUDE,
        "longitude": config.LONGITUDE,
        "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
        "daily": "sunrise,sunset",
        "timezone": config.TIMEZONE,
        "wind_speed_unit": "kn",
        "forecast_days": 3,
        "models": config.FORECAST_MODELS,
    }
    r = requests.get(config.OPEN_METEO_FORECAST_URL, params=params, timeout=60)
    if r.status_code == 400:  # ICON-CH1 nicht verfügbar -> Standardmodell
        params.pop("models")
        r = requests.get(config.OPEN_METEO_FORECAST_URL, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def build_hours(data: dict) -> list[Hour]:
    daylight = {}
    d = data["daily"]
    for day, sr, ss in zip(d["time"], d["sunrise"], d["sunset"]):
        daylight[dt.date.fromisoformat(day)] = (
            dt.datetime.fromisoformat(sr),
            dt.datetime.fromisoformat(ss),
        )
    h = data["hourly"]
    hours = []
    for t, speed, gust, direction in zip(
        h["time"], h["wind_speed_10m"], h["wind_gusts_10m"], h["wind_direction_10m"]
    ):
        t = dt.datetime.fromisoformat(t)
        sun = daylight.get(t.date())
        hours.append(
            Hour(
                time=t,
                speed=speed,
                gust=gust,
                direction=direction,
                daylight=bool(sun) and core.hour_is_daylight(t, sun[0], sun[1]),
            )
        )
    return hours


def windows_today_tomorrow(hours: list[Hour]) -> dict[str, list]:
    """Kite-Fenster für heute/morgen pro Schwelle; twintip-Fenster werden
    nicht zusätzlich als foil gemeldet (höchste erfüllte Schwelle zählt)."""
    today = dt.datetime.now(TZ).date()
    result = {}
    for name, thr in sorted(
        config.THRESHOLDS_KN.items(), key=lambda kv: kv[1], reverse=True
    ):
        wins = [
            w
            for w in core.find_windows(
                hours, thr, config.MIN_WINDOW_HOURS, config.GUSTY_FACTOR
            )
            if w.date in (today, today + dt.timedelta(days=1))
        ]
        result[name] = wins
    # foil-Fenster streichen, die von einem twintip-Fenster abgedeckt sind
    if "foil" in result and "twintip" in result:
        tt = [(w.start, w.end) for w in result["twintip"]]
        result["foil"] = [
            w
            for w in result["foil"]
            if not any(s <= w.start and w.end <= e for s, e in tt)
        ]
    return result


def format_message(per_threshold: dict[str, list]) -> str:
    today = dt.datetime.now(TZ).date()
    day_name = {today: "Heute", today + dt.timedelta(days=1): "Morgen"}
    lines = [f"🪁 <b>Kite-Alarm {config.SPOT_NAME}</b>"]
    for name in ("twintip", "foil"):
        for w in per_threshold.get(name, []):
            gusty = " ⚠️ böig" if w.gusty else ""
            gust = f", Böen {w.max_gust:.0f} kn" if w.max_gust is not None else ""
            lines.append(
                f"{day_name[w.date]} {w.start:%H}–{w.end:%H} Uhr: "
                f"Ø {w.mean_speed:.0f} kn{gust}, {w.sector or '?'} "
                f"→ <b>{name}</b> (≥{config.THRESHOLDS_KN[name]:.0f} kn){gusty}"
            )
    url = os.environ.get("DASHBOARD_URL", config.DASHBOARD_URL_DEFAULT)
    lines.append(f'<a href="{url}">Dashboard</a>')
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    r.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--guard-hour",
        type=int,
        default=None,
        help="Nur ausführen, wenn die lokale Stunde (Europe/Zurich) diesem "
        "Wert entspricht. Erlaubt zwei UTC-Crons für Sommer-/Winterzeit.",
    )
    args = parser.parse_args()

    now = dt.datetime.now(TZ)
    if args.guard_hour is not None and now.hour != args.guard_hour:
        print(f"Lokale Zeit {now:%H:%M} — nicht Stunde {args.guard_hour}, überspringe.")
        return 0

    hours = build_hours(fetch_forecast())
    per_threshold = windows_today_tomorrow(hours)
    if not any(per_threshold.values()):
        print("Keine Kite-Fenster für heute/morgen — keine Nachricht.")
        return 0

    message = format_message(per_threshold)
    print(message)
    if not args.dry_run:
        send_telegram(message)
        print("Telegram-Nachricht gesendet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
