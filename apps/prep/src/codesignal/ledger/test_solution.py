"""Test suite for ICF Mock 4 -- Ledger.

Run everything:        python3 -m pytest -q
Run one level:         python3 -m pytest -q -m level1
Test your own attempt: ICF_IMPL=attempt python3 -m pytest -q -m level1
"""

import importlib
import os

import pytest

_impl = importlib.import_module(os.environ.get("ICF_IMPL", "solution"))
Ledger = _impl.Ledger


# ======================================================================
# Level 1 -- core account operations
# ======================================================================
#
# Levels 1-3 expose no way to read a balance, and `amount` is contractually
# positive, so these tests probe a balance with a deposit of 1 and assert the
# returned total: `deposit(t, "alice", 1) == 101` means the balance was 100.
# From Level 4 onwards `get_balance` does the job directly.


@pytest.mark.level1
def test_create_account_returns_true_for_a_new_id():
    ledger = Ledger()
    assert ledger.create_account(1, "alice") is True


@pytest.mark.level1
def test_create_account_returns_false_for_a_duplicate_id():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    assert ledger.create_account(2, "alice") is False


@pytest.mark.level1
def test_duplicate_create_does_not_reset_the_balance():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.deposit(2, "alice", 500)
    assert ledger.create_account(3, "alice") is False
    assert ledger.deposit(4, "alice", 1) == 501  # the 500 is still there


@pytest.mark.level1
def test_new_account_starts_at_zero():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    assert ledger.deposit(2, "alice", 1) == 1


@pytest.mark.level1
def test_deposit_returns_the_new_balance():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    assert ledger.deposit(2, "alice", 100) == 100


@pytest.mark.level1
def test_deposits_accumulate():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.deposit(2, "alice", 100)
    assert ledger.deposit(3, "alice", 250) == 350


@pytest.mark.level1
def test_deposit_into_a_missing_account_returns_none():
    ledger = Ledger()
    assert ledger.deposit(1, "ghost", 100) is None


@pytest.mark.level1
def test_transfer_returns_the_sources_new_balance():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 100)
    assert ledger.transfer(3, "alice", "bob", 30) == 70


@pytest.mark.level1
def test_transfer_credits_the_target():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 100)
    ledger.transfer(3, "alice", "bob", 30)
    assert ledger.deposit(4, "bob", 1) == 31  # bob holds the 30


@pytest.mark.level1
def test_transfer_of_the_entire_balance_succeeds_and_leaves_zero():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 100)
    assert ledger.transfer(3, "alice", "bob", 100) == 0


@pytest.mark.level1
def test_transfer_to_self_returns_none_and_changes_nothing():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.deposit(2, "alice", 100)
    assert ledger.transfer(3, "alice", "alice", 10) is None
    assert ledger.deposit(4, "alice", 1) == 101


@pytest.mark.level1
def test_transfer_with_insufficient_funds_returns_none_and_moves_nothing():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 100)
    assert ledger.transfer(3, "alice", "bob", 101) is None
    assert ledger.deposit(4, "alice", 1) == 101
    assert ledger.deposit(4, "bob", 1) == 1


@pytest.mark.level1
def test_transfer_from_a_missing_source_returns_none():
    ledger = Ledger()
    ledger.create_account(1, "bob")
    assert ledger.transfer(2, "ghost", "bob", 10) is None


@pytest.mark.level1
def test_transfer_to_a_missing_target_returns_none_and_keeps_the_money():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.deposit(2, "alice", 100)
    assert ledger.transfer(3, "alice", "ghost", 10) is None
    assert ledger.deposit(4, "alice", 1) == 101


@pytest.mark.level1
def test_accounts_are_independent():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 100)
    assert ledger.deposit(3, "bob", 1) == 1


# ======================================================================
# Level 2 -- top spenders aggregation
# ======================================================================


