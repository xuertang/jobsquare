"""Test suite for ICF Mock 5 -- InMemoryDB.

Run everything:        python3 -m pytest -q
Run one level:         python3 -m pytest -q -m level1
Test your own attempt: ICF_IMPL=attempt python3 -m pytest -q -m level1
"""

import importlib
import os

import pytest

_impl = importlib.import_module(os.environ.get("ICF_IMPL", "solution"))
InMemoryDB = _impl.InMemoryDB


# ======================================================================
# Level 1 -- core operations
# ======================================================================


@pytest.mark.level1
def test_set_then_get_returns_the_value():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    assert db.get(2, "wallet_a", "balance") == "100"


@pytest.mark.level1
def test_set_returns_none():
    db = InMemoryDB()
    assert db.set(1, "wallet_a", "balance", "100") is None


@pytest.mark.level1
def test_get_on_a_missing_key_returns_none():
    db = InMemoryDB()
    assert db.get(1, "ghost", "balance") is None


@pytest.mark.level1
def test_get_on_a_missing_field_of_an_existing_key_returns_none():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    assert db.get(2, "wallet_a", "status") is None


@pytest.mark.level1
def test_set_overwrites_an_existing_field():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.set(2, "wallet_a", "balance", "250")
    assert db.get(3, "wallet_a", "balance") == "250"


@pytest.mark.level1
def test_delete_existing_field_returns_true_and_hides_it():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    assert db.delete(2, "wallet_a", "balance") is True
    assert db.get(3, "wallet_a", "balance") is None


@pytest.mark.level1
def test_delete_on_a_missing_key_returns_false():
    db = InMemoryDB()
    assert db.delete(1, "ghost", "balance") is False


@pytest.mark.level1
def test_delete_on_a_missing_field_of_an_existing_key_returns_false():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    assert db.delete(2, "wallet_a", "status") is False
    assert db.get(3, "wallet_a", "balance") == "100"


@pytest.mark.level1
def test_delete_is_not_idempotent_in_its_return_value():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    assert db.delete(2, "wallet_a", "balance") is True
    assert db.delete(3, "wallet_a", "balance") is False


@pytest.mark.level1
def test_set_after_delete_recreates_the_field():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.delete(2, "wallet_a", "balance")
    db.set(3, "wallet_a", "balance", "999")
    assert db.get(4, "wallet_a", "balance") == "999"


@pytest.mark.level1
def test_fields_of_one_record_are_independent():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.set(1, "wallet_a", "status", "active")
    db.delete(2, "wallet_a", "balance")
    assert db.get(3, "wallet_a", "balance") is None
    assert db.get(3, "wallet_a", "status") == "active"


@pytest.mark.level1
def test_records_are_independent_of_each_other():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.set(1, "wallet_b", "balance", "200")
    db.delete(2, "wallet_a", "balance")
    assert db.get(3, "wallet_a", "balance") is None
    assert db.get(3, "wallet_b", "balance") == "200"


@pytest.mark.level1
def test_empty_string_value_is_a_hit_not_a_miss():
    db = InMemoryDB()
    db.set(1, "wallet_a", "note", "")
    assert db.get(2, "wallet_a", "note") == ""
    assert db.get(2, "wallet_a", "note") is not None


@pytest.mark.level1
def test_values_persist_across_later_timestamps():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    assert db.get(10**9, "wallet_a", "balance") == "100"


# ======================================================================
# Level 2 -- scan and scan_by_prefix
# ======================================================================


def _seed_wallet() -> "InMemoryDB":
    db = InMemoryDB()
    db.set(1, "wallet_a", "status", "active")
    db.set(1, "wallet_a", "balance", "100")
    db.set(1, "wallet_a", "balance_pending", "20")
    db.set(1, "wallet_a", "currency", "USD")
    return db


@pytest.mark.level2
def test_scan_returns_all_fields_sorted_by_field_name():
    db = _seed_wallet()
    assert db.scan(2, "wallet_a") == (
        "balance(100), balance_pending(20), currency(USD), status(active)"
    )


@pytest.mark.level2
def test_scan_uses_comma_space_as_the_separator():
    db = InMemoryDB()
    db.set(1, "k", "a", "1")
    db.set(1, "k", "b", "2")
    assert db.scan(2, "k") == "a(1), b(2)"
    assert ", " in db.scan(2, "k")


