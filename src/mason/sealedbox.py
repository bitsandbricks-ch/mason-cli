"""libsodium's sealed box (crypto_box_seal) in plain Python, for GitHub Actions secrets.

GitHub takes a secret only encrypted with the repo's (or environment's) public key: X25519 for the key
exchange, XSalsa20-Poly1305 for the box, the nonce a BLAKE2b hash of both public keys. Secrets are
small, so plain Python is fast enough, and mason needs no compiled dependency for it. `open_box` is
here for the tests (and to check a box round-trips); GitHub never gives a private key out.
"""

from __future__ import annotations

import hashlib
import os
import struct

P = 2**255 - 19
A24 = 121665


# ── X25519 (RFC 7748) ────────────────────────────────────────────────────────


def _clamp(k: bytes) -> int:
    b = bytearray(k)
    b[0] &= 248
    b[31] &= 127
    b[31] |= 64
    return int.from_bytes(b, "little")


def x25519(scalar: bytes, point: bytes) -> bytes:
    k = _clamp(scalar)
    u = int.from_bytes(point, "little") & ((1 << 255) - 1)
    x1, x2, z2, x3, z3, swap = u, 1, 0, u, 1, 0
    for t in reversed(range(255)):
        bit = (k >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        a, b = (x2 + z2) % P, (x2 - z2) % P
        aa, bb = a * a % P, b * b % P
        e = (aa - bb) % P
        c, d = (x3 + z3) % P, (x3 - z3) % P
        da, cb = d * a % P, c * b % P
        x3 = (da + cb) ** 2 % P
        z3 = x1 * (da - cb) ** 2 % P
        x2 = aa * bb % P
        z2 = e * (aa + A24 * e) % P
    if swap:
        x2, z2 = x3, z3
    return (x2 * pow(z2, P - 2, P) % P).to_bytes(32, "little")


def public_key(secret: bytes) -> bytes:
    return x25519(secret, (9).to_bytes(32, "little"))


# ── Salsa20 / HSalsa20 / XSalsa20 ────────────────────────────────────────────

SIGMA = b"expand 32-byte k"


def _rounds(x: list[int]) -> list[int]:
    def r(a, b):
        return ((a << b) | (a >> (32 - b))) & 0xFFFFFFFF

    x = list(x)
    for _ in range(10):
        for a, b, c, d in ((0, 4, 8, 12), (5, 9, 13, 1), (10, 14, 2, 6), (15, 3, 7, 11),
                           (0, 1, 2, 3), (5, 6, 7, 4), (10, 11, 8, 9), (15, 12, 13, 14)):
            x[b] ^= r((x[a] + x[d]) & 0xFFFFFFFF, 7)
            x[c] ^= r((x[b] + x[a]) & 0xFFFFFFFF, 9)
            x[d] ^= r((x[c] + x[b]) & 0xFFFFFFFF, 13)
            x[a] ^= r((x[d] + x[c]) & 0xFFFFFFFF, 18)
    return x


def _state(key: bytes, sixteen: bytes) -> list[int]:
    c, k, n = struct.unpack("<4I", SIGMA), struct.unpack("<8I", key), struct.unpack("<4I", sixteen)
    return [c[0], k[0], k[1], k[2], k[3], c[1], n[0], n[1], n[2], n[3], c[2], k[4], k[5], k[6], k[7], c[3]]


def hsalsa20(key: bytes, nonce16: bytes) -> bytes:
    x = _rounds(_state(key, nonce16))
    return struct.pack("<8I", *(x[i] for i in (0, 5, 10, 15, 6, 7, 8, 9)))


def salsa20_stream(key: bytes, nonce8: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        s = _state(key, nonce8 + struct.pack("<Q", counter))
        x = _rounds(s)
        out += struct.pack("<16I", *((a + b) & 0xFFFFFFFF for a, b in zip(x, s)))
        counter += 1
    return bytes(out[:length])


# ── Poly1305 ─────────────────────────────────────────────────────────────────


def poly1305(key: bytes, msg: bytes) -> bytes:
    r = int.from_bytes(key[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:], "little")
    p, acc = (1 << 130) - 5, 0
    for i in range(0, len(msg), 16):
        block = msg[i:i + 16] + b"\x01"
        acc = (acc + int.from_bytes(block, "little")) * r % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


# ── the box ──────────────────────────────────────────────────────────────────


def _secretbox(msg: bytes, nonce: bytes, key: bytes) -> bytes:
    stream = salsa20_stream(hsalsa20(key, nonce[:16]), nonce[16:], 32 + len(msg))
    cipher = bytes(a ^ b for a, b in zip(msg, stream[32:]))
    return poly1305(stream[:32], cipher) + cipher


def _secretbox_open(box: bytes, nonce: bytes, key: bytes) -> bytes:
    tag, cipher = box[:16], box[16:]
    stream = salsa20_stream(hsalsa20(key, nonce[:16]), nonce[16:], 32 + len(cipher))
    if poly1305(stream[:32], cipher) != tag:
        raise ValueError("the box doesn't open: wrong key or a damaged message")
    return bytes(a ^ b for a, b in zip(cipher, stream[32:]))


def _shared(secret: bytes, public: bytes) -> bytes:
    return hsalsa20(x25519(secret, public), bytes(16))


def _nonce(eph_pk: bytes, pk: bytes) -> bytes:
    return hashlib.blake2b(eph_pk + pk, digest_size=24).digest()


def seal(message: bytes, recipient: bytes, ephemeral: bytes | None = None) -> bytes:
    """crypto_box_seal: only the holder of `recipient`'s private key can open it."""
    if len(recipient) != 32:
        raise ValueError("a public key has 32 bytes")
    esk = ephemeral or os.urandom(32)
    epk = public_key(esk)
    return epk + _secretbox(message, _nonce(epk, recipient), _shared(esk, recipient))


def open_box(box: bytes, secret: bytes) -> bytes:
    """crypto_box_seal_open (tests)."""
    epk, pk = box[:32], public_key(secret)
    return _secretbox_open(box[32:], _nonce(epk, pk), _shared(secret, epk))
