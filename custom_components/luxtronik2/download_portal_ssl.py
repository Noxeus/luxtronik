"""SSL context for the Alpha Innotec / Nibe firmware download portal.

`www.heatpump24.com` serves an **incomplete TLS certificate chain**: it presents
only its own leaf certificate and omits the two CA certificates that link it to a
publicly trusted root. Reproduce with::

    openssl s_client -connect www.heatpump24.com:443 -servername www.heatpump24.com
    # Verify return code: 21 (unable to verify the first certificate)

The chain the server *should* send::

    heatpump24.com                    <- sent by the server
      +- Telia RSA OV CA v4           <- NOT sent, not in the default CA store
          +- Telia RSA TLS Root CA v3 <- NOT sent, not in the default CA store
              +- Telia Root CA v2     <- publicly trusted, present everywhere

Web browsers hide this because they compensate for missing intermediates (Firefox
preloads every intermediate known to CCADB, Chrome and Edge fetch them via the
certificate's AIA extension). Python/OpenSSL does neither, so the firmware update
check fails with ``CERTIFICATE_VERIFY_FAILED`` while the portal opens fine in a
browser.

As a workaround we pin the two missing CA certificates and use them *only* for
requests to the download portal. Certificate verification stays fully enabled --
this closes the chain, it does not skip validation.

Both certificates were verified **offline** to chain up to ``Telia Root CA v2`` in
the Mozilla/certifi store before being pinned here. Note that ``cadata`` installs
them as trust anchors, so at runtime OpenSSL may terminate the path at a pinned
anchor without walking up to that public root. The practical consequence is that
the revocation status of a pinned CA is never consulted on this context: if Telia
revoked one of them, this context would keep trusting it. Bounded to one host,
with hostname verification intact.

Both intermediates are pinned deliberately: if the portal is only partially fixed
(the common case of adding just the issuing CA to the web server), the chain would
still dead-end at ``Telia RSA TLS Root CA v3``, which is not in the default store
either.

**This module can be deleted once Nibe serves a complete chain again** -- see
https://github.com/BenPru/luxtronik/issues/783. Source of the pinned certificates,
taken from the AIA extension of the portal's own certificate:

* http://cps.trust.telia.com/teliarsaovcav4.cer
* http://cps.trust.telia.com/teliarsatlsrootcav3.cer
"""

# region Imports
from __future__ import annotations

import ssl
from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.util.ssl import SSL_ALPN_HTTP11, create_client_context

from .const import LOGGER

# endregion Imports