def _seed_level2() -> Ledger:
    """alice sends 300, bob sends 300, carol sends 100, dave sends nothing."""
    ledger = Ledger()
    for account_id in ("alice", "bob", "carol", "dave"):
        ledger.create_account(1, account_id)
        ledger.deposit(2, account_id, 1000)
    ledger.transfer(3, "alice", "dave", 300)
    ledger.transfer(4, "bob", "dave", 200)
    ledger.transfer(5, "bob", "carol", 100)
    ledger.transfer(6, "carol", "dave", 100)
    return ledger


@pytest.mark.level2
def test_top_spenders_on_an_empty_ledger_is_the_empty_string():
    assert Ledger().top_spenders(1, 5) == ""


@pytest.mark.level2
def test_top_spenders_orders_by_outgoing_descending():
    ledger = _seed_level2()
    assert ledger.top_spenders(10, 3) == "alice(300), bob(300), carol(100)"


@pytest.mark.level2
def test_top_spenders_breaks_ties_by_account_id_ascending():
    ledger = Ledger()
    ledger.create_account(1, "zoe")
    ledger.create_account(1, "amy")
    ledger.create_account(1, "sink")
    ledger.deposit(2, "zoe", 500)
    ledger.deposit(2, "amy", 500)
    ledger.transfer(3, "zoe", "sink", 500)
    ledger.transfer(3, "amy", "sink", 500)
    assert ledger.top_spenders(4, 2) == "amy(500), zoe(500)"


@pytest.mark.level2
def test_top_spenders_includes_accounts_that_never_sent_anything():
    ledger = _seed_level2()
    assert ledger.top_spenders(10, 4) == "alice(300), bob(300), carol(100), dave(0)"


@pytest.mark.level2
def test_top_spenders_with_n_larger_than_the_account_count_returns_all():
    ledger = _seed_level2()
    assert ledger.top_spenders(10, 99) == "alice(300), bob(300), carol(100), dave(0)"


@pytest.mark.level2
def test_top_spenders_with_n_zero_is_the_empty_string():
    ledger = _seed_level2()
    assert ledger.top_spenders(10, 0) == ""


@pytest.mark.level2
def test_top_spenders_with_negative_n_is_the_empty_string():
    ledger = _seed_level2()
    assert ledger.top_spenders(10, -4) == ""


@pytest.mark.level2
def test_top_spenders_with_n_one_returns_a_single_entry_without_a_separator():
    ledger = _seed_level2()
    assert ledger.top_spenders(10, 1) == "alice(300)"


@pytest.mark.level2
def test_top_spenders_separator_is_comma_space():
    ledger = _seed_level2()
    assert ", " in ledger.top_spenders(10, 2)
    assert ledger.top_spenders(10, 2).split(", ") == ["alice(300)", "bob(300)"]


@pytest.mark.level2
def test_received_money_does_not_count_as_outgoing():
    ledger = _seed_level2()
    # dave received 600 in total and sent nothing.
    assert ledger.top_spenders(10, 4).endswith("dave(0)")


@pytest.mark.level2
def test_a_failed_transfer_does_not_count_toward_outgoing():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 50)
    assert ledger.transfer(3, "alice", "bob", 500) is None
    assert ledger.transfer(3, "alice", "alice", 10) is None
    assert ledger.top_spenders(4, 2) == "alice(0), bob(0)"


@pytest.mark.level2
def test_outgoing_totals_accumulate_across_transfers():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 1000)
    ledger.transfer(3, "alice", "bob", 100)
    ledger.transfer(4, "alice", "bob", 250)
    assert ledger.top_spenders(5, 1) == "alice(350)"


@pytest.mark.level2
def test_top_spenders_ranks_all_zero_accounts_by_id():
    ledger = Ledger()
    for account_id in ("c", "a", "b"):
        ledger.create_account(1, account_id)
    assert ledger.top_spenders(2, 3) == "a(0), b(0), c(0)"


@pytest.mark.level2
def test_top_spenders_truncates_at_n_after_sorting():
    ledger = _seed_level2()
    assert ledger.top_spenders(10, 2) == "alice(300), bob(300)"


