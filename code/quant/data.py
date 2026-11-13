"""Validate price snapshots and adapt them to Qlib's documented binary format.

Price/factor/volume conventions follow Qlib's data documentation. The small
binary writer follows microsoft/qlib scripts/dump_bin.py (_data_to_bin), MIT.
It is a data adapter; features, learning and trading use Qlib itself.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def qlib_symbol(symbol):
    if symbol == "sh000300":
        return "SH000300"
    code, exchange = symbol.split(".")
    if not (len(code) == 6 and code.isdigit() and exchange in {"SH", "SZ"}):
        raise ValueError("unsupported security identifier")
    return exchange + code


def load_series(directory, entry):
    directory = Path(directory).resolve()
    path = (directory / entry["relative_path"]).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError("market file must remain inside the snapshot")
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["file_sha256"]:
        raise ValueError("market file hash mismatch")
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    if len(frame) != entry["rows"] or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("market row count, date order or uniqueness mismatch")
    numeric = frame[["open", "high", "low", "close", "volume"]].to_numpy(float)
    if not np.isfinite(numeric).all() or (numeric[:, :4] <= 0).any() or (numeric[:, 4] < 0).any():
        raise ValueError("invalid price or volume")
    if not ((frame.low <= frame[["open", "close"]].min(axis=1)) &
            (frame.high >= frame[["open", "close"]].max(axis=1))).all():
        raise ValueError("inconsistent OHLC")
    if frame.index[0].date().isoformat() != entry["data_start"] or frame.index[-1].date().isoformat() != entry["data_end"]:
        raise ValueError("market date range mismatch")
    return frame


def normalise_stock(raw, adjusted):
    if not raw.index.equals(adjusted.index):
        raise ValueError("raw/adjusted trading dates differ")
    # Qlib adjusted prices start at 1; factor restores the executable raw
    # price and volume/factor preserves traded share/notional conventions.
    result = adjusted[["open", "high", "low", "close"]].copy() / float(adjusted.close.iloc[0])
    result["factor"] = result.close / raw.close
    result["volume"] = raw.volume * 100 / result.factor
    result["vwap"] = raw.amount / result.volume
    result["change"] = result.close.pct_change(fill_method=None)
    result.loc[raw.volume <= 0, :] = np.nan
    return result


def write_binary(frame, calendar, directory):
    directory.mkdir(parents=True, exist_ok=True)
    start, end = calendar.get_loc(frame.index[0]), calendar.get_loc(frame.index[-1])
    aligned = frame.reindex(calendar[start:end + 1])
    for column in aligned:
        np.hstack([start, aligned[column].to_numpy(float)]).astype("<f4").tofile(directory / f"{column}.day.bin")


def prepare_market(source, output):
    source, output = Path(source), Path(output)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    entries = {(e["symbol"], e["adjustment"]): e for e in manifest["series"]}
    if len(entries) != len(manifest["series"]):
        raise ValueError("duplicate market series")
    benchmark = load_series(source, entries[("sh000300", "none")])
    calendar = benchmark.index
    (output / "calendars").mkdir(parents=True, exist_ok=True)
    (output / "instruments").mkdir(exist_ok=True)
    (output / "calendars/day.txt").write_text("\n".join(d.date().isoformat() for d in calendar) + "\n",
                                              encoding="utf-8", newline="\n")
    stocks, intervals = [], []
    for (symbol, adjustment), entry in sorted(entries.items()):
        if symbol == "sh000300" or adjustment != "qfq":
            continue
        raw_entry = entries[(symbol, "none")]
        if raw_entry["volume_unit"] != "hand_100_shares":
            raise ValueError("stock volume unit must be explicitly verified")
        raw, adjusted = load_series(source, raw_entry), load_series(source, entry)
        if not raw.index.isin(calendar).all():
            raise ValueError("stock contains dates outside the market calendar")
        frame = normalise_stock(raw, adjusted)
        code = qlib_symbol(symbol)
        write_binary(frame, calendar, output / "features" / code.lower())
        stocks.append({"symbol": symbol, "qlib_symbol": code, "name": entry["company"]})
        intervals.append(f"{code}\t{frame.index[0].date()}\t{frame.index[-1].date()}")
    if not stocks:
        raise ValueError("no paired stock series")
    write_binary(benchmark[["open", "high", "low", "close", "volume"]].assign(factor=1.0),
                 calendar, output / "features/sh000300")
    (output / "instruments/all.txt").write_text("\n".join(intervals) + "\n", encoding="utf-8", newline="\n")
    metadata = {"stocks": stocks, "trading_days": len(calendar),
                "data_start": str(calendar[0].date()), "data_end": str(calendar[-1].date()),
                "source_manifest_sha256": hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest(),
                "price_basis": "current forward-adjusted snapshot; raw prices retained via factor",
                "vintage_reconstruction": False}
    (output / "capture.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return metadata, calendar


def purged_segments(calendar, boundaries, horizon):
    """Label is close[t+1+h] / close[t+1] - 1 on MARKET sessions.

    Last eligible feature date in a split must have its entire label inside
    that split. Do not shift per-security rows across a suspension.
    """
    if horizon < 1:
        raise ValueError("horizon must be positive")
    ranges = [(pd.Timestamp(start), pd.Timestamp(end)) for start, end in boundaries.values()]
    if any(start > end for start, end in ranges) or any(a[1] >= b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError("raw experiment segments overlap or are reversed")
    result = {}
    for name, (start, end) in boundaries.items():
        dates = calendar[(calendar >= start) & (calendar <= end)]
        if len(dates) <= horizon + 1:
            raise ValueError(f"too few dates in {name}")
        result[name] = (str(dates[0].date()), str(dates[-horizon - 2].date()))
    ordered = list(result.values())
    if any(a[1] >= b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("experiment segments overlap")
    return result
