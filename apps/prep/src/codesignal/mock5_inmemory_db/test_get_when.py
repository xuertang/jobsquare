"""Level 4 variant -- point-in-time reads via `get_when`.

Run: ICF_IMPL=attempt python3 -m pytest -q test_get_when.py
"""

import importlib
import os

import pytest

_impl = importlib.import_module(os.environ.get("ICF_IMPL", "attempt"))
InMemoryDB = _impl.InMemoryDB


# --- the core promise: overwrites do not destroy the past -----------------

@pytest.mark.level4
def test_reads_the_value_in_force_at_that_instant():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.set(20, "wallet_a", "balance", "250")
    db.set(30, "wallet_a", "balance", "400")
    assert db.get_when(99, "wallet_a", "balance", 10) == "100"
    assert db.get_when(99, "wallet_a", "balance", 15) == "100"
    assert db.get_when(99, "wallet_a", "balance", 20) == "250"
    assert db.get_when(99, "wallet_a", "balance", 29) == "250"
    assert db.get_when(99, "wallet_a", "balance", 30) == "400"


@pytest.mark.level4
def test_before_the_first_write_is_a_miss():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    assert db.get_when(99, "wallet_a", "balance", 9) is None


@pytest.mark.level4
def test_get_is_get_when_asked_about_the_present():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.set(20, "wallet_a", "balance", "250")
    for now in (10, 15, 20, 50):
        assert db.get(now, "wallet_a", "balance") == db.get_when(
            now, "wallet_a", "balance", now
        )


# --- misses ---------------------------------------------------------------

@pytest.mark.level4
def test_missing_key_and_missing_field_are_both_misses():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    assert db.get_when(99, "wallet_zzz", "balance", 10) is None
    assert db.get_when(99, "wallet_a", "currency", 10) is None


@pytest.mark.level4
def test_empty_string_is_a_hit_not_a_miss():
    db = InMemoryDB()
    db.set(10, "wallet_a", "note", "")
    assert db.get_when(99, "wallet_a", "note", 10) == ""


# --- deletion is a tombstone, not an erasure ------------------------------

@pytest.mark.level4
def test_delete_hides_the_field_only_from_that_instant_on():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.delete(20, "wallet_a", "balance")
    assert db.get_when(99, "wallet_a", "balance", 15) == "100"   # before the delete
    assert db.get_when(99, "wallet_a", "balance", 20) is None    # at the delete
    assert db.get_when(99, "wallet_a", "balance", 25) is None    # after it


@pytest.mark.level4
def test_a_field_rewritten_after_deletion_has_a_gap_in_its_history():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.delete(20, "wallet_a", "balance")
    db.set(30, "wallet_a", "balance", "900")
    assert db.get_when(99, "wallet_a", "balance", 15) == "100"
    assert db.get_when(99, "wallet_a", "balance", 25) is None
    assert db.get_when(99, "wallet_a", "balance", 35) == "900"


# --- TTL is evaluated at at_ts, not at timestamp --------------------------

@pytest.mark.level4
def test_expiry_is_judged_at_the_queried_instant():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "promo", "SAVE20", 100)  # alive [10, 110)
    assert db.get_when(500, "wallet_a", "promo", 10) == "SAVE20"
    assert db.get_when(500, "wallet_a", "promo", 109) == "SAVE20"
    assert db.get_when(500, "wallet_a", "promo", 110) is None  # boundary is exclusive
    assert db.get_when(500, "wallet_a", "promo", 111) is None


@pytest.mark.level4
def test_an_expired_field_is_still_readable_at_an_instant_when_it_was_alive():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "promo", "SAVE20", 5)  # dead from 15
    assert db.get(1000, "wallet_a", "promo") is None       # gone in the present
    assert db.get_when(1000, "wallet_a", "promo", 12) == "SAVE20"


@pytest.mark.level4
def test_deleting_an_expired_field_does_not_erase_its_live_past():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "promo", "SAVE20", 5)
    assert db.delete(60, "wallet_a", "promo") is False  # already dead -> False
    assert db.get_when(99, "wallet_a", "promo", 12) == "SAVE20"


@pytest.mark.level4
def test_ttl_overwritten_by_a_permanent_set_keeps_both_eras_readable():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "promo", "SAVE20", 5)
    db.set(30, "wallet_a", "promo", "PERMANENT")
    assert db.get_when(99, "wallet_a", "promo", 12) == "SAVE20"
    assert db.get_when(99, "wallet_a", "promo", 20) is None      # expired, not yet reset
    assert db.get_when(99, "wallet_a", "promo", 30) == "PERMANENT"
    assert db.get_when(9999, "wallet_a", "promo", 9999) == "PERMANENT"


# --- same-timestamp and future-instant edges ------------------------------

@pytest.mark.level4
def test_two_writes_at_the_same_instant_resolve_to_the_later_one():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.set(10, "wallet_a", "balance", "250")
    assert db.get_when(99, "wallet_a", "balance", 10) == "250"


@pytest.mark.level4
def test_a_future_instant_reads_the_same_as_the_present():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    assert db.get_when(20, "wallet_a", "balance", 10_000) == "100"


@pytest.mark.level4
def test_asking_later_does_not_change_what_was_true():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.set(20, "wallet_a", "balance", "250")
    early = db.get_when(20, "wallet_a", "balance", 15)
    late = db.get_when(10_000, "wallet_a", "balance", 15)
    assert early == late == "100"


@pytest.mark.level4
def test_fields_and_keys_have_independent_histories():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.set(10, "wallet_a", "status", "active")
    db.set(10, "wallet_b", "balance", "999")
    db.set(20, "wallet_a", "balance", "250")
    assert db.get_when(99, "wallet_a", "balance", 15) == "100"
    assert db.get_when(99, "wallet_a", "status", 15) == "active"
    assert db.get_when(99, "wallet_b", "balance", 15) == "999"


# --- interaction with the retained backup/restore -------------------------

@pytest.mark.level4
def test_history_survives_a_restore():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.backup(20)
    db.set(30, "wallet_a", "balance", "250")
    db.restore(40, 20)
    assert db.get(40, "wallet_a", "balance") == "100"          # rolled back
    assert db.get_when(99, "wallet_a", "balance", 30) == "250" # the past is intact


@pytest.mark.level4
def test_restore_tombstones_records_created_after_the_backup():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.backup(20)
    db.set(30, "wallet_b", "balance", "999")
    db.restore(40, 20)
    assert db.get(40, "wallet_b", "balance") is None           # gone in the present
    assert db.get_when(99, "wallet_b", "balance", 35) == "999" # but it did exist