# ======================================================================
# Level 3 -- scheduled and cancellable payments
# ======================================================================


def _funded(balance: int = 1000, *, account_id: str = "alice") -> Ledger:
    ledger = Ledger()
    ledger.create_account(1, account_id)
    ledger.deposit(1, account_id, balance)
    return ledger


@pytest.mark.level3
def test_schedule_payment_returns_sequential_ids():
    ledger = _funded()
    assert ledger.schedule_payment(2, "alice", 10, 100) == "payment1"
    assert ledger.schedule_payment(2, "alice", 10, 100) == "payment2"


@pytest.mark.level3
def test_payment_ids_are_global_across_accounts():
    ledger = _funded()
    ledger.create_account(2, "bob")
    assert ledger.schedule_payment(3, "alice", 10, 100) == "payment1"
    assert ledger.schedule_payment(3, "bob", 10, 100) == "payment2"
    assert ledger.schedule_payment(3, "alice", 10, 100) == "payment3"


@pytest.mark.level3
def test_schedule_payment_for_a_missing_account_returns_none():
    ledger = _funded()
    assert ledger.schedule_payment(2, "ghost", 10, 5) is None


@pytest.mark.level3
def test_scheduling_does_not_move_money_now():
    ledger = _funded(1000)
    ledger.schedule_payment(2, "alice", 400, 10)
    assert ledger.deposit(3, "alice", 1) == 1001  # nothing was withheld
    assert ledger.top_spenders(3, 1) == "alice(0)"


@pytest.mark.level3
def test_payment_executes_once_the_clock_reaches_its_scheduled_time():
    ledger = _funded(1000)
    ledger.schedule_payment(2, "alice", 400, 10)  # due at 12
    assert ledger.deposit(11, "alice", 1) == 1001  # not yet
    assert ledger.deposit(12, "alice", 1) == 602  # 1001 - 400 + 1


@pytest.mark.level3
def test_delay_zero_fires_at_the_next_operation_not_during_scheduling():
    ledger = _funded(1000)
    ledger.schedule_payment(5, "alice", 400, 0)  # due at 5, the same instant
    # schedule_payment itself must not execute it; the very next operation does.
    assert ledger.deposit(5, "alice", 1) == 601  # 1000 - 400 + 1


@pytest.mark.level3
def test_executed_payment_counts_toward_top_spenders():
    ledger = _funded(1000)
    ledger.create_account(1, "bob")
    ledger.schedule_payment(2, "alice", 400, 3)
    assert ledger.top_spenders(5, 2) == "alice(400), bob(0)"


@pytest.mark.level3
def test_underfunded_payment_is_discarded_without_effect():
    ledger = _funded(100)
    ledger.schedule_payment(2, "alice", 500, 3)
    assert ledger.deposit(5, "alice", 1) == 101  # nothing deducted
    assert ledger.top_spenders(5, 1) == "alice(0)"  # not counted as spending
    ledger.deposit(6, "alice", 1000)
    assert ledger.deposit(7, "alice", 1) == 1102  # and it does not retry later


@pytest.mark.level3
def test_a_payment_does_not_reserve_the_balance_when_scheduled():
    ledger = _funded(100)
    ledger.create_account(1, "bob")
    ledger.schedule_payment(2, "alice", 500, 10)  # more than the balance, legal
    assert ledger.transfer(3, "alice", "bob", 100) == 0  # full balance still spendable
    ledger.deposit(4, "alice", 500)
    assert ledger.deposit(12, "alice", 1) == 1  # funded by then, so it executed
    assert ledger.top_spenders(12, 1) == "alice(600)"


@pytest.mark.level3
def test_cancel_before_the_due_time_stops_the_payment():
    ledger = _funded(1000)
    payment_id = ledger.schedule_payment(2, "alice", 400, 10)
    assert ledger.cancel_payment(5, "alice", payment_id) is True
    assert ledger.deposit(100, "alice", 1) == 1001  # it never fired