# CN=Telia RSA OV CA v4, O=Telia Company AB, C=SE   (expires 2048-05-23)
# CN=Telia RSA TLS Root CA v3, O=Telia Company AB, C=SE  (expires 2043-11-28)
DOWNLOAD_PORTAL_CA_BUNDLE: Final = """\
-----BEGIN CERTIFICATE-----
MIIGbTCCBFWgAwIBAgIPAZPeTwwJQRn7bMtN44sDMA0GCSqGSIb3DQEBDAUAMEsx
CzAJBgNVBAYTAlNFMRkwFwYDVQQKDBBUZWxpYSBDb21wYW55IEFCMSEwHwYDVQQD
DBhUZWxpYSBSU0EgVExTIFJvb3QgQ0EgdjMwHhcNMjQxMjE5MDk0NDUwWhcNNDgw
NTIzMTAwMDAwWjBFMQswCQYDVQQGEwJTRTEZMBcGA1UECgwQVGVsaWEgQ29tcGFu
eSBBQjEbMBkGA1UEAwwSVGVsaWEgUlNBIE9WIENBIHY0MIICIjANBgkqhkiG9w0B
AQEFAAOCAg8AMIICCgKCAgEAyevbfqI/MpHiVKNeyMb56lR5NQu4Vi0l7lyThYVh
lTqQzATHvZVm+Pdj6gfhuY1wyRnbkE+bkjdq58rpqn0p2j/4GHqAsas0LJLkS2A4
LwmxJ+DHr1tJOonMbCwTbwKRdX54LwwDGNw0ShgVWSfI5nNDwg8HhRDFESFFH2n1
WwmJlu5JQmqK6nb0gB+nGGYMGJzdGNQ5h6PW8TKG2egE1RL79IZ0jeA9Lo65CClC
JK5bkGqkR0lrfEETyQZBoZp06c4T2XnX+2yUZoIkk/yy8C/mrMv0ilbcR8c8s9lq
3cKFz15HjS/7L3mUyDqSOOObUr4cSJBrR8fHIHUEfiEv+rKE3iIURWdrJ2ANFgot
d/H9vbe5cBnShiakQN2lKmyEI9pN9Gt0QS12XmlOe4h4q2En6ERdJi3CiLO15tY3
6B6guuDpwvJtMhlVduw8u+2/l3gkTwnniYmyG8pjAtEEUJtCAWc/5hHaGqaVwwBK
vbrqG5SNPeCuKBaIQcVNlIV00+WzTSRTXevnMc0UUiYyDh/qY0Qlg5Xked8P0fuR
xFhUDlyISUqB3iiNS4YsfJMrkvC5LSthTEMyqo09IT21r8GIRhCtcbRWLexTnil5
lwtZjVHJTNrpn1bd6qbQG+md8k2wBkvatBL+oRgM5H3XhJ8U7YkCwAQNhUjURDAi
omECAwEAAaOCAVIwggFOMB8GA1UdIwQYMBaAFLDHqdLdsihWcwSUjBRcSG83UpKo
MB0GA1UdDgQWBBRV2aNwgnw836jT+d5/BdG6Zku/7TAOBgNVHQ8BAf8EBAMCAQYw
EQYDVR0gBAowCDAGBgRVHSAAMBIGA1UdEwEB/wQIMAYBAf8CAQAwRwYDVR0fBEAw
PjA8oDqgOIY2aHR0cDovL2h0dHBjcmwudHJ1c3QudGVsaWEuY29tL3RlbGlhcnNh
dGxzcm9vdGNhdjMuY3JsMBMGA1UdJQQMMAoGCCsGAQUFBwMBMHcGCCsGAQUFBwEB
BGswaTA+BggrBgEFBQcwAoYyaHR0cDovL2Nwcy50cnVzdC50ZWxpYS5jb20vdGVs
aWFyc2F0bHNyb290Y2F2My5jZXIwJwYIKwYBBQUHMAGGG2h0dHA6Ly9vY3NwLnRy
dXN0LnRlbGlhLmNvbTANBgkqhkiG9w0BAQwFAAOCAgEAjKRIbcTHtBF8nTXO8JMn
toxF0CSvUFVpTXN2AeF1BRequPvdCy5zteVKnnx5c4lBLgMLasrGH6wKbOdkVTbq
fNGVNF81R4/AXhqNHPyGpqpb9zMWTYMtswv3k3FpYADypH1Z4BLCIh8mqBnO5dP0
m16sa075V5MBvB506jixKuB/oZRTaLdBlFclB6VZZtEt/zVSsgY1BXkJIPKJ5hKL
9AWnCq1XpObnQEnvOgwudD/8ohq5H+OsoY3GhWY6dy7MNoK1Sc/p0FL0UOqlgDcw
0ze58dD8BUmrf/sZD++4nP8CZ53EzvTv+hIYqTYsOe8Zmp62osGvcf1aOLnGmV0Z
QWxQR7WfiS42DQ+l3w9b8n0i7+zl9Kp3ONlzkQuUwR/bOUwY1ZhaXGBs4/5C0swv
Zm76yxPda9gJ8EB1AJzqLdqG96KCVaUmZPWcPr52b/h8XPYTlNqpvuacvYD9K//p
7bJ5Hqdp/G/rvFTeLhRb/jdVwGE83CXRLqRBBwp25NgwvfTCa4fPCP3uY6g+1C7r
MqcWxh3+onbnrFY38FfQt5/u0NfCO4PsgeemqPDqBFwu+SmYCLUxm83+p1pvtlA0
ZzYCJrKF3/9Gq8rDdUSrDqUEmjGz03cNABRbxnEVOBNTDU/dkCydzn4d8Vwc8CaQ
OSD0WKQ4Ru9c5KCWAB1a5qo=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIGXTCCBEWgAwIBAgIPAZPeF/aL5o1El0fggo9WMA0GCSqGSIb3DQEBDAUAMEQx
CzAJBgNVBAYTAkZJMRowGAYDVQQKDBFUZWxpYSBGaW5sYW5kIE95ajEZMBcGA1UE
AwwQVGVsaWEgUm9vdCBDQSB2MjAeFw0yNDEyMTkwODQzNTVaFw00MzExMjgxMDAw
MDBaMEsxCzAJBgNVBAYTAlNFMRkwFwYDVQQKDBBUZWxpYSBDb21wYW55IEFCMSEw
HwYDVQQDDBhUZWxpYSBSU0EgVExTIFJvb3QgQ0EgdjMwggIiMA0GCSqGSIb3DQEB
AQUAA4ICDwAwggIKAoICAQCxXz0obX2EJ/hLUW+TwPdPIMRGGZy/HwXsqZvhYBPH
eKN7WJ3cofFETRMqZw0JsBDntu8cURhriFHaXbRWNVp0TGo5b7aV330xsSI76NFU
7P4FvEvEmeYbAKoj4F+5OONVF4PGzGNC+OAGwKVo7+ybmLvSeVlxYZG0iS9YMrc0
2RPlG3Bdz87w1MVWltSpPpxGMiPeiUBuVH6VF/gV/Lmj5D19puNif1n1LiK2u4SV
wQV/0uOTt/B1PJxP+u8lb3D8HcbZrevR//Nc05Wu4gFyoTqmRKiykAJTZsbjZ9gq
tsz8Zaenu76n0WvPiNo3Clvhge4R5LwGtq01w/xfraNci+8ofGWwwMkKdvhTwnMU
4uxTqaiFVjnwF1mu+LQaT1Q66qaCgbp2yQeiSyNlOUrrUP8ifOYSgDXIBgkUNXKy
NHENQ671wDAA1uqarvtYgUvoGmdmBWo+0x8brA3wGtMp1qm+KVWxhHn0EWAiwBUE
zGsaH5b5By+Ylp9SkBK+UCsq9UbYUjiLo+IuNIFPT7oXoRAutip585AX98E0Rdv6
eNRDRJRWsCq0fhj46MIj9rj8klCmnF56ZlxDRJRKGCIjkAznEc7mLJpStONgfjPF
TP2P7UURsMf/Gmy2vWBcHKSym6n6FFNolxsD5Rukmq1Zmd0A910ma3pglD51TekO
7wIDAQABo4IBQzCCAT8wHwYDVR0jBBgwFoAUcqzkM3mqRYf2/awdntbHL4bYJDkw
HQYDVR0OBBYEFLDHqdLdsihWcwSUjBRcSG83UpKoMA4GA1UdDwEB/wQEAwIBBjAR
BgNVHSAECjAIMAYGBFUdIAAwDwYDVR0TAQH/BAUwAwEB/zBBBgNVHR8EOjA4MDag
NKAyhjBodHRwOi8vaHR0cGNybC50cnVzdC50ZWxpYS5jb20vdGVsaWFyb290Y2F2
Mi5jcmwwEwYDVR0lBAwwCgYIKwYBBQUHAwEwcQYIKwYBBQUHAQEEZTBjMCcGCCsG
AQUFBzABhhtodHRwOi8vb2NzcC50cnVzdC50ZWxpYS5jb20wOAYIKwYBBQUHMAKG
LGh0dHA6Ly9jcHMudHJ1c3QudGVsaWEuY29tL3RlbGlhcm9vdGNhdjIuY2VyMA0G
CSqGSIb3DQEBDAUAA4ICAQAT4SS0u5ClKu1GEu8h+cTDPYXUNFLFV39Bw6DwsMTm
86aVP+wsqJC1tCaZ7b/UAIP9+NXxqSkHQG8x+ola4OACGZszvPZVCjhgpHJ2LGW/
/9lgA+Nj5rvZQ82zPhXMxbVdINvnc+hgBnTNwJeb8Pg2IHOfnInkCXkZSBDXeiqo
4gR+CAvuvCVmONv8uE5S2NlpKGc15F1qkEGWvYiOOTtokemzkPv30XPZvYbpput+
rPTMmlZFV/HE1ucbZOtiV2yq68oaSeGnPo69qequyOju/K3J8nBFZXy/VrS34/0p
iDHqT9fLNnIxGIObo3KSVJRpFkZgxACtNpEUhv4LqnKiradLDC+Z85smkQaJp9O7
pfGhC2nJ5qZkkqVqTkzPWTq5mD5e3f01co8dGphsfqFlOiSjehqx4MRooEiZNOTf
WXN7omD2vNbugOX2xOjl6wSszi3er39YJyKPG11nKFkZNHRngohgvfPwnwszBw3z
e4sF0ALGbvTWCNt5gzYQve3JYkhlVplvJsLeAg4wWZ7gw8WbzKDUbINI/2bA7GXY
4vneJAlBss8EP635laezoww9Ym6v/jElGcFD6AlIgrIYQjBGl8mneS+eEuER2xLZ
5I4eAX4i7BLX58gmpffd79bo5445ehUl4hGVlbcZagelzszEWeXCH2jaDy2/a2Pz
Bg==
-----END CERTIFICATE-----
"""

