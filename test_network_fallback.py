import logging
import threading
import unittest
from unittest.mock import patch

import main


class NetworkFallbackTests(unittest.TestCase):
    def test_manual_sign_during_scheduler_takes_over_and_invalidates_timer_event(self):
        app = main.App.__new__(main.App)
        app.scheduler_enabled = True
        app.signing = False
        app.schedule_version = 7
        app.logger = logging.getLogger("test")
        app.save_credentials = lambda: ("user", "password")
        launched = []
        app.launch_sign = lambda source, credentials=None: launched.append((source, credentials))

        app.manual_sign()

        self.assertEqual(app.schedule_version, 8)
        self.assertEqual(launched, [("timer", ("user", "password"))])

    def test_connection_failure_retries_through_system_proxy(self):
        direct, proxy = object(), object()
        expected = {"success": True}
        with patch.object(main, "request_json", side_effect=[main.NetworkError("offline"), expected]) as request:
            actual = main.request_with_fallback(
                direct, proxy, "/api/user/login", "POST", {}, "",
                threading.Event(), logging.getLogger("test"),
            )
        self.assertEqual(actual, expected)
        self.assertEqual(request.call_count, 2)
        self.assertIs(request.call_args_list[0].args[0], direct)
        self.assertIs(request.call_args_list[1].args[0], proxy)

    def test_http_conflict_is_not_replayed_through_proxy(self):
        direct, proxy = object(), object()
        conflict = main.SignError("server returned HTTP 409 Conflict")
        with patch.object(main, "request_json", side_effect=conflict) as request:
            with self.assertRaisesRegex(main.SignError, "HTTP 409"):
                main.request_with_fallback(
                    direct, proxy, "/api/user/login", "POST", {}, "",
                    threading.Event(), logging.getLogger("test"),
                )
        request.assert_called_once()
        self.assertIs(request.call_args.args[0], direct)

    def test_login_http_409_retries_once_through_system_proxy(self):
        direct, proxy = object(), object()
        expected = {"success": True}
        conflict = main.HttpStatusError(409, "server returned HTTP 409 Conflict")
        with patch.object(main, "request_json", side_effect=[conflict, expected]) as request:
            actual = main.request_with_fallback(
                direct, proxy, main.LOGIN_API, "POST", {"username": "u", "password": "p"}, "",
                threading.Event(), logging.getLogger("test"), retry_login_conflict_via_proxy=True,
            )
        self.assertEqual(actual, expected)
        self.assertEqual(request.call_count, 2)
        self.assertIs(request.call_args_list[0].args[0], direct)
        self.assertIs(request.call_args_list[1].args[0], proxy)

    def test_http_409_elsewhere_is_not_replayed(self):
        conflict = main.HttpStatusError(409, "server returned HTTP 409 Conflict")
        with patch.object(main, "request_json", side_effect=conflict) as request:
            with self.assertRaisesRegex(main.HttpStatusError, "HTTP 409"):
                main.request_with_fallback(
                    object(), object(), main.CHECKIN_API, "POST", {}, "token",
                    threading.Event(), logging.getLogger("test"), retry_login_conflict_via_proxy=True,
                )
        request.assert_called_once()

    def test_network_failure_without_configured_proxy_is_reported(self):
        with patch.object(main, "request_json", side_effect=main.NetworkError("offline")) as request:
            with self.assertRaisesRegex(main.NetworkError, r"\u672a\u68c0\u6d4b\u5230\u53ef\u7528\u7684\u7cfb\u7edf\u4ee3\u7406"):
                main.request_with_fallback(
                    object(), None, "/api/user/login", "POST", {}, "",
                    threading.Event(), logging.getLogger("test"),
                )
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()

