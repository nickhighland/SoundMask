from __future__ import annotations

from app.auth import hash_password, verify_password


def test_hash_password_uses_pbkdf2_sha256_for_new_passwords():
    hashed = hash_password("soundmask-admin-password")

    assert hashed.startswith("$pbkdf2-sha256$")
    assert verify_password("soundmask-admin-password", hashed) is True


def test_verify_password_rejects_empty_hash():
    assert verify_password("anything", "") is False
