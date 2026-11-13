"""Hand-calculable price/volume and time boundaries, no model/API calls."""
import hashlib
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    from quant.data import load_series, normalise_stock, purged_segments, write_binary
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "install the optional quant environment for adapter tests")
class QuantDataTests(unittest.TestCase):
    def test_price_restoration_volume_and_future_common_scaling(self):
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        frame = pd.DataFrame({"open": 10., "high": 12., "low": 9., "close": 11.,
                              "volume": 1000., "amount": 1100000.}, index=dates)
        adjusted = frame.copy()
        adjusted.loc[:, ["open", "high", "low", "close"]] *= 0.8
        first = normalise_stock(frame, adjusted)
        np.testing.assert_allclose(first.close / first.factor, frame.close)
        np.testing.assert_allclose(first.close * first.volume, frame.close * frame.volume * 100)
        adjusted.loc[:, ["open", "high", "low", "close"]] *= 0.25
        pd.testing.assert_frame_equal(first, normalise_stock(frame, adjusted))

    def test_market_calendar_suspension_is_not_compressed(self):
        with tempfile.TemporaryDirectory() as temp:
            calendar = pd.date_range("2024-01-01", periods=8, freq="B")
            frame = pd.DataFrame({"close": [10., 20., 40.]}, index=calendar[[1, 2, 4]])
            write_binary(frame, calendar, Path(temp))
            values = np.fromfile(Path(temp) / "close.day.bin", dtype="<f4")
            self.assertEqual(values[0], 1)
            self.assertTrue(np.isnan(values[3]))
            self.assertEqual(values[4], 40)

    def test_entry_next_close_and_five_sessions_stay_inside_split(self):
        calendar = pd.date_range("2024-01-01", periods=40, freq="B")
        split = purged_segments(calendar, {"train": (calendar[0], calendar[19]),
                                           "valid": (calendar[20], calendar[39])}, 5)
        last_feature = pd.Timestamp(split["train"][1])
        self.assertEqual(calendar.get_loc(last_feature), 13)
        self.assertEqual(calendar[calendar.get_loc(last_feature) + 6], calendar[19])
        with self.assertRaisesRegex(ValueError, "overlap"):
            purged_segments(calendar, {"train": (calendar[0], calendar[25]),
                                       "valid": (calendar[20], calendar[39])}, 5)

    def test_tampered_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stock.csv"
            path.write_text("date,open,high,low,close,volume,amount\n2024-01-02,10,11,9,10,100,100000\n", encoding="utf-8")
            entry = {"relative_path": path.name, "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "rows": 1, "data_start": "2024-01-02", "data_end": "2024-01-02"}
            self.assertEqual(len(load_series(Path(temp), entry)), 1)
            path.write_text(path.read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash"):
                load_series(Path(temp), entry)


if __name__ == "__main__":
    unittest.main()
