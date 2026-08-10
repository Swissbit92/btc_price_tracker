"""`compute_all` must survive a series shorter than its longest indicator.

`ta.ichimoku` returns a tuple whose FIRST ELEMENT is None when the series is
shorter than senkou (52). `_compute_ichimoku` guarded the tuple — which is
neither None nor empty in that case — and then dereferenced the element, so
`compute_all` raised AttributeError and the token's whole update died.

The effect was silent and total: any token with under 52 periods in its window
could never have a bar written. Five weekly collections (sol, pepe, sui, wif,
wld) were stuck for up to 129 days. It read as an indicator-warmup quirk
because pandas_ta's own log line sits immediately above it:

    [X] Series has 50 rows but indicator requires at least 52. Returning None.

Every other helper in `indicators.py` guards the object it dereferences; this
was the only one that guarded the container.
"""

import numpy as np
import pandas as pd
import pytest

from btc_tracker_mongodb.indicators import compute_all


def _ohlcv(rows: int) -> pd.DataFrame:
    """A deterministic frame with enough variation for indicators to compute."""
    idx = pd.date_range("2026-01-01", periods=rows, freq="W", tz="UTC")
    base = np.linspace(100.0, 140.0, rows)
    wobble = np.sin(np.arange(rows)) * 2.0
    close = base + wobble
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.5,
            "Low": close - 1.5,
            "Close": close,
            "Volume": np.full(rows, 1_000.0),
        },
        index=idx,
    )


class TestShortHistoryDoesNotCrash:
    @pytest.mark.parametrize("rows", [4, 20, 30, 42, 49, 51])
    def test_compute_all_survives_series_shorter_than_ichimoku(self, rows):
        """4 rows is wif's real weekly window; 49 is sol's; 51 is one short of senkou."""
        out = compute_all(_ohlcv(rows), "1w")

        assert len(out) == rows

    def test_ichimoku_columns_are_absent_rather_than_wrong(self):
        """Leaving them out is correct, not a fallback: `_validatable_cols`
        intersects with the frame's columns, so an absent column cannot block a
        row — and a token genuinely has no ichimoku until it has 52 periods."""
        out = compute_all(_ohlcv(20), "1w")

        for col in ("Ichimoku_A", "Ichimoku_B", "Ichimoku_Conversion", "Ichimoku_Base"):
            assert col not in out.columns

    def test_ichimoku_is_computed_once_there_is_enough_history(self):
        """The guard must not suppress ichimoku on a series that can support it."""
        out = compute_all(_ohlcv(120), "1w")

        assert "Ichimoku_A" in out.columns
        assert out["Ichimoku_A"].notna().any()