_SSL_CONTEXT: ssl.SSLContext | None = None
_BUILD_FAILED = False


def _create_ssl_context() -> ssl.SSLContext:
    """Build the download portal SSL context. Blocking, run in an executor.

    Built with `create_client_context()` so it honours the same CA configuration
    as every other Home Assistant request (REQUESTS_CA_BUNDLE, else certifi).
    Never `client_context()`: that one is process wide and cached, and loading
    the pin into it would leak these trust anchors to every client in HA.
    """
    context = create_client_context(alpn_protocols=SSL_ALPN_HTTP11)
    context.load_verify_locations(cadata=DOWNLOAD_PORTAL_CA_BUNDLE)
    return context


async def async_get_download_portal_ssl_context(
    hass: HomeAssistant,
) -> ssl.SSLContext | None:
    """Return the cached SSL context for download portal requests.

    Returns None if the context cannot be built, so the caller can fall back to
    the default context instead of failing outright.
    """
    global _SSL_CONTEXT, _BUILD_FAILED

    if _SSL_CONTEXT is None:
        # Two config entries polling at once can both build a context here. That
        # is accepted: last write wins and both contexts are equivalent.
        try:
            # create_client_context() loads the CA store from disk.
            _SSL_CONTEXT = await hass.async_add_executor_job(_create_ssl_context)
        except Exception:
            # Report the first failure in full, then stay quiet: this runs on
            # every poll and repeating the traceback would be the very log spam
            # this module exists to avoid.
            if _BUILD_FAILED:
                LOGGER.debug("Could not build the download portal SSL context")
            else:
                _BUILD_FAILED = True
                LOGGER.warning(
                    "Could not build the download portal SSL context", exc_info=True
                )
            return None
        _BUILD_FAILED = False

    return _SSL_CONTEXT
