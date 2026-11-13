"""Копия восстанавливает точные байты; подмена, усечение и неправильный ключ отклоняются."""

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from teamtime.services import fund_backup


def test_full_backup_roundtrip_and_no_plaintext_in_delivery(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    payload = os.urandom(80_000)
    (source / "database.dump").write_bytes(payload)
    (source / "settings.txt").write_text("fictional-configuration-secret", encoding="utf-8")
    key = tmp_path / "backup.key"
    key.write_bytes(base64.b64encode(os.urandom(32)))
    monkeypatch.setattr(fund_backup, "CHUNK", 8192)
    monkeypatch.setattr(fund_backup, "DELIVERY_PART", 16384)
    destination = tmp_path / "encrypted"
    fund_backup.pack(source, destination, key)
    parts = list(destination.glob("*.part*"))
    assert len(parts) > 1
    assert all(b"fictional-configuration-secret" not in p.read_bytes() for p in parts)
    restored = tmp_path / "restored"
    fund_backup.unpack(destination, restored, key)
    assert (restored / "database.dump").read_bytes() == payload
    assert (restored / "settings.txt").read_text(
        encoding="utf-8"
    ) == "fictional-configuration-secret"
    with pytest.raises(ValueError, match="уже существует"):
        fund_backup.unpack(destination, restored, key)


@pytest.mark.parametrize("damage", ["wrong_key", "truncated", "changed", "extra", "reordered"])
def test_aead_rejects_incomplete_or_modified_stream(tmp_path, monkeypatch, damage):
    monkeypatch.setattr(fund_backup, "CHUNK", 16)
    source = tmp_path / "source"
    source.write_bytes(b"some non-private content" * 3)
    encrypted = tmp_path / "encrypted"
    key = os.urandom(32)
    fund_backup.encrypt(source, encrypted, key)
    payload = encrypted.read_bytes()
    if damage == "wrong_key":
        key = os.urandom(32)
    elif damage == "truncated":
        payload = payload[:-21]
    elif damage == "changed":
        payload = payload[:40] + bytes([payload[40] ^ 1]) + payload[41:]
    elif damage == "reordered":
        start = len(fund_backup.MAGIC) + 8
        first = payload[start : start + 37]
        second = payload[start + 37 : start + 74]
        payload = payload[:start] + second + first + payload[start + 74 :]
    else:
        payload += b"unexpected"
    encrypted.write_bytes(payload)
    with pytest.raises((ValueError, InvalidTag)):
        fund_backup.decrypt(encrypted, tmp_path / "output", key)


def test_key_cannot_be_included_in_own_archive(tmp_path):
    (tmp_path / "database.dump").write_bytes(b"dump")
    (tmp_path / "backup.key").write_bytes(base64.b64encode(os.urandom(32)))
    with pytest.raises(ValueError, match="Ключ нельзя"):
        fund_backup.pack(tmp_path, tmp_path / "out", tmp_path / "backup.key")
