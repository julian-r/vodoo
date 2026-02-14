"""Tests for RetryConfig and exponential backoff behaviour."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from vodoo.config import OdooConfig
from vodoo.transport import DEFAULT_RETRY, RetryConfig

# -- RetryConfig unit tests ---------------------------------------------------


class TestRetryConfig:
    def test_defaults(self) -> None:
        rc = RetryConfig()
        assert rc.max_retries == 2
        assert rc.backoff_base == 0.5
        assert rc.backoff_max == 30.0

    def test_custom_values(self) -> None:
        rc = RetryConfig(max_retries=5, backoff_base=1.0, backoff_max=60.0)
        assert rc.max_retries == 5
        assert rc.backoff_base == 1.0
        assert rc.backoff_max == 60.0

    def test_frozen(self) -> None:
        rc = RetryConfig()
        with pytest.raises(AttributeError):
            rc.max_retries = 10  # type: ignore[misc]

    def test_delay_exponential(self) -> None:
        rc = RetryConfig(backoff_base=1.0, backoff_max=100.0)
        assert rc.delay(0) == 1.0  # 1.0 * 2^0
        assert rc.delay(1) == 2.0  # 1.0 * 2^1
        assert rc.delay(2) == 4.0  # 1.0 * 2^2
        assert rc.delay(3) == 8.0  # 1.0 * 2^3

    def test_delay_capped_at_max(self) -> None:
        rc = RetryConfig(backoff_base=1.0, backoff_max=5.0)
        assert rc.delay(0) == 1.0
        assert rc.delay(1) == 2.0
        assert rc.delay(2) == 4.0
        assert rc.delay(3) == 5.0  # capped
        assert rc.delay(10) == 5.0  # still capped

    def test_delay_with_fractional_base(self) -> None:
        rc = RetryConfig(backoff_base=0.5, backoff_max=30.0)
        assert rc.delay(0) == 0.5  # 0.5 * 2^0
        assert rc.delay(1) == 1.0  # 0.5 * 2^1
        assert rc.delay(2) == 2.0  # 0.5 * 2^2
        assert rc.delay(3) == 4.0  # 0.5 * 2^3

    def test_zero_retries_disables(self) -> None:
        rc = RetryConfig(max_retries=0)
        assert rc.max_retries == 0


class TestDefaultRetry:
    def test_default_is_retry_config(self) -> None:
        assert isinstance(DEFAULT_RETRY, RetryConfig)

    def test_default_matches_expected_values(self) -> None:
        assert DEFAULT_RETRY.max_retries == 2
        assert DEFAULT_RETRY.backoff_base == 0.5
        assert DEFAULT_RETRY.backoff_max == 30.0


# -- OdooConfig integration ---------------------------------------------------


class TestOdooConfigRetry:
    """Test that OdooConfig exposes retry settings and builds RetryConfig."""

    def _make_config(self, **overrides: object) -> OdooConfig:
        defaults = {
            "url": "https://test.odoo.com",
            "database": "testdb",
            "username": "admin",
            "password": "secret",
        }
        defaults.update(overrides)
        return OdooConfig(**defaults)  # type: ignore[arg-type]

    def test_default_retry_config(self) -> None:
        cfg = self._make_config()
        rc = cfg.retry_config
        assert rc.max_retries == 2
        assert rc.backoff_base == 0.5
        assert rc.backoff_max == 30.0

    def test_custom_retry_config(self) -> None:
        cfg = self._make_config(retry_count=5, retry_backoff=2.0, retry_max_backoff=120.0)
        rc = cfg.retry_config
        assert rc.max_retries == 5
        assert rc.backoff_base == 2.0
        assert rc.backoff_max == 120.0

    def test_zero_retries(self) -> None:
        cfg = self._make_config(retry_count=0)
        rc = cfg.retry_config
        assert rc.max_retries == 0

    def test_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ODOO_URL", "https://test.odoo.com")
        monkeypatch.setenv("ODOO_DATABASE", "testdb")
        monkeypatch.setenv("ODOO_USERNAME", "admin")
        monkeypatch.setenv("ODOO_PASSWORD", "secret")
        monkeypatch.setenv("ODOO_RETRY_COUNT", "4")
        monkeypatch.setenv("ODOO_RETRY_BACKOFF", "1.5")
        monkeypatch.setenv("ODOO_RETRY_MAX_BACKOFF", "60")
        cfg = OdooConfig(_env_file=None)  # type: ignore[call-arg]
        rc = cfg.retry_config
        assert rc.max_retries == 4
        assert rc.backoff_base == 1.5
        assert rc.backoff_max == 60.0


# -- Transport retry behaviour ------------------------------------------------


class TestTransportRetry:
    """Test that transports actually use the retry config with exponential backoff."""

    def test_legacy_transport_uses_retry_config(self) -> None:
        from vodoo.transport import LegacyTransport

        rc = RetryConfig(max_retries=3, backoff_base=0.1, backoff_max=1.0)
        t = LegacyTransport(
            url="http://localhost:8069",
            database="test",
            username="admin",
            password="secret",
            retry=rc,
        )
        assert t.retry is rc
        t.close()

    def test_json2_transport_uses_retry_config(self) -> None:
        from vodoo.transport import JSON2Transport

        rc = RetryConfig(max_retries=3, backoff_base=0.1, backoff_max=1.0)
        t = JSON2Transport(
            url="http://localhost:8069",
            database="test",
            username="admin",
            password="secret",
            retry=rc,
        )
        assert t.retry is rc
        t.close()

    def test_default_retry_when_none(self) -> None:
        from vodoo.transport import LegacyTransport

        t = LegacyTransport(
            url="http://localhost:8069",
            database="test",
            username="admin",
            password="secret",
        )
        assert t.retry == DEFAULT_RETRY
        t.close()

    @patch("vodoo.transport.time.sleep")
    def test_legacy_exponential_backoff_delays(self, mock_sleep: MagicMock) -> None:
        """Verify that LegacyTransport uses exponential delays on retryable errors."""
        from vodoo.transport import LegacyTransport

        rc = RetryConfig(max_retries=3, backoff_base=0.1, backoff_max=10.0)
        t = LegacyTransport(
            url="http://localhost:8069",
            database="test",
            username="admin",
            password="secret",
            retry=rc,
        )
        t._uid = 1  # skip authentication

        # Mock call_service to always raise ConnectError
        t.call_service = MagicMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("connection refused"),
        )

        with pytest.raises(httpx.ConnectError):
            t.execute_kw("res.partner", "search_read", [[]])

        # Should have retried 3 times (attempts 0, 1, 2 fail; attempt 3 raises)
        assert t.call_service.call_count == 4  # 1 initial + 3 retries

        # Check exponential backoff delays: 0.1*2^0, 0.1*2^1, 0.1*2^2
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == pytest.approx([0.1, 0.2, 0.4])
        t.close()

    @patch("vodoo.transport.time.sleep")
    def test_zero_retries_no_sleep(self, mock_sleep: MagicMock) -> None:
        """With max_retries=0, no retries or sleeps should happen."""
        from vodoo.transport import LegacyTransport

        rc = RetryConfig(max_retries=0)
        t = LegacyTransport(
            url="http://localhost:8069",
            database="test",
            username="admin",
            password="secret",
            retry=rc,
        )
        t._uid = 1

        t.call_service = MagicMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("connection refused"),
        )

        with pytest.raises(httpx.ConnectError):
            t.execute_kw("res.partner", "search_read", [[]])

        assert t.call_service.call_count == 1
        mock_sleep.assert_not_called()
        t.close()

    @patch("vodoo.transport.time.sleep")
    def test_non_retryable_method_not_retried(self, mock_sleep: MagicMock) -> None:
        """Write methods should not be retried even on transient errors."""
        from vodoo.transport import LegacyTransport

        rc = RetryConfig(max_retries=3)
        t = LegacyTransport(
            url="http://localhost:8069",
            database="test",
            username="admin",
            password="secret",
            retry=rc,
        )
        t._uid = 1

        t.call_service = MagicMock(  # type: ignore[method-assign]
            side_effect=httpx.ConnectError("connection refused"),
        )

        with pytest.raises(httpx.ConnectError):
            t.execute_kw("res.partner", "write", [[1], {"name": "test"}])

        assert t.call_service.call_count == 1
        mock_sleep.assert_not_called()
        t.close()
