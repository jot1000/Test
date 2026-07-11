"""Unit-Tests für die Kernlogik (reine Standardbibliothek, via unittest)."""

import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core
from core import Hour, find_windows, hour_is_daylight


def hours_from_speeds(speeds, start=datetime(2024, 5, 1, 8), **kwargs):
    return [
        Hour(time=start + timedelta(hours=i), speed=s, **kwargs)
        for i, s in enumerate(speeds)
    ]


class TestUnits(unittest.TestCase):
    def test_kmh_to_kn(self):
        self.assertAlmostEqual(core.kmh_to_kn(1.852), 1.0)

    def test_ms_to_kn(self):
        self.assertAlmostEqual(core.ms_to_kn(10.0), 19.438, places=2)


class TestSectors(unittest.TestCase):
    def test_cardinals(self):
        self.assertEqual(core.SECTORS_16[core.direction_to_sector(0)], "N")
        self.assertEqual(core.SECTORS_16[core.direction_to_sector(90)], "O")
        self.assertEqual(core.SECTORS_16[core.direction_to_sector(180)], "S")
        self.assertEqual(core.SECTORS_16[core.direction_to_sector(270)], "W")

    def test_sector_boundaries(self):
        # 11.25 ist die Grenze N/NNO; knapp darunter noch N
        self.assertEqual(core.direction_to_sector(11.24), 0)
        self.assertEqual(core.direction_to_sector(11.26), 1)
        # 348.75..360 wickelt zurück auf N
        self.assertEqual(core.direction_to_sector(349), 0)
        self.assertEqual(core.direction_to_sector(360), 0)

    def test_mean_direction_wraparound(self):
        # 350° und 10° mitteln sich zu 0°, nicht zu 180°
        m = core.mean_direction([350, 10])
        self.assertAlmostEqual(m, 0.0, places=6)

    def test_mean_direction_empty(self):
        self.assertIsNone(core.mean_direction([]))
        self.assertIsNone(core.mean_direction([None, None]))


class TestDaylight(unittest.TestCase):
    def test_overlap(self):
        sunrise = datetime(2024, 5, 1, 6, 10)
        sunset = datetime(2024, 5, 1, 20, 40)
        # Stunde 05:00-06:00 endet vor Sonnenaufgang -> Nacht
        self.assertFalse(hour_is_daylight(datetime(2024, 5, 1, 5), sunrise, sunset))
        # Stunde 06:00-07:00 überschneidet Sonnenaufgang -> Tageslicht
        self.assertTrue(hour_is_daylight(datetime(2024, 5, 1, 6), sunrise, sunset))
        # Stunde 20:00-21:00 überschneidet Sonnenuntergang -> Tageslicht
        self.assertTrue(hour_is_daylight(datetime(2024, 5, 1, 20), sunrise, sunset))
        # Stunde 21:00-22:00 liegt komplett danach -> Nacht
        self.assertFalse(hour_is_daylight(datetime(2024, 5, 1, 21), sunrise, sunset))


class TestFindWindows(unittest.TestCase):
    def test_simple_window(self):
        hours = hours_from_speeds([8, 11, 12, 13, 9], gust=15.0, direction=250.0)
        windows = find_windows(hours, threshold_kn=10, min_hours=2)
        self.assertEqual(len(windows), 1)
        w = windows[0]
        self.assertEqual(w.n_hours, 3)
        self.assertEqual(w.start, datetime(2024, 5, 1, 9))
        self.assertEqual(w.end, datetime(2024, 5, 1, 12))
        self.assertAlmostEqual(w.mean_speed, 12.0)
        self.assertEqual(w.sector, "WSW")

    def test_min_duration_filters_single_hours(self):
        hours = hours_from_speeds([8, 14, 8, 14, 8])
        self.assertEqual(find_windows(hours, 10, min_hours=2), [])

    def test_night_hours_break_window(self):
        hours = hours_from_speeds([14, 14, 14, 14])
        hours[1].daylight = False
        hours[2].daylight = False
        # Übrig bleiben zwei isolierte Einzelstunden -> kein Fenster
        self.assertEqual(find_windows(hours, 10, min_hours=2), [])

    def test_data_gap_breaks_window(self):
        hours = hours_from_speeds([14, 14])
        later = hours_from_speeds([14, 14], start=datetime(2024, 5, 1, 15))
        windows = find_windows(hours + later, 10, min_hours=2)
        self.assertEqual(len(windows), 2)

    def test_missing_speed_breaks_window(self):
        hours = hours_from_speeds([14, None, 14, 14])
        windows = find_windows(hours, 10, min_hours=2)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].n_hours, 2)

    def test_gusty_flag(self):
        calm = hours_from_speeds([12, 12, 12], gust=18.0)
        self.assertFalse(find_windows(calm, 10)[0].gusty)
        gusty = hours_from_speeds([12, 12, 12], gust=30.0)
        w = find_windows(gusty, 10)[0]
        self.assertTrue(w.gusty)
        self.assertAlmostEqual(w.gust_factor, 2.5)

    def test_threshold_is_inclusive(self):
        hours = hours_from_speeds([10.0, 10.0])
        self.assertEqual(len(find_windows(hours, 10, min_hours=2)), 1)

    def test_kite_days(self):
        hours = hours_from_speeds([14] * 3)
        next_day = hours_from_speeds([14] * 3, start=datetime(2024, 5, 2, 8))
        windows = find_windows(hours + next_day, 10)
        self.assertEqual(
            core.kite_days(windows), {date(2024, 5, 1), date(2024, 5, 2)}
        )


class TestStatsHelpers(unittest.TestCase):
    def test_calendar_days(self):
        days = core.calendar_days()
        self.assertEqual(len(days), 366)
        self.assertIn((2, 29), days)
        self.assertEqual(days[0], (1, 1))
        self.assertEqual(days[-1], (12, 31))

    def test_smooth_circular_preserves_mean(self):
        values = [0.0] * 360
        values[10] = 1.0
        smoothed = core.smooth_circular(values, radius=3)
        self.assertAlmostEqual(sum(smoothed), 1.0, places=9)
        self.assertAlmostEqual(smoothed[10], 1 / 7)
        self.assertAlmostEqual(smoothed[13], 1 / 7)
        self.assertAlmostEqual(smoothed[14], 0.0)

    def test_smooth_circular_wraps(self):
        values = [0.0] * 100
        values[0] = 1.0
        smoothed = core.smooth_circular(values, radius=3)
        self.assertAlmostEqual(smoothed[99], 1 / 7)  # Jahreswechsel

    def test_mean_std(self):
        m, s = core.mean_std([2, 4, 4, 4, 5, 5, 7, 9])
        self.assertAlmostEqual(m, 5.0)
        self.assertAlmostEqual(s, 2.0)


if __name__ == "__main__":
    unittest.main()
