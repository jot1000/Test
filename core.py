"""Reine Kernlogik der Kite-Wind-Analyse (nur Standardbibliothek).

Fenster-Erkennung, Windsektoren, Glättung und Statistik-Helfer.
Bewusst ohne pandas/requests, damit die Logik überall (auch im Notifier
und in Unit-Tests) identisch und ohne Abhängigkeiten nutzbar ist.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional, Sequence

# --- Einheiten -------------------------------------------------------------

KN_PER_KMH = 1.0 / 1.852
KN_PER_MS = 3.6 / 1.852


def kmh_to_kn(v: float) -> float:
    return v * KN_PER_KMH


def ms_to_kn(v: float) -> float:
    return v * KN_PER_MS


# --- Windrichtung: 16 Sektoren (deutsche Bezeichnungen, O = Ost) -----------

SECTORS_16 = [
    "N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def direction_to_sector(degrees: float) -> int:
    """Grad (0-360, meteorologisch: woher der Wind kommt) -> Sektorindex 0-15."""
    return int((degrees % 360.0) / 22.5 + 0.5) % 16


def mean_direction(degrees: Iterable[float]) -> Optional[float]:
    """Vektormittel von Windrichtungen in Grad (None bei leerer Eingabe)."""
    xs, ys, n = 0.0, 0.0, 0
    for d in degrees:
        if d is None:
            continue
        r = math.radians(d)
        xs += math.sin(r)
        ys += math.cos(r)
        n += 1
    if n == 0:
        return None
    deg = math.degrees(math.atan2(xs, ys)) % 360.0
    return 0.0 if deg >= 360.0 - 1e-9 else deg


# --- Stundenwerte & Kite-Fenster -------------------------------------------


@dataclass
class Hour:
    """Ein Stundenwert. `time` ist der Stundenbeginn in Lokalzeit,
    `speed`/`gust` in Knoten, `direction` in Grad, `daylight` = Stunde
    überschneidet sich mit Tageslicht (Sonnenauf- bis -untergang)."""

    time: datetime
    speed: Optional[float]
    gust: Optional[float] = None
    direction: Optional[float] = None
    daylight: bool = True


@dataclass
class Window:
    """Ein Kite-Fenster: zusammenhängende Tageslicht-Stunden über der Schwelle."""

    start: datetime
    end: datetime  # exklusiv (Ende der letzten Stunde)
    n_hours: int
    mean_speed: float
    max_gust: Optional[float]
    gust_factor: Optional[float]  # Mittel der stündlichen Faktoren Böe/Wind
    gusty: bool
    direction: Optional[float]  # Vektormittel in Grad
    sector: Optional[str]

    @property
    def date(self):
        return self.start.date()


def hour_is_daylight(hour_start: datetime, sunrise: datetime, sunset: datetime) -> bool:
    """Stunde zählt als Tageslicht, wenn sich [start, start+1h) mit
    [sunrise, sunset] überschneidet."""
    hour_end = hour_start + timedelta(hours=1)
    return hour_end > sunrise and hour_start < sunset


def find_windows(
    hours: Sequence[Hour],
    threshold_kn: float,
    min_hours: int = 2,
    gusty_factor: float = 2.0,
) -> list[Window]:
    """Findet alle Kite-Fenster in einer zeitlich sortierten Stundenreihe.

    Ein Fenster ist eine maximale Folge direkt aufeinanderfolgender
    Tageslicht-Stunden mit Mittelwind >= Schwelle und Länge >= min_hours.
    Datenlücken (Zeitsprung != 1 h) und fehlende Werte beenden eine Folge.
    """
    windows: list[Window] = []
    run: list[Hour] = []

    def flush():
        nonlocal run
        if len(run) >= min_hours:
            speeds = [h.speed for h in run]
            gusts = [h.gust for h in run if h.gust is not None]
            factors = [
                h.gust / h.speed
                for h in run
                if h.gust is not None and h.speed and h.speed > 0
            ]
            gf = sum(factors) / len(factors) if factors else None
            direction = mean_direction(h.direction for h in run)
            windows.append(
                Window(
                    start=run[0].time,
                    end=run[-1].time + timedelta(hours=1),
                    n_hours=len(run),
                    mean_speed=sum(speeds) / len(speeds),
                    max_gust=max(gusts) if gusts else None,
                    gust_factor=gf,
                    gusty=gf is not None and gf > gusty_factor,
                    direction=direction,
                    sector=SECTORS_16[direction_to_sector(direction)]
                    if direction is not None
                    else None,
                )
            )
        run = []

    prev_time: Optional[datetime] = None
    for h in hours:
        contiguous = prev_time is not None and h.time - prev_time == timedelta(hours=1)
        qualifies = h.daylight and h.speed is not None and h.speed >= threshold_kn
        if qualifies:
            if run and not contiguous:
                flush()
            run.append(h)
        else:
            flush()
        prev_time = h.time
    flush()
    return windows


def kite_days(windows: Iterable[Window]) -> set:
    """Menge der Kalendertage (date) mit mindestens einem Kite-Fenster."""
    return {w.date for w in windows}


# --- Statistik-Helfer -------------------------------------------------------

# Kalendertage eines Schaltjahres als (Monat, Tag)-Schlüssel, 366 Einträge
def calendar_days() -> list[tuple[int, int]]:
    days_in_month = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return [(m + 1, d + 1) for m in range(12) for d in range(days_in_month[m])]


def smooth_circular(values: Sequence[float], radius: int = 3) -> list[float]:
    """Gleitendes Mittel über +-radius Positionen, zyklisch (Jahreswechsel)."""
    n = len(values)
    if n == 0:
        return []
    out = []
    width = 2 * radius + 1
    for i in range(n):
        s = sum(values[(i + k) % n] for k in range(-radius, radius + 1))
        out.append(s / width)
    return out


def mean_std(values: Sequence[float]) -> tuple[float, float]:
    """Mittelwert und (Populations-)Standardabweichung; (0, 0) bei leer."""
    if not values:
        return 0.0, 0.0
    m = sum(values) / len(values)
    var = sum((v - m) ** 2 for v in values) / len(values)
    return m, math.sqrt(var)
