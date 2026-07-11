#!/usr/bin/env python3
"""Sondierung: Gibt es brauchbare ARPA-Lombardia-Windsensoren am Comersee?

ARPA Lombardia publiziert Messdaten als Open Data auf dati.lombardia.it
(Socrata-API, ohne API-Key nutzbar). Dieses Skript sucht Wind-Sensoren
in der Nähe des Como-Spots (Seemitte Domaso–Colico), listet sie mit
Distanz auf und holt für die nächstgelegenen den jüngsten Messwert —
daraus lässt sich ablesen, ob eine Station als Live-Quelle fürs
Dashboard taugt (Aktualität!).

Aufruf (lokal oder via GitHub-Workflow "ARPA-Sondierung"):
    python arpa_probe.py
    python arpa_probe.py --radius 30
    python arpa_probe.py --registry nf78-nj6b --data 647i-nhxk

Die Socrata-Dataset-IDs können sich ändern; die Standardwerte sind die
bekannten IDs für "Stazioni Meteorologiche" (Sensor-Register) und
"Dati sensori meteo" (Messwerte). Schlägt eine ID fehl, auf
https://www.dati.lombardia.it nach "sensori meteo" suchen und die IDs
per Argument übergeben.
"""

from __future__ import annotations

import argparse
import math
import sys

import requests

import config

BASE = "https://www.dati.lombardia.it/resource"
# Kandidaten für Dataset-IDs (erste funktionierende gewinnt)
REGISTRY_CANDIDATES = ["nf78-nj6b"]   # Sensor-Register (Stationen + Sensortyp)
DATA_CANDIDATES = ["647i-nhxk"]       # Messwerte (idsensore, data, valore)

