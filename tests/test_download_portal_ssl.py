"""Tests for the firmware download portal SSL context."""

from __future__ import annotations

from datetime import UTC, datetime
import os
import socket
import ssl
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

from homeassistant.util.ssl import SSL_ALPN_HTTP11, create_client_context
import pytest

from custom_components.luxtronik2 import download_portal_ssl
from custom_components.luxtronik2.const import DOWNLOAD_PORTAL_URL
from custom_components.luxtronik2.download_portal_ssl import (
    DOWNLOAD_PORTAL_CA_BUNDLE,
    async_get_download_portal_ssl_context,
)

# The two CA certificates www.heatpump24.com fails to send. See issue #783.
EXPECTED_PINNED_CAS = (
    "Telia RSA OV CA v4",
    "Telia RSA TLS Root CA v3",
)

# Opt in for the live check below. It is not part of a normal run: it needs the
# network, and an outage at Nibe must never fail an unrelated pull request.
PORTAL_TLS_CHECK_ENV = "LUXTRONIK_CHECK_PORTAL_TLS"


@pytest.fixture(autouse=True)
def _reset_context_cache():
    """Reset the module level context cache between tests."""
    download_portal_ssl._SSL_CONTEXT = None
    download_portal_ssl._BUILD_FAILED = False
    yield
    download_portal_ssl._SSL_CONTEXT = None
    download_portal_ssl._BUILD_FAILED = False


def _make_hass() -> MagicMock:
    """Return a hass mock whose executor runs the job inline."""
    hass = MagicMock()

    async def _run(func, *args):
        return func(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=_run)
    return hass


