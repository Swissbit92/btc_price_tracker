"""Telegram alerts that survive one dropped connection.

WHY THIS EXISTS. Each of the three launchd entrypoints (`run_hourly`,
`run_daily`, `run_watchdog`) carried its own `_send_telegram`, and all three
ended the same way::

    except Exception:
        pass

One dropped TCP connection and the alert was gone, with nothing written
anywhere. These are the **failure** notifications — the message that says the
pipeline broke — so the case where the send fails is exactly the case where
something already went wrong and you most need to hear about it.

Two of the three also never looked at the HTTP response at all, only at whether
an exception was raised. `run_watchdog._send_telegram` therefore returned
``True`` after a 400, and its caller had no way to know the stale-data alert had
been rejected rather than delivered. Same family as this ecosystem's recurring
sentinel bug: a failure that renders as a success.

THE POLICY, shared with eeva-sol, eeva-exec, eeva-dca and the ecosystem
monitoring scripts — the repos never import each other, so the RULE travels and
the implementation does not:

**Retry by KIND, never by pessimism.** 5xx is the far side and 429 is us; both
are answered by waiting. A 4xx is our own request — a malformed body, a caption
past the 1024-char limit — and retrying it burns the rate limit three times to
fail identically. eeva-sol learned the distinction from a Jupiter 400 that
wrapped an upstream 503: read the failure before deciding it is transient.

**It never raises.** A failure to report a problem must not become a second
problem, and must never crash a pipeline that was otherwise fine.

**An upload is rebuilt per attempt.** A file handle read by attempt 1 is at EOF
for attempt 2, so a retry reusing it uploads an empty body that Telegram may
accept — reporting success having sent nothing, which is strictly worse than not
retrying at all.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

import requests

TIMEOUT_SECONDS = 20
SEND_ATTEMPTS = 3
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
BACKOFF_SECONDS = (1.0, 3.0)
CAPTION_LIMIT = 1024


def _post_with_retry(
    post: Callable[[], requests.Response],
    sleep: Callable[[float], None] | None = None,
) -> bool:
    """Run `post` until Telegram accepts it, or the failure is not worth retrying.

    `post` is a CALLABLE rather than a prepared request precisely so an upload
    can be rebuilt per attempt. Returns whether Telegram accepted it; never
    raises.
    """
    # Resolved at CALL time: a default argument captures `time.sleep` at import
    # and no test could then replace it.
    sleep = sleep or time.sleep
    for attempt in range(1, SEND_ATTEMPTS + 1):
        last = attempt == SEND_ATTEMPTS
        try:
            resp = post()
            # Checked, not assumed. Two of the three original senders looked only
            # at whether an exception was raised, so a 400 read as delivered.
            if resp.status_code == 200:
                return True
            if resp.status_code not in RETRY_STATUSES or last:
                return False
        except Exception:  # noqa: BLE001 - reporting must never crash the pipeline
            if last:
                return False
        sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
    return False


def send_alert(
    message: str,
    photo_path: str | Path | None = None,
    token: str | None = None,
    chat_id: str | None = None,
    sleep: Callable[[float], None] | None = None,
) -> bool:
    """Send one alert, with a header image when one is available.

    Returns whether everything intended was delivered. Unconfigured credentials
    return False quietly — a pipeline must run identically with or without a
    token, so the absence of alerting can never be the reason a job fails.

    A message longer than Telegram's 1024-char caption limit is sent as a caption
    plus a follow-up text part. Previously only `run_daily` did this and the other
    two **silently truncated**, which for the watchdog meant a long list of stale
    collections lost its tail — the alert arrived looking complete.
    """
    token = token or os.getenv("TG_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return False

    def _text(body: str) -> bool:
        return _post_with_retry(
            lambda: requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": body, "parse_mode": "HTML"},
                timeout=TIMEOUT_SECONDS,
            ),
            sleep=sleep,
        )

    has_photo = bool(photo_path) and Path(photo_path).is_file()
    if not has_photo:
        return _text(message)

    def _photo() -> requests.Response:
        # Reopened per attempt — see the module docstring.
        with open(photo_path, "rb") as f:
            return requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={
                    "chat_id": chat_id,
                    "caption": message[:CAPTION_LIMIT],
                    "parse_mode": "HTML",
                },
                files={"photo": f},
                timeout=TIMEOUT_SECONDS,
            )

    try:
        sent = _post_with_retry(_photo, sleep=sleep)
    except OSError:
        # Vanished between is_file() and open(). Not transient; the words matter
        # more than the picture, so fall through to text.
        sent = False
    if not sent:
        return _text(message)

    remainder = message[CAPTION_LIMIT:]
    return _text(remainder) if remainder else True