@pytest.mark.level3
def test_cancel_at_the_scheduled_time_is_too_late():
    ledger = _funded(1000)
    payment_id = ledger.schedule_payment(2, "alice", 400, 10)  # due at 12
    assert ledger.cancel_payment(12, "alice", payment_id) is False
    assert ledger.deposit(12, "alice", 1) == 601  # it had already fired


@pytest.mark.level3
def test_cancel_after_execution_returns_false():
    ledger = _funded(1000)
    payment_id = ledger.schedule_payment(2, "alice", 400, 1)
    assert ledger.deposit(20, "alice", 1) == 601  # this call executed it
    assert ledger.cancel_payment(21, "alice", payment_id) is False


@pytest.mark.level3
def test_cancel_by_the_wrong_owner_returns_false_and_leaves_it_pending():
    ledger = _funded(1000)
    ledger.create_account(1, "bob")
    payment_id = ledger.schedule_payment(2, "alice", 400, 10)
    assert ledger.cancel_payment(3, "bob", payment_id) is False
    assert ledger.deposit(12, "alice", 1) == 601  # still fired


@pytest.mark.level3
def test_cancel_an_unknown_payment_id_returns_false():
    ledger = _funded(1000)
    assert ledger.cancel_payment(2, "alice", "payment99") is False
    assert ledger.cancel_payment(2, "ghost", "payment1") is False


@pytest.mark.level3
def test_cancel_twice_returns_false_the_second_time():
    ledger = _funded(1000)
    payment_id = ledger.schedule_payment(2, "alice", 400, 10)
    assert ledger.cancel_payment(3, "alice", payment_id) is True
    assert ledger.cancel_payment(4, "alice", payment_id) is False


@pytest.mark.level3
def test_payments_due_at_the_same_time_execute_in_creation_order():
    ledger = _funded(100)
    ledger.schedule_payment(2, "alice", 60, 5)  # payment1, due at 7
    ledger.schedule_payment(2, "alice", 60, 5)  # payment2, due at 7 -- underfunded
    assert ledger.deposit(7, "alice", 1) == 41
    assert ledger.top_spenders(7, 1) == "alice(60)"


@pytest.mark.level3
def test_earlier_scheduled_payments_execute_first():
    ledger = _funded(100)
    ledger.schedule_payment(2, "alice", 80, 20)  # payment1, due at 22
    ledger.schedule_payment(2, "alice", 80, 10)  # payment2, due at 12 -- runs first
    assert ledger.deposit(30, "alice", 1) == 21
    assert ledger.top_spenders(30, 1) == "alice(80)"


@pytest.mark.level3
def test_every_operation_drains_due_payments_including_reads():
    ledger = _funded(1000)
    ledger.schedule_payment(2, "alice", 400, 5)  # due at 7
    assert ledger.top_spenders(7, 1) == "alice(400)"  # a read triggered it
    ledger2 = _funded(1000)
    ledger2.schedule_payment(2, "alice", 400, 5)
    assert ledger2.create_account(7, "bob") is True  # so does an unrelated write
    assert ledger2.deposit(7, "alice", 1) == 601


# ======================================================================
# Level 4 -- account merges and historical balances
# ======================================================================


@pytest.mark.level4
def test_merge_adds_the_absorbed_balance_to_the_survivor():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 100)
    ledger.deposit(2, "bob", 250)
    assert ledger.merge_accounts(3, "alice", "bob") is True
    assert ledger.get_balance(4, "alice", 4) == 350


@pytest.mark.level4
def test_merge_removes_the_absorbed_account():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.merge_accounts(2, "alice", "bob")
    assert ledger.deposit(3, "bob", 10) is None
    assert ledger.top_spenders(3, 5) == "alice(0)"


@pytest.mark.level4
def test_merge_combines_the_outgoing_totals():
    ledger = Ledger()
    for account_id in ("alice", "bob", "sink"):
        ledger.create_account(1, account_id)
        ledger.deposit(1, account_id, 1000)
    ledger.transfer(2, "alice", "sink", 300)
    ledger.transfer(2, "bob", "sink", 400)
    ledger.merge_accounts(3, "alice", "bob")
    assert ledger.top_spenders(4, 5) == "alice(700), sink(0)"