class TestBundledCertificates:
    """The pinned CA bundle itself."""

    def test_bundle_contains_both_missing_chain_certificates(self):
        """Both omitted intermediates must be present, not just the first one.

        Loaded into an *empty* store on purpose: create_default_context() pulls in
        the OS trust store first, which on some machines already carries these CAs
        and would make this assertion pass with an empty bundle.
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=DOWNLOAD_PORTAL_CA_BUNDLE)

        assert len(context.get_ca_certs()) == len(EXPECTED_PINNED_CAS)

        subjects = {
            value
            for cert in context.get_ca_certs()
            for rdn in cert.get("subject", ())
            for key, value in rdn
            if key == "commonName"
        }

        for expected in EXPECTED_PINNED_CAS:
            assert expected in subjects

    def test_pinned_chain_is_cryptographically_anchored_in_certifi(self):
        """The property the whole design rests on, checked offline.

        Names are not enough: verify the actual signatures, so a bad paste of PEM
        bytes cannot slip through. Each pinned CA must be signed by the next, and
        the topmost one by a CA that is already publicly trusted.
        """
        from itertools import pairwise
        import warnings

        import certifi
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import padding

        def _assert_signed_by(cert, issuer) -> None:
            issuer.public_key().verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                padding.PKCS1v15(),
                cert.signature_hash_algorithm,
            )

        pinned = x509.load_pem_x509_certificates(DOWNLOAD_PORTAL_CA_BUNDLE.encode())
        assert len(pinned) == len(EXPECTED_PINNED_CAS)

        with open(certifi.where(), "rb") as trust_store, warnings.catch_warnings():
            # certifi ships a certificate with a non-positive serial number.
            warnings.simplefilter("ignore")
            trusted = {
                cert.subject.rfc4514_string(): cert
                for cert in x509.load_pem_x509_certificates(trust_store.read())
            }

        # Each pinned CA is signed by the next one in the bundle ...
        for cert, issuer in pairwise(pinned):
            assert cert.issuer == issuer.subject
            _assert_signed_by(cert, issuer)

        # ... and the topmost by a CA that is already publicly trusted.
        topmost = pinned[-1]
        public_root = trusted.get(topmost.issuer.rfc4514_string())
        assert public_root is not None
        _assert_signed_by(topmost, public_root)

    def test_bundled_certificates_are_not_expired(self):
        """Guard against silently shipping a stale pin."""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=DOWNLOAD_PORTAL_CA_BUNDLE)

        now = datetime.now(UTC)
        pinned = [
            cert
            for cert in context.get_ca_certs()
            if any(
                value in EXPECTED_PINNED_CAS
                for rdn in cert.get("subject", ())
                for key, value in rdn
                if key == "commonName"
            )
        ]
        assert len(pinned) == len(EXPECTED_PINNED_CAS)

        for cert in pinned:
            not_after = datetime.strptime(
                cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
            ).replace(tzinfo=UTC)
            assert not_after > now


class TestAsyncGetDownloadPortalSslContext:
    """Context construction and caching."""

    @pytest.mark.asyncio
    async def test_returns_ssl_context_built_in_executor(self):
        hass = _make_hass()

        context = await async_get_download_portal_ssl_context(hass)

        assert isinstance(context, ssl.SSLContext)
        hass.async_add_executor_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_context_is_built_once_and_cached(self):
        hass = _make_hass()

        first = await async_get_download_portal_ssl_context(hass)
        second = await async_get_download_portal_ssl_context(hass)

        assert first is second
        hass.async_add_executor_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_verification_stays_enabled(self):
        """The pin must never turn into a blanket 'skip verification'."""
        hass = _make_hass()

        context = await async_get_download_portal_ssl_context(hass)

        assert context is not None
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True

    @pytest.mark.asyncio
    async def test_returns_none_when_context_cannot_be_built(self, caplog):
        hass = _make_hass()
        hass.async_add_executor_job = AsyncMock(side_effect=ssl.SSLError("boom"))

        context = await async_get_download_portal_ssl_context(hass)

        assert context is None
        assert "download portal" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_repeated_build_failure_warns_only_once(self, caplog):
        """A permanent failure must not re-spam the log on every poll."""
        import logging

        hass = _make_hass()
        hass.async_add_executor_job = AsyncMock(side_effect=ssl.SSLError("boom"))

        with caplog.at_level(logging.DEBUG):
            await async_get_download_portal_ssl_context(hass)
            await async_get_download_portal_ssl_context(hass)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1


@pytest.mark.skipif(
    not os.environ.get(PORTAL_TLS_CHECK_ENV),
    reason=f"live network check, set {PORTAL_TLS_CHECK_ENV}=1 to run it",
)
@pytest.mark.usefixtures("socket_enabled")
class TestWorkaroundStillNeeded:
    """Tells us when the pin can be dropped again.

    Run by the scheduled `portal-tls-watch` workflow. It fails on purpose once
    Nibe repairs the chain, because that failure is the notification.
    """

    def test_portal_still_serves_an_incomplete_chain(self, monkeypatch):
        # The test harness blocks the network twice over: pytest-homeassistant-
        # custom-component replaces socket.getaddrinfo with one that refuses every
        # hostname, and pytest-socket wraps connect() with a 127.0.0.1 allow list.
        # _socket still holds the untouched C originals, so restore both from there
        # rather than reaching into either plugin's private helpers.
        import _socket

        monkeypatch.setattr(socket, "getaddrinfo", _socket.getaddrinfo)
        monkeypatch.setattr(socket.socket, "connect", _socket.socket.connect)

        host = urlparse(DOWNLOAD_PORTAL_URL).hostname
        assert host is not None

        # Exactly what the integration would use without download_portal_ssl.
        context = create_client_context(alpn_protocols=SSL_ALPN_HTTP11)

        try:
            with (
                socket.create_connection((host, 443), timeout=30) as sock,
                context.wrap_socket(sock, server_hostname=host),
            ):
                pass
        except ssl.SSLCertVerificationError:
            # Still broken: the workaround is still earning its place.
            return
        except OSError as err:
            pytest.skip(f"{host} is unreachable, cannot tell either way: {err}")

        pytest.fail(
            f"{host} now verifies without the pinned CA bundle, so the "
            "workaround is obsolete. Delete custom_components/luxtronik2/"
            "download_portal_ssl.py, drop the ssl= argument and this test, "
            "and close https://github.com/BenPru/luxtronik/issues/783."
        )
