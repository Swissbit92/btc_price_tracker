"""btc_tracker_mongodb.alerting — an alert survives one dropped connection.

Each of the three launchd entrypoints carried its own `_send_telegram`, and all
three ended in `except Exception: pass`. These are the FAILURE alerts, so the
case where the send fails is the case where something has already gone wrong.

Two of the three never looked at the HTTP response at all — only at whether an
exception was raised — so a 400 read as delivered. That is this ecosystem's
recurring sentinel bug: a failure rendered as a success.
"""

from __future__ import annotations

from unittest.mock import patch

from btc_tracker_mongodb import alerting


def _resp(status=200):
    class R:
        status_code = status
        text = ""
    return R()


NO_SLEEP = {"sleep": lambda _: None}


class TestRetryPolicy:
    def test_a_transport_failure_is_retried_then_succeeds(self):
        calls = {"n": 0}

        def post():
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionResetError("Connection reset by peer")
            return _resp()

        assert alerting._post_with_retry(post, sleep=lambda _: None) is True
        assert calls["n"] == 2

    def test_a_5xx_is_retried(self):
        calls = {"n": 0}

        def post():
            calls["n"] += 1
            return _resp(503) if calls["n"] == 1 else _resp()

        assert alerting._post_with_retry(post, sleep=lambda _: None) is True
        assert calls["n"] == 2

    def test_a_4xx_is_not_retried(self):
        calls = {"n": 0}

        def post():
            calls["n"] += 1
            return _resp(400)

        assert alerting._post_with_retry(post, sleep=lambda _: None) is False
        assert calls["n"] == 1

    def test_a_non_200_is_a_failure_not_a_success(self):
        """The old senders returned True whenever no exception was raised."""
        assert alerting._post_with_retry(lambda: _resp(400), sleep=lambda _: None) is False

    def test_retries_are_bounded_and_it_never_raises(self):
        calls = {"n": 0}

        def post():
            calls["n"] += 1
            raise TimeoutError("timed out")

        assert alerting._post_with_retry(post, sleep=lambda _: None) is False
        assert calls["n"] == 3


class TestSendAlert:
    def test_unconfigured_never_reaches_the_network(self):
        with patch.object(alerting.requests, "post") as post:
            assert alerting.send_alert("hi", token="", chat_id="", **NO_SLEEP) is False
            post.assert_not_called()

    def test_a_plain_message_is_sent(self):
        with patch.object(alerting.requests, "post", return_value=_resp()) as post:
            assert alerting.send_alert("hi", token="t", chat_id="c", **NO_SLEEP) is True
        assert "sendMessage" in post.call_args[0][0]

    def test_an_upload_is_rebuilt_per_attempt_not_replayed(self, tmp_path):
        """The retry bug that would look like a success.

        A file read by attempt 1 is at EOF for attempt 2; reusing the handle
        uploads an EMPTY body Telegram may accept — success, having sent nothing.
        """
        img = tmp_path / "header.png"
        img.write_bytes(b"IMGDATA")
        bodies, calls = [], {"n": 0}

        def fake_post(url, **kw):
            if "sendPhoto" in url:
                calls["n"] += 1
                bodies.append(kw["files"]["photo"].read())
                return _resp(503) if calls["n"] == 1 else _resp()
            return _resp()

        with patch.object(alerting.requests, "post", side_effect=fake_post):
            assert alerting.send_alert("short", img, token="t", chat_id="c", **NO_SLEEP) is True
        assert bodies == [b"IMGDATA", b"IMGDATA"]

    def test_a_long_message_keeps_its_tail_instead_of_being_truncated(self, tmp_path):
        """`run_watchdog` used to truncate at 1024, losing the end of the
        stale-collection list while the alert still looked complete."""
        img = tmp_path / "header.png"
        img.write_bytes(b"IMG")
        long_msg = "A" * 1500
        seen = []

        def fake_post(url, **kw):
            seen.append(("photo" if "sendPhoto" in url else "text", kw))
            return _resp()

        with patch.object(alerting.requests, "post", side_effect=fake_post):
            assert alerting.send_alert(long_msg, img, token="t", chat_id="c", **NO_SLEEP) is True
        kinds = [k for k, _ in seen]
        assert kinds == ["photo", "text"], "the overflow must be sent, not dropped"
        assert seen[1][1]["json"]["text"] == "A" * 476

    def test_a_failed_photo_falls_back_to_text_so_the_words_still_arrive(self, tmp_path):
        img = tmp_path / "header.png"
        img.write_bytes(b"IMG")

        def fake_post(url, **kw):
            return _resp(400) if "sendPhoto" in url else _resp()

        with patch.object(alerting.requests, "post", side_effect=fake_post):
            assert alerting.send_alert("body", img, token="t", chat_id="c", **NO_SLEEP) is True

    def test_a_missing_photo_is_simply_a_text_alert(self):
        with patch.object(alerting.requests, "post", return_value=_resp()) as post:
            assert alerting.send_alert("body", "/nope/none.png", token="t", chat_id="c", **NO_SLEEP) is True
        assert "sendMessage" in post.call_args[0][0]