@pytest.mark.level4
def test_merge_with_identical_ids_returns_false():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    assert ledger.merge_accounts(2, "alice", "alice") is False


@pytest.mark.level4
def test_merge_with_a_missing_account_returns_false():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    assert ledger.merge_accounts(2, "alice", "ghost") is False
    assert ledger.merge_accounts(2, "ghost", "alice") is False
    assert ledger.merge_accounts(2, "ghost", "phantom") is False


@pytest.mark.level4
def test_merged_pending_payment_fires_against_the_survivor():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(1, "alice", 500)
    ledger.schedule_payment(2, "bob", 300, 20)  # bob cannot afford this alone
    ledger.merge_accounts(3, "alice", "bob")
    assert ledger.get_balance(22, "alice", 22) == 200  # billed to alice, and it cleared
    assert ledger.top_spenders(22, 1) == "alice(300)"


@pytest.mark.level4
def test_survivor_can_cancel_a_payment_inherited_from_the_absorbed_account():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(1, "alice", 500)
    payment_id = ledger.schedule_payment(2, "bob", 300, 20)
    ledger.merge_accounts(3, "alice", "bob")
    assert ledger.cancel_payment(4, "alice", payment_id) is True
    assert ledger.get_balance(22, "alice", 22) == 500  # the payment never fired


@pytest.mark.level4
def test_the_absorbed_id_can_no_longer_cancel_its_own_payment():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(1, "bob", 500)
    payment_id = ledger.schedule_payment(2, "bob", 300, 20)
    ledger.merge_accounts(3, "alice", "bob")
    assert ledger.cancel_payment(4, "bob", payment_id) is False


@pytest.mark.level4
def test_get_balance_before_the_account_existed_is_none():
    ledger = Ledger()
    ledger.create_account(10, "alice")
    assert ledger.get_balance(20, "alice", 9) is None
    assert ledger.get_balance(20, "alice", 10) == 0


@pytest.mark.level4
def test_get_balance_for_an_account_that_never_existed_is_none():
    ledger = Ledger()
    ledger.create_account(10, "alice")
    assert ledger.get_balance(20, "ghost", 15) is None


@pytest.mark.level4
def test_get_balance_at_the_exact_timestamp_of_a_deposit_sees_the_deposit():
    ledger = Ledger()
    ledger.create_account(5, "alice")
    ledger.deposit(10, "alice", 100)
    assert ledger.get_balance(20, "alice", 9) == 0
    assert ledger.get_balance(20, "alice", 10) == 100
    assert ledger.get_balance(20, "alice", 11) == 100


@pytest.mark.level4
def test_get_balance_replays_a_sequence_of_operations():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 100)
    ledger.deposit(4, "alice", 50)
    ledger.transfer(6, "alice", "bob", 120)
    assert ledger.get_balance(10, "alice", 1) == 0
    assert ledger.get_balance(10, "alice", 3) == 100
    assert ledger.get_balance(10, "alice", 5) == 150
    assert ledger.get_balance(10, "alice", 6) == 30
    assert ledger.get_balance(10, "bob", 5) == 0
    assert ledger.get_balance(10, "bob", 6) == 120


@pytest.mark.level4
def test_get_balance_records_a_scheduled_payment_at_its_scheduled_instant():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.deposit(1, "alice", 100)
    ledger.schedule_payment(10, "alice", 30, 5)  # due at 15
    assert ledger.get_balance(20, "alice", 14) == 100
    assert ledger.get_balance(20, "alice", 15) == 70


@pytest.mark.level4
def test_get_balance_of_a_merged_away_account_before_and_after_the_merge():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "bob", 250)
    ledger.merge_accounts(5, "alice", "bob")
    assert ledger.get_balance(10, "bob", 4) == 250  # history survives the merge
    assert ledger.get_balance(10, "bob", 5) is None  # gone from the merge onward
    assert ledger.get_balance(10, "bob", 9) is None