SPOT = config.SPOTS["comer"]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def get_json(dataset: str, params: dict) -> list:
    r = requests.get(f"{BASE}/{dataset}.json", params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def latest_value_params(sensor_id: str, days: int = 7) -> dict:
    """Jüngster Messwert eines Sensors. Wichtig: Datumsfilter, sonst
    sortiert Socrata den kompletten Jahresdatensatz -> Timeout."""
    import datetime as dt

    since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    return {
        "$where": f"idsensore='{sensor_id}' AND data >= '{since}'",
        "$order": "data DESC",
        "$limit": 1,
    }


def try_candidates(candidates: list[str], params: dict, what: str) -> tuple[str, list]:
    last_error = None
    for ds in candidates:
        try:
            rows = get_json(ds, params)
            print(f"[OK] {what}: Dataset {ds} liefert {len(rows)} Zeilen")
            return ds, rows
        except Exception as e:
            last_error = e
            print(f"[!!] {what}: Dataset {ds} fehlgeschlagen ({e})")
    raise SystemExit(
        f"Kein {what}-Dataset erreichbar (zuletzt: {last_error}). "
        "Auf https://www.dati.lombardia.it nach 'sensori meteo' suchen und "
        "die ID per --registry/--data übergeben."
    )


def sensor_latlon(row: dict) -> tuple[float, float] | None:
    """Koordinaten aus dem Registereintrag ziehen (Feldnamen variieren)."""
    for lat_key, lon_key in (("lat", "lng"), ("wgs84_nord", "wgs84_est")):
        try:
            lat, lon = float(row[lat_key]), float(row[lon_key])
            if 44 < lat < 47.5 and 8 < lon < 12:
                return lat, lon
        except (KeyError, TypeError, ValueError):
            continue
    # Socrata-"location"-Spalte (verschachtelt)
    loc = row.get("location") or {}
    try:
        return float(loc["latitude"]), float(loc["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--radius", type=float, default=25.0, help="Suchradius in km")
    parser.add_argument("--registry", default=None, help="Socrata-ID Sensor-Register")
    parser.add_argument("--data", default=None, help="Socrata-ID Messwerte")
    parser.add_argument("--max-probe", type=int, default=12,
                        help="Für so viele nächste Sensoren den letzten Wert holen")
    args = parser.parse_args()

    registry_ids = [args.registry] if args.registry else REGISTRY_CANDIDATES
    data_ids = [args.data] if args.data else DATA_CANDIDATES

    print(f"Spot: {SPOT['name']} ({SPOT['latitude']}, {SPOT['longitude']})")
    print(f"Suche Windsensoren im Umkreis von {args.radius:.0f} km …\n")

    _, sensors = try_candidates(registry_ids, {"$limit": 50000}, "Sensor-Register")

    wind = []
    for row in sensors:
        tipo = str(row.get("tipologia", "")).lower()
        if "vento" not in tipo:  # Velocità/Direzione Vento
            continue
        pos = sensor_latlon(row)
        if not pos:
            continue
        d = haversine_km(SPOT["latitude"], SPOT["longitude"], pos[0], pos[1])
        if d <= args.radius:
            wind.append({
                "idsensore": row.get("idsensore"),
                "tipo": row.get("tipologia"),
                "einheit": row.get("unit_dimisura") or row.get("unitadimisura") or "?",
                "station": row.get("nomestazione", "?"),
                "quota": row.get("quota", "?"),
                "aktiv_bis": row.get("datastop") or "aktiv",
                "lat": pos[0], "lon": pos[1], "dist": d,
            })

    if not wind:
        print("Keine Windsensoren im Radius gefunden. Radius erhöhen (--radius 40)?")
        return 0

    wind.sort(key=lambda s: s["dist"])
    print(f"\n{len(wind)} Windsensoren im Radius:\n")
    print(f"{'km':>5}  {'Sensor':>8}  {'Typ':<18} {'Einheit':<8} {'bis':<12} Station (Höhe)")
    for s in wind:
        print(f"{s['dist']:5.1f}  {str(s['idsensore']):>8}  {str(s['tipo'])[:18]:<18} "
              f"{str(s['einheit']):<8} {str(s['aktiv_bis'])[:10]:<12} "
              f"{s['station']} ({s['quota']} m)")

    print(f"\nJüngste Messwerte der {args.max_probe} nächsten Sensoren "
          "(entscheidend ist die Aktualität des Zeitstempels!):\n")
    data_ds = None
    for s in wind[: args.max_probe]:
        params = latest_value_params(str(s["idsensore"]))
        try:
            if data_ds is None:
                # Kandidaten sanft durchprobieren (nicht fatal bei Fehlschlag)
                for ds in data_ids:
                    try:
                        rows = get_json(ds, params)
                        data_ds = ds
                        break
                    except Exception as e:
                        print(f"[!!] Messwerte-Dataset {ds}: {e}")
                if data_ds is None:
                    print("Kein Messwerte-Dataset erreichbar — nur Registerdaten oben.")
                    break
            else:
                rows = get_json(data_ds, params)
            if rows:
                r0 = rows[0]
                print(f"  Sensor {s['idsensore']} ({s['station']}, {s['tipo']}): "
                      f"{r0.get('valore')} {s['einheit']} am {r0.get('data')} "
                      f"(Status {r0.get('stato', '?')})")
            else:
                print(f"  Sensor {s['idsensore']} ({s['station']}): keine Messwerte "
                      "in den letzten 7 Tagen")
        except Exception as e:
            print(f"  Sensor {s['idsensore']} ({s['station']}): Abfrage fehlgeschlagen ({e})")

    print("\nInterpretation: Ein Sensor taugt als Live-Quelle, wenn (a) Typ "
          "'Velocità Vento' UND idealerweise ein Schwester-Sensor 'Direzione "
          "Vento' an derselben Station existiert, (b) der Zeitstempel oben "
          "höchstens wenige Stunden alt ist und (c) die Distanz klein ist "
          "(Gera Lario/Colico/Dongo wären ideal).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
