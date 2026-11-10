"""The sealed box GitHub secrets need: RFC 7748's X25519 vector, round trips, and libsodium itself."""

from __future__ import annotations

import pytest

from mason import sealedbox as sb


def test_x25519_rfc7748():
    k = bytes.fromhex("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4")
    u = bytes.fromhex("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")
    assert sb.x25519(k, u).hex() == "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"


def test_round_trip_and_tamper():
    secret = bytes(range(1, 33))
    for msg in (b"", b"x", "grüezi ".encode() * 40):
        box = sb.seal(msg, sb.public_key(secret))
        assert len(box) == 32 + 16 + len(msg)
        assert sb.open_box(box, secret) == msg
    box = bytearray(sb.seal(b"token", sb.public_key(secret)))
    box[-1] ^= 1
    with pytest.raises(ValueError):
        sb.open_box(bytes(box), secret)


def test_libsodium_opens_it():
    nacl = pytest.importorskip("nacl.public")
    key = nacl.PrivateKey.generate()
    box = sb.seal(b"s3cret", bytes(key.public_key))
    assert nacl.SealedBox(key).decrypt(box) == b"s3cret"
    assert sb.open_box(nacl.SealedBox(key.public_key).encrypt(b"back"), bytes(key)) == b"back"