@pytest.mark.level4
def test_merge_does_not_rewrite_the_survivors_history():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "alice", 100)
    ledger.deposit(2, "bob", 250)
    ledger.merge_accounts(5, "alice", "bob")
    assert ledger.get_balance(10, "alice", 4) == 100  # alice's own past, unchanged
    assert ledger.get_balance(10, "alice", 5) == 350  # the merge is an event at t=5


@pytest.mark.level4
def test_get_balance_reflects_a_payment_that_failed_and_was_discarded():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.deposit(1, "alice", 10)
    ledger.schedule_payment(2, "alice", 500, 3)  # due at 5, unaffordable
    assert ledger.get_balance(9, "alice", 5) == 10
    assert ledger.get_balance(9, "alice", 9) == 10


@pytest.mark.level4
def test_an_id_freed_by_a_merge_can_be_created_again():
    ledger = Ledger()
    ledger.create_account(1, "alice")
    ledger.create_account(1, "bob")
    ledger.deposit(2, "bob", 250)
    ledger.merge_accounts(5, "alice", "bob")
    assert ledger.create_account(8, "bob") is True
    assert ledger.get_balance(10, "bob", 4) == 250
    assert ledger.get_balance(10, "bob", 7) is None
    assert ledger.get_balance(10, "bob", 8) == 0


# ---------------------------------------------------------------- #
# Backward compatibility: Levels 1 and 2 must still behave exactly. #
# ---------------------------------------------------------------- #


@pytest.mark.level4
def test_backward_compat_level1_operations_on_a_full_featured_ledger():
    ledger = Ledger()
    assert ledger.create_account(1, "alice") is True
    assert ledger.create_account(1, "bob") is True
    assert ledger.create_account(1, "alice") is False
    assert ledger.deposit(2, "alice", 100) == 100
    assert ledger.deposit(2, "ghost", 100) is None
    assert ledger.transfer(3, "alice", "bob", 30) == 70
    assert ledger.transfer(3, "alice", "alice", 1) is None
    assert ledger.transfer(3, "alice", "ghost", 1) is None
    assert ledger.transfer(3, "alice", "bob", 71) is None
    assert ledger.transfer(3, "alice", "bob", 70) == 0

    # ...and they still hold once payments and merges are in play.
    ledger.create_account(4, "carol")
    ledger.deposit(4, "carol", 500)
    ledger.schedule_payment(4, "carol", 100, 10)
    ledger.merge_accounts(5, "bob", "alice")
    assert ledger.create_account(6, "alice") is True
    assert ledger.get_balance(6, "bob", 6) == 100
    assert ledger.transfer(20, "bob", "carol", 100) == 0
    # carol: 500 - 100 (the payment fired at 14) + 100 (the transfer)
    assert ledger.get_balance(20, "carol", 20) == 500


@pytest.mark.level4
def test_backward_compat_level2_top_spenders_on_a_full_featured_ledger():
    ledger = Ledger()
    for account_id in ("alice", "bob", "carol", "dave"):
        ledger.create_account(1, account_id)
        ledger.deposit(1, account_id, 1000)
    ledger.transfer(2, "alice", "dave", 300)
    ledger.transfer(2, "bob", "dave", 300)
    ledger.transfer(2, "carol", "dave", 100)
    assert ledger.top_spenders(3, 4) == "alice(300), bob(300), carol(100), dave(0)"
    assert ledger.top_spenders(3, 0) == ""
    assert ledger.top_spenders(3, 99) == "alice(300), bob(300), carol(100), dave(0)"

    ledger.schedule_payment(4, "dave", 250, 2)  # fires at 6
    ledger.merge_accounts(10, "carol", "bob")  # carol absorbs bob's 300
    assert ledger.top_spenders(10, 4) == "carol(400), alice(300), dave(250)"
    assert ledger.top_spenders(10, 1) == "carol(400)"