@pytest.mark.level2
def test_scan_of_a_single_field_has_no_separator():
    db = InMemoryDB()
    db.set(1, "k", "only", "v")
    assert db.scan(2, "k") == "only(v)"


@pytest.mark.level2
def test_scan_of_a_missing_key_returns_empty_string():
    db = _seed_wallet()
    assert db.scan(2, "wallet_ghost") == ""


@pytest.mark.level2
def test_scan_of_a_key_whose_fields_were_all_deleted_returns_empty_string():
    db = InMemoryDB()
    db.set(1, "k", "a", "1")
    db.delete(2, "k", "a")
    assert db.scan(3, "k") == ""


@pytest.mark.level2
def test_scan_ignores_insertion_order():
    db = InMemoryDB()
    db.set(1, "k", "zeta", "3")
    db.set(1, "k", "alpha", "1")
    db.set(1, "k", "mid", "2")
    assert db.scan(2, "k") == "alpha(1), mid(2), zeta(3)"


@pytest.mark.level2
def test_scan_reflects_the_latest_value_of_an_overwritten_field():
    db = _seed_wallet()
    db.set(2, "wallet_a", "balance", "555")
    assert db.scan(3, "wallet_a") == (
        "balance(555), balance_pending(20), currency(USD), status(active)"
    )


@pytest.mark.level2
def test_scan_excludes_a_deleted_field():
    db = _seed_wallet()
    db.delete(2, "wallet_a", "currency")
    assert db.scan(3, "wallet_a") == (
        "balance(100), balance_pending(20), status(active)"
    )


@pytest.mark.level2
def test_scan_by_prefix_returns_only_matching_fields():
    db = _seed_wallet()
    assert db.scan_by_prefix(2, "wallet_a", "bal") == "balance(100), balance_pending(20)"


@pytest.mark.level2
def test_scan_by_prefix_with_an_empty_prefix_behaves_like_scan():
    db = _seed_wallet()
    assert db.scan_by_prefix(2, "wallet_a", "") == db.scan(2, "wallet_a")


@pytest.mark.level2
def test_scan_by_prefix_matching_nothing_returns_empty_string():
    db = _seed_wallet()
    assert db.scan_by_prefix(2, "wallet_a", "zzz") == ""


@pytest.mark.level2
def test_scan_by_prefix_equal_to_a_full_field_name_matches_that_field():
    db = _seed_wallet()
    assert db.scan_by_prefix(2, "wallet_a", "currency") == "currency(USD)"


@pytest.mark.level2
def test_scan_by_prefix_of_a_missing_key_returns_empty_string():
    db = _seed_wallet()
    assert db.scan_by_prefix(2, "wallet_ghost", "bal") == ""


@pytest.mark.level2
def test_scan_by_prefix_is_plain_string_ordering():
    db = InMemoryDB()
    db.set(1, "k", "f10", "a")
    db.set(1, "k", "f2", "b")
    db.set(1, "k", "f1", "c")
    assert db.scan_by_prefix(2, "k", "f") == "f1(c), f10(a), f2(b)"


@pytest.mark.level2
def test_scan_is_isolated_per_key():
    db = _seed_wallet()
    db.set(1, "wallet_b", "balance", "9")
    assert db.scan(2, "wallet_b") == "balance(9)"


# ======================================================================
# Level 3 -- TTL
# ======================================================================


@pytest.mark.level3
def test_set_with_ttl_returns_none_and_is_readable_at_its_own_timestamp():
    db = InMemoryDB()
    assert db.set_with_ttl(10, "wallet_a", "balance", "100", 5) is None
    assert db.get(10, "wallet_a", "balance") == "100"


@pytest.mark.level3
def test_ttl_liveness_is_half_open_on_both_boundaries():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)  # alive on [10, 15)
    assert db.get(10, "wallet_a", "balance") == "100"  # inclusive start
    assert db.get(14, "wallet_a", "balance") == "100"  # t + ttl - 1
    assert db.get(15, "wallet_a", "balance") is None  # exclusive end
    assert db.get(16, "wallet_a", "balance") is None


@pytest.mark.level3
def test_ttl_of_zero_is_dead_on_arrival():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 0)
    assert db.get(10, "wallet_a", "balance") is None
    assert db.scan(10, "wallet_a") == ""


@pytest.mark.level3
def test_negative_ttl_is_dead_on_arrival():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", -5)
    assert db.get(10, "wallet_a", "balance") is None
    assert db.get(20, "wallet_a", "balance") is None
    assert db.scan(10, "wallet_a") == ""


