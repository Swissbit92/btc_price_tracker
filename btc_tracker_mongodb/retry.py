"""
retry.py — Shared retry/backoff helper for KuCoin's misclassified 429000 rate-limit error.

CCXT surfaces KuCoin's HTTP 429 rate-limit response as a generic `ExchangeError` rather than
`RateLimitExceeded`, so callers must string-match "429" in the exception text to tell a
transient rate limit apart from a genuine exchange error.

Extracted from `extract.py`'s original inline retry loop (audit 2026-08-22, rec #6 — Clean
Code, sev med-high) so `extract_perp.py`'s OHLCV and funding-rate fetchers share the *exact
same* semantics instead of drifting. Before this fix, only the spot path
(`extract.fetch_candles`) retried; the perp path had none, and `lean_pipeline.py` had to
invent its own general-purpose `_retry()` around the perp fetchers as a workaround — direct
evidence the gap was real (a 300-token backfill hits transient 429s/timeouts routinely).

`lean_pipeline._retry()` stays as-is: it wraps a broader set of exceptions (any transient
network/exchange failure across a bulk research-universe backfill) and is intentionally more
permissive than this helper, which targets the one specific misclassified error both
production fetchers hit.
"""

import time

from ccxt.base.errors import ExchangeError


def call_with_kucoin_retry(fn, *args, tries: int = 3, **kwargs):
    """Call ``fn(*args, **kwargs)``, retrying on KuCoin's misclassified 429000 rate limit.

    Retries up to *tries* times total with exponential backoff (1s, 2s, 4s, ...) between
    attempts. Any `ExchangeError` whose message does not contain "429", or exhausting all
    retries, re-raises the original exception unchanged.
    """
    for attempt in range(tries):
        try:
            return fn(*args, **kwargs)
        except ExchangeError as e:
            if "429" in str(e) and attempt < tries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s, ...
                continue
            raise
