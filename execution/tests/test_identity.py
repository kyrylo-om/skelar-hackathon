import time

import pytest

from execution.identity import IdentityError, sign, verify
from execution.products import check_path


def test_round_trip():
    assert verify(sign("shopx", "s-201")) == ("shopx", "s-201")


@pytest.mark.parametrize(
    "token", [None, "", "shopx.s-201", "shopx.s-201.abc.sig", "sh op.s-201.1.sig", "a.b.c.d.e"]
)
def test_malformed(token):
    with pytest.raises(IdentityError):
        verify(token)


@pytest.mark.parametrize("swap", [("shopx", "s-202"), ("cloudbox", "s-201")])
def test_tenant_or_customer_swapped_in_a_signed_token(swap):
    _, _, expires, signature = sign("shopx", "s-201").split(".")
    with pytest.raises(IdentityError, match="signature"):
        verify(f"{swap[0]}.{swap[1]}.{expires}.{signature}")


def test_expired():
    with pytest.raises(IdentityError, match="expired"):
        verify(sign("shopx", "s-201", ttl=-1))


def test_no_secret_configured(monkeypatch):
    monkeypatch.delenv("EXECUTION_SECRET")
    with pytest.raises(IdentityError, match="EXECUTION_SECRET"):
        verify(f"shopx.s-201.{int(time.time()) + 60}.sig")


def test_ids_are_plain():
    with pytest.raises(ValueError):
        sign("shopx", "s-201.extra")


@pytest.mark.parametrize("path", ["/orders", "/orders/1042", "/payments?limit=5", "/a/b-c_d.e"])
def test_plain_paths_pass(path):
    assert check_path(path) == path