@pytest.mark.level3
def test_plain_set_is_permanent():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    assert db.get(10**9, "wallet_a", "balance") == "100"


@pytest.mark.level3
def test_plain_set_over_a_ttl_field_makes_it_permanent_again():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)
    db.set(12, "wallet_a", "balance", "200")
    assert db.get(15, "wallet_a", "balance") == "200"  # would have died at 15
    assert db.get(10**9, "wallet_a", "balance") == "200"


@pytest.mark.level3
def test_set_with_ttl_over_a_permanent_field_makes_it_expiring():
    db = InMemoryDB()
    db.set(10, "wallet_a", "balance", "100")
    db.set_with_ttl(12, "wallet_a", "balance", "200", 5)
    assert db.get(16, "wallet_a", "balance") == "200"
    assert db.get(17, "wallet_a", "balance") is None


@pytest.mark.level3
def test_set_with_ttl_rearms_an_existing_field_from_the_new_timestamp():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)  # would die at 15
    db.set_with_ttl(14, "wallet_a", "balance", "200", 5)  # now dies at 19
    assert db.get(15, "wallet_a", "balance") == "200"
    assert db.get(18, "wallet_a", "balance") == "200"
    assert db.get(19, "wallet_a", "balance") is None


@pytest.mark.level3
def test_delete_of_an_expired_field_returns_false():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)
    assert db.delete(15, "wallet_a", "balance") is False
    assert db.get(15, "wallet_a", "balance") is None
    assert db.scan(15, "wallet_a") == ""


@pytest.mark.level3
def test_delete_of_an_expired_field_leaves_the_field_recreatable():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)
    assert db.delete(15, "wallet_a", "balance") is False
    db.set(16, "wallet_a", "balance", "new")
    assert db.get(17, "wallet_a", "balance") == "new"


@pytest.mark.level3
def test_delete_of_a_still_live_ttl_field_returns_true():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)
    assert db.delete(14, "wallet_a", "balance") is True
    assert db.get(14, "wallet_a", "balance") is None


@pytest.mark.level3
def test_scan_skips_expired_fields():
    db = InMemoryDB()
    db.set(10, "wallet_a", "status", "active")
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)
    assert db.scan(14, "wallet_a") == "balance(100), status(active)"
    assert db.scan(15, "wallet_a") == "status(active)"


@pytest.mark.level3
def test_scan_by_prefix_skips_expired_fields():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)
    db.set(10, "wallet_a", "balance_pending", "20")
    assert db.scan_by_prefix(14, "wallet_a", "bal") == (
        "balance(100), balance_pending(20)"
    )
    assert db.scan_by_prefix(15, "wallet_a", "bal") == "balance_pending(20)"


@pytest.mark.level3
def test_scan_of_a_record_whose_fields_have_all_expired_is_empty_string():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)
    db.set_with_ttl(10, "wallet_a", "status", "active", 3)
    assert db.scan(12, "wallet_a") == "balance(100), status(active)"
    assert db.scan(15, "wallet_a") == ""


@pytest.mark.level3
def test_permanent_and_expiring_fields_coexist_in_one_record():
    db = InMemoryDB()
    db.set(10, "wallet_a", "currency", "USD")
    db.set_with_ttl(10, "wallet_a", "promo", "SUMMER", 4)
    db.set_with_ttl(10, "wallet_a", "hold", "50", 2)
    assert db.scan(11, "wallet_a") == "currency(USD), hold(50), promo(SUMMER)"
    assert db.scan(12, "wallet_a") == "currency(USD), promo(SUMMER)"
    assert db.scan(14, "wallet_a") == "currency(USD)"


# ======================================================================
# Level 4 -- backup and restore
# ======================================================================


@pytest.mark.level4
def test_backup_on_an_empty_database_returns_zero():
    db = InMemoryDB()
    assert db.backup(10) == 0


@pytest.mark.level4
def test_backup_counts_records_not_fields():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.set(1, "wallet_a", "status", "active")
    db.set(1, "wallet_a", "currency", "USD")
    db.set(1, "wallet_b", "balance", "200")
    assert db.backup(2) == 2


@pytest.mark.level4
def test_backup_ignores_records_whose_fields_have_all_expired():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)
    db.set(10, "wallet_b", "balance", "200")
    assert db.backup(14) == 2
    assert db.backup(15) == 1


