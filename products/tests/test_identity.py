import time

import pytest

from supportkit.identity import IdentityError, sign, verify


def test_round_trip():
    assert verify(sign(7)) == 7


@pytest.mark.parametrize("token", [None, "", "7", "7.abc.def", "x.1.sig", "7.1.2.3"])
def test_malformed(token):
    with pytest.raises(IdentityError):
        verify(token)


def test_customer_swapped_in_signed_token():
    _, expires, signature = sign(7).split(".")
    with pytest.raises(IdentityError, match="signature"):
        verify(f"8.{expires}.{signature}")


def test_signed_with_another_secret(monkeypatch):
    monkeypatch.setenv("SUPPORTKIT_SECRET", "attacker")
    token = sign(7)
    monkeypatch.setenv("SUPPORTKIT_SECRET", "test-secret")
    with pytest.raises(IdentityError, match="signature"):
        verify(token)


def test_expired():
    with pytest.raises(IdentityError, match="expired"):
        verify(sign(7, ttl=-1))


def test_no_secret_configured(monkeypatch):
    monkeypatch.delenv("SUPPORTKIT_SECRET")
    with pytest.raises(IdentityError, match="SUPPORTKIT_SECRET"):
        verify(f"7.{int(time.time()) + 60}.sig")
