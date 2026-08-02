"""TOTP primitive tests."""

from services import totp


def test_generate_secret_is_base32():
    secret = totp.generate_secret()
    assert secret
    # base32 alphabet only (no padding).
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)


def test_current_code_verifies():
    secret = totp.generate_secret()
    code = totp.totp_now(secret)
    assert totp.verify(secret, code)


def test_wrong_code_rejected():
    secret = totp.generate_secret()
    code = totp.totp_now(secret)
    wrong = "000000" if code != "000000" else "111111"
    assert not totp.verify(secret, wrong)


def test_code_outside_window_rejected():
    secret = totp.generate_secret()
    at = 1_000_000
    code_now = totp.totp_now(secret, at=at)
    # A code from 5 steps (150s) earlier is outside the +/-1 window.
    assert not totp.verify(secret, code_now, at=at + 5 * 30, window=1)


def test_adjacent_window_accepted():
    secret = totp.generate_secret()
    at = 1_000_000
    prev_code = totp.totp_now(secret, at=at - 30)
    assert totp.verify(secret, prev_code, at=at, window=1)


def test_provisioning_uri_shape():
    secret = totp.generate_secret()
    uri = totp.provisioning_uri(secret, "operator@nha.gov.pk", issuer="ATIS")
    assert uri.startswith("otpauth://totp/")
    assert "secret=" in uri and "issuer=ATIS" in uri