@pytest.mark.level4
def test_backup_returns_zero_when_everything_has_expired():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)
    db.set_with_ttl(10, "wallet_b", "balance", "200", 3)
    assert db.backup(100) == 0


@pytest.mark.level4
def test_backup_does_not_mutate_live_state():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.backup(2)
    assert db.scan(3, "wallet_a") == "balance(100)"


@pytest.mark.level4
def test_restore_resumes_remaining_lifespan_after_a_far_clock_jump():
    # The headline Level 4 test: a snapshot must store REMAINING lifespan, not
    # absolute expiry. With absolute expiry the field comes back already dead.
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 100)  # expires at 110
    assert db.backup(15) == 1  # 95 units remain
    db.restore(1000, 15)
    assert db.get(1000, "wallet_a", "balance") == "100"
    assert db.get(1094, "wallet_a", "balance") == "100"  # 1000 + 95 - 1
    assert db.get(1095, "wallet_a", "balance") is None  # 1000 + 95
    assert db.scan(1094, "wallet_a") == "balance(100)"
    assert db.scan(1095, "wallet_a") == ""


@pytest.mark.level4
def test_restore_keeps_permanent_fields_permanent():
    db = InMemoryDB()
    db.set(10, "wallet_a", "currency", "USD")
    db.backup(15)
    db.restore(10**6, 15)
    assert db.get(10**9, "wallet_a", "currency") == "USD"


@pytest.mark.level4
def test_restore_brings_back_a_record_deleted_after_the_backup():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.backup(2)
    db.delete(3, "wallet_a", "balance")
    assert db.get(4, "wallet_a", "balance") is None
    db.restore(5, 2)
    assert db.get(5, "wallet_a", "balance") == "100"


@pytest.mark.level4
def test_restore_removes_a_record_created_after_the_backup():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.backup(2)
    db.set(3, "wallet_b", "balance", "200")
    db.restore(4, 2)
    assert db.get(4, "wallet_b", "balance") is None
    assert db.scan(4, "wallet_b") == ""
    assert db.get(4, "wallet_a", "balance") == "100"


@pytest.mark.level4
def test_restore_replaces_the_entire_state_in_one_go():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.set(1, "wallet_a", "status", "active")
    db.backup(2)
    db.set(3, "wallet_a", "balance", "999")  # changed after the backup
    db.delete(3, "wallet_a", "status")  # removed after the backup
    db.set(3, "wallet_c", "balance", "5")  # created after the backup
    db.restore(4, 2)
    assert db.scan(4, "wallet_a") == "balance(100), status(active)"
    assert db.scan(4, "wallet_c") == ""


@pytest.mark.level4
def test_restore_with_no_eligible_backup_is_a_no_op():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.restore(5, 4)  # no backup at all
    assert db.get(5, "wallet_a", "balance") == "100"

    db.backup(10)
    db.set(11, "wallet_b", "balance", "200")
    db.restore(12, 9)  # the only backup is at 10, which is after 9
    assert db.get(12, "wallet_b", "balance") == "200"


@pytest.mark.level4
def test_restore_picks_the_latest_backup_at_or_before_the_target():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "1")
    db.backup(2)
    db.set(3, "wallet_a", "balance", "2")
    db.backup(4)
    db.set(5, "wallet_a", "balance", "3")
    db.backup(6)

    db.restore(7, 5)  # latest backup at or before 5 is the one at 4
    assert db.get(7, "wallet_a", "balance") == "2"
    db.restore(8, 4)  # exact hit on the backup at 4
    assert db.get(8, "wallet_a", "balance") == "2"
    db.restore(9, 2)
    assert db.get(9, "wallet_a", "balance") == "1"


@pytest.mark.level4
def test_two_backups_at_the_same_timestamp_the_later_call_wins():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "first")
    assert db.backup(5) == 1
    db.set(5, "wallet_a", "balance", "second")
    db.set(5, "wallet_b", "balance", "extra")
    assert db.backup(5) == 2
    db.restore(6, 5)
    assert db.get(6, "wallet_a", "balance") == "second"
    assert db.get(6, "wallet_b", "balance") == "extra"


@pytest.mark.level4
def test_a_backup_may_be_taken_at_the_restore_timestamp():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.backup(2)
    db.set(3, "wallet_b", "balance", "200")
    db.restore(4, 2)
    assert db.backup(4) == 1  # restore is an ordinary operation
    db.set(5, "wallet_c", "balance", "300")
    db.restore(6, 4)
    assert db.scan(6, "wallet_a") == "balance(100)"
    assert db.scan(6, "wallet_c") == ""


@pytest.mark.level4
def test_a_field_with_one_unit_of_life_left_survives_the_round_trip():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)  # expires at 15
    assert db.backup(14) == 1  # exactly 1 unit remains
    db.restore(100, 14)
    assert db.get(100, "wallet_a", "balance") == "100"
    assert db.get(101, "wallet_a", "balance") is None


@pytest.mark.level4
def test_a_field_expiring_exactly_at_the_backup_timestamp_is_not_backed_up():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)  # expires at 15
    db.set(10, "wallet_b", "status", "active")
    assert db.backup(15) == 1  # wallet_a has no live field
    db.restore(200, 15)
    assert db.get(200, "wallet_a", "balance") is None
    assert db.get(200, "wallet_b", "status") == "active"


@pytest.mark.level4
def test_deleting_an_expired_field_leaves_nothing_for_a_backup_to_resurrect():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 5)  # expires at 15
    db.set(10, "wallet_b", "status", "active")
    assert db.delete(20, "wallet_a", "balance") is False  # expired, and purged
    assert db.backup(21) == 1  # only wallet_b has a live field
    db.restore(22, 21)
    assert db.get(22, "wallet_a", "balance") is None
    assert db.scan(22, "wallet_a") == ""
    assert db.get(22, "wallet_b", "status") == "active"


@pytest.mark.level4
def test_the_same_backup_can_be_restored_twice():
    db = InMemoryDB()
    db.set_with_ttl(10, "wallet_a", "balance", "100", 50)  # expires at 60
    db.backup(20)  # 40 units remain
    db.restore(100, 20)
    assert db.get(139, "wallet_a", "balance") == "100"
    db.set(140, "wallet_a", "balance", "clobbered")
    db.restore(200, 20)
    assert db.get(239, "wallet_a", "balance") == "100"
    assert db.get(240, "wallet_a", "balance") is None


@pytest.mark.level4
def test_mutations_continue_normally_after_a_restore():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.backup(2)
    db.restore(3, 2)
    db.set_with_ttl(4, "wallet_a", "promo", "SUMMER", 3)
    assert db.scan(6, "wallet_a") == "balance(100), promo(SUMMER)"
    assert db.scan(7, "wallet_a") == "balance(100)"
    assert db.delete(8, "wallet_a", "balance") is True
    assert db.scan(9, "wallet_a") == ""


# ---------------------------------------------------------------- #
# Backward compatibility: Levels 1 and 2 must still behave exactly. #
# ---------------------------------------------------------------- #


@pytest.mark.level4
def test_backward_compat_level1_core_operations_on_a_full_featured_db():
    db = InMemoryDB()
    assert db.set(1, "wallet_a", "balance", "100") is None
    assert db.get(2, "wallet_a", "balance") == "100"
    assert db.get(2, "wallet_a", "status") is None
    assert db.get(2, "ghost", "balance") is None
    db.set(3, "wallet_a", "balance", "250")
    assert db.get(4, "wallet_a", "balance") == "250"
    assert db.delete(5, "wallet_a", "balance") is True
    assert db.delete(6, "wallet_a", "balance") is False
    assert db.get(7, "wallet_a", "balance") is None
    assert db.delete(8, "ghost", "balance") is False


@pytest.mark.level4
def test_backward_compat_level2_scans_on_a_full_featured_db():
    db = _seed_wallet()
    assert db.scan(2, "wallet_a") == (
        "balance(100), balance_pending(20), currency(USD), status(active)"
    )
    assert db.scan_by_prefix(2, "wallet_a", "bal") == "balance(100), balance_pending(20)"
    assert db.scan_by_prefix(2, "wallet_a", "") == db.scan(2, "wallet_a")
    assert db.scan_by_prefix(2, "wallet_a", "zzz") == ""
    assert db.scan(2, "wallet_ghost") == ""


@pytest.mark.level4
def test_backward_compat_plain_set_never_expires_even_across_backup_restore():
    db = InMemoryDB()
    db.set(1, "wallet_a", "balance", "100")
    db.backup(2)
    db.restore(10**6, 2)
    assert db.get(10**9, "wallet_a", "balance") == "100"
    assert db.scan(10**9, "wallet_a") == "balance(100)"
