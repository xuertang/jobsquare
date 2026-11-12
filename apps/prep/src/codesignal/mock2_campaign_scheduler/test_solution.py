import importlib, os
_impl = importlib.import_module(os.environ.get("ICF_IMPL", "solution"))
CampaignScheduler = _impl.CampaignScheduler

import pytest


# ===================================================================== #
# Level 1 -- campaign lifecycle CRUD                                     #
# ===================================================================== #


@pytest.mark.level1
def test_create_returns_true_and_duplicate_returns_false():
    s = CampaignScheduler()
    assert s.create_campaign(1, "summer-promo", "email", 8) is True
    assert s.create_campaign(2, "summer-promo", "push", 1) is False
    # The duplicate attempt must not have overwritten anything.
    assert s.get_campaign(3, "summer-promo") == (
        "summer-promo(channel=email, priority=8, status=active)"
    )


@pytest.mark.level1
def test_get_campaign_format_is_exact():
    s = CampaignScheduler()
    s.create_campaign(1, "host-winback", "push", 3)
    assert s.get_campaign(2, "host-winback") == (
        "host-winback(channel=push, priority=3, status=active)"
    )


@pytest.mark.level1
def test_get_missing_campaign_returns_none():
    s = CampaignScheduler()
    assert s.get_campaign(1, "nope") is None
    s.create_campaign(2, "real", "web", 1)
    assert s.get_campaign(3, "nope") is None


@pytest.mark.level1
def test_timestamp_is_accepted_but_ignored_at_level_one():
    """Level 1 semantics do not depend on the timestamp it is handed.

    The parameter is in every signature from the start; nothing at this level
    reads it. Two identical calls at wildly different timestamps -- including
    one that moves backwards -- must behave identically.
    """
    a = CampaignScheduler()
    b = CampaignScheduler()
    assert a.create_campaign(0, "c", "email", 5) == b.create_campaign(999, "c", "email", 5)
    assert a.pause_campaign(0, "c") == b.pause_campaign(1, "c")
    assert a.get_campaign(0, "c") == b.get_campaign(10**9, "c")
    assert a.resume_campaign(0, "c") == b.resume_campaign(2, "c")
    assert a.delete_campaign(0, "c") == b.delete_campaign(3, "c")


@pytest.mark.level1
def test_pause_then_resume_round_trip():
    s = CampaignScheduler()
    s.create_campaign(1, "c1", "email", 5)
    assert s.pause_campaign(2, "c1") is True
    assert s.get_campaign(3, "c1") == "c1(channel=email, priority=5, status=paused)"
    assert s.resume_campaign(4, "c1") is True
    assert s.get_campaign(5, "c1") == "c1(channel=email, priority=5, status=active)"


@pytest.mark.level1
def test_pause_twice_is_false_and_idempotent():
    s = CampaignScheduler()
    s.create_campaign(1, "c1", "email", 5)
    assert s.pause_campaign(2, "c1") is True
    assert s.pause_campaign(3, "c1") is False
    assert s.get_campaign(4, "c1") == "c1(channel=email, priority=5, status=paused)"


@pytest.mark.level1
def test_resume_an_already_active_campaign_is_false():
    s = CampaignScheduler()
    s.create_campaign(1, "c1", "web", 2)
    assert s.resume_campaign(2, "c1") is False


@pytest.mark.level1
def test_lifecycle_ops_on_missing_id_all_return_false():
    s = CampaignScheduler()
    assert s.pause_campaign(1, "ghost") is False
    assert s.resume_campaign(2, "ghost") is False
    assert s.delete_campaign(3, "ghost") is False


@pytest.mark.level1
def test_delete_removes_campaign_and_second_delete_is_false():
    s = CampaignScheduler()
    s.create_campaign(1, "c1", "email", 5)
    assert s.delete_campaign(2, "c1") is True
    assert s.get_campaign(3, "c1") is None
    assert s.delete_campaign(4, "c1") is False


@pytest.mark.level1
def test_recreate_after_delete_starts_fresh():
    s = CampaignScheduler()
    s.create_campaign(1, "c1", "email", 9)
    s.pause_campaign(2, "c1")
    s.delete_campaign(3, "c1")
    assert s.create_campaign(4, "c1", "web", 2) is True
    # New channel, new priority, and status is active again -- not paused.
    assert s.get_campaign(5, "c1") == "c1(channel=web, priority=2, status=active)"


@pytest.mark.level1
def test_campaigns_are_independent():
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 1)
    s.create_campaign(1, "b", "email", 2)
    s.pause_campaign(2, "a")
    assert s.get_campaign(3, "a") == "a(channel=email, priority=1, status=paused)"
    assert s.get_campaign(3, "b") == "b(channel=email, priority=2, status=active)"
    s.delete_campaign(4, "a")
    assert s.get_campaign(5, "b") == "b(channel=email, priority=2, status=active)"


@pytest.mark.level1
def test_priority_zero_and_negative_are_allowed():
    s = CampaignScheduler()
    assert s.create_campaign(1, "zero", "web", 0) is True
    assert s.create_campaign(1, "neg", "web", -4) is True
    assert s.get_campaign(2, "zero") == "zero(channel=web, priority=0, status=active)"
    assert s.get_campaign(2, "neg") == "neg(channel=web, priority=-4, status=active)"


# ===================================================================== #
# Level 2 -- querying, ranking and aggregation                           #
# ===================================================================== #


@pytest.mark.level2
def test_list_by_channel_sorted_by_priority_desc():
    s = CampaignScheduler()
    s.create_campaign(1, "low", "email", 1)
    s.create_campaign(1, "high", "email", 9)
    s.create_campaign(1, "mid", "email", 5)
    assert s.list_by_channel(2, "email") == (
        "high(priority=9), mid(priority=5), low(priority=1)"
    )


@pytest.mark.level2
def test_listings_return_one_string_not_a_list():
    """The separator is a comma AND a space; a single entry has no separator."""
    s = CampaignScheduler()
    s.create_campaign(1, "solo", "email", 3)
    assert s.list_by_channel(2, "email") == "solo(priority=3)"
    assert s.top_campaigns(2, 5) == "solo(priority=3)"
    s.create_campaign(3, "duo", "email", 1)
    assert s.list_by_channel(4, "email") == "solo(priority=3), duo(priority=1)"
    assert isinstance(s.list_by_channel(4, "email"), str)
    assert isinstance(s.top_campaigns(4, 5), str)


@pytest.mark.level2
def test_list_by_channel_tie_break_is_id_ascending():
    s = CampaignScheduler()
    s.create_campaign(1, "zeta", "web", 5)
    s.create_campaign(1, "alpha", "web", 5)
    s.create_campaign(1, "Mid", "web", 5)
    # Plain lexicographic ordering: uppercase sorts before lowercase.
    assert s.list_by_channel(2, "web") == (
        "Mid(priority=5), alpha(priority=5), zeta(priority=5)"
    )


@pytest.mark.level2
def test_list_by_channel_isolates_channels_and_unknown_channel_is_empty():
    s = CampaignScheduler()
    s.create_campaign(1, "e1", "email", 3)
    s.create_campaign(1, "p1", "push", 7)
    assert s.list_by_channel(2, "email") == "e1(priority=3)"
    assert s.list_by_channel(2, "push") == "p1(priority=7)"
    assert s.list_by_channel(2, "sms") == ""


@pytest.mark.level2
def test_paused_campaigns_are_excluded_from_listings():
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 9)
    s.create_campaign(1, "b", "email", 4)
    s.pause_campaign(2, "a")
    assert s.list_by_channel(3, "email") == "b(priority=4)"
    assert s.top_campaigns(3, 5) == "b(priority=4)"
    # ...and reappear on resume.
    s.resume_campaign(4, "a")
    assert s.list_by_channel(5, "email") == "a(priority=9), b(priority=4)"


@pytest.mark.level2
def test_count_active_tracks_pause_resume_and_delete():
    s = CampaignScheduler()
    assert s.count_active(1) == 0
    s.create_campaign(1, "a", "email", 1)
    s.create_campaign(1, "b", "push", 2)
    assert s.count_active(2) == 2
    s.pause_campaign(3, "a")
    assert s.count_active(4) == 1
    s.resume_campaign(5, "a")
    assert s.count_active(6) == 2
    s.delete_campaign(7, "b")
    assert s.count_active(8) == 1


@pytest.mark.level2
def test_top_campaigns_ranks_across_all_channels():
    s = CampaignScheduler()
    s.create_campaign(1, "e1", "email", 4)
    s.create_campaign(1, "p1", "push", 9)
    s.create_campaign(1, "w1", "web", 7)
    assert s.top_campaigns(2, 2) == "p1(priority=9), w1(priority=7)"


@pytest.mark.level2
def test_top_campaigns_cross_channel_tie_break():
    s = CampaignScheduler()
    s.create_campaign(1, "zebra", "email", 6)
    s.create_campaign(1, "apple", "push", 6)
    s.create_campaign(1, "mango", "web", 6)
    assert s.top_campaigns(2, 3) == (
        "apple(priority=6), mango(priority=6), zebra(priority=6)"
    )


@pytest.mark.level2
def test_top_campaigns_n_larger_than_population():
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 1)
    assert s.top_campaigns(2, 99) == "a(priority=1)"


@pytest.mark.level2
def test_top_campaigns_non_positive_n_is_empty():
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 1)
    assert s.top_campaigns(2, 0) == ""
    assert s.top_campaigns(2, -3) == ""


@pytest.mark.level2
def test_deleted_campaign_disappears_from_every_query():
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 5)
    s.create_campaign(1, "b", "email", 3)
    s.delete_campaign(2, "a")
    assert s.list_by_channel(3, "email") == "b(priority=3)"
    assert s.top_campaigns(3, 5) == "b(priority=3)"
    assert s.count_active(3) == 1


@pytest.mark.level2
def test_queries_on_empty_scheduler():
    s = CampaignScheduler()
    assert s.list_by_channel(1, "email") == ""
    assert s.top_campaigns(1, 3) == ""
    assert s.count_active(1) == 0


@pytest.mark.level2
def test_level_two_queries_ignore_their_timestamp():
    """Nothing at Level 2 depends on the timestamp; only the state matters."""
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 5)
    s.create_campaign(1, "b", "email", 2)
    for t in (0, 1, 7, 10**6):
        assert s.list_by_channel(t, "email") == "a(priority=5), b(priority=2)"
        assert s.top_campaigns(t, 1) == "a(priority=5)"
        assert s.count_active(t) == 2


# ===================================================================== #
# Level 3 -- budgets and sliding-window rate limiting                    #
# ===================================================================== #


@pytest.mark.level3
def test_serve_deducts_budget():
    s = CampaignScheduler(window=10, max_impressions_per_window=5)
    s.create_campaign(0, "c1", "email", 5)
    s.set_budget(0, "c1", 100)
    assert s.serve(1, "c1", 30) is True
    assert s.remaining_budget(1, "c1") == 70
    assert s.serve(2, "c1", 20) is True
    assert s.remaining_budget(2, "c1") == 50


@pytest.mark.level3
def test_uncapped_campaign_reports_minus_one_and_never_drains():
    s = CampaignScheduler(window=10, max_impressions_per_window=5)
    s.create_campaign(0, "c1", "email", 5)
    assert s.remaining_budget(0, "c1") == -1
    assert s.serve(1, "c1", 10_000) is True
    assert s.remaining_budget(1, "c1") == -1


@pytest.mark.level3
def test_budget_accessors_on_missing_campaign():
    s = CampaignScheduler()
    assert s.remaining_budget(1, "ghost") is None
    assert s.set_budget(1, "ghost", 100) is False
    assert s.serve(1, "ghost", 5) is False


@pytest.mark.level3
def test_set_budget_rejects_negative_and_leaves_state_untouched():
    s = CampaignScheduler()
    s.create_campaign(0, "c1", "email", 5)
    s.set_budget(1, "c1", 50)
    assert s.set_budget(2, "c1", -1) is False
    assert s.remaining_budget(3, "c1") == 50


@pytest.mark.level3
def test_set_budget_overwrites_absolutely_ignoring_prior_spend():
    s = CampaignScheduler(window=10, max_impressions_per_window=5)
    s.create_campaign(0, "c1", "email", 5)
    s.set_budget(0, "c1", 100)
    s.serve(1, "c1", 60)
    assert s.remaining_budget(1, "c1") == 40
    assert s.set_budget(2, "c1", 25) is True
    assert s.remaining_budget(2, "c1") == 25


@pytest.mark.level3
def test_serving_a_paused_campaign_fails_and_costs_nothing():
    s = CampaignScheduler(window=10, max_impressions_per_window=5)
    s.create_campaign(0, "c1", "email", 5)
    s.set_budget(0, "c1", 100)
    s.pause_campaign(0, "c1")
    assert s.serve(1, "c1", 10) is False
    assert s.remaining_budget(1, "c1") == 100
    s.resume_campaign(2, "c1")
    assert s.serve(2, "c1", 10) is True


@pytest.mark.level3
def test_budget_hitting_exactly_zero_succeeds_then_blocks():
    s = CampaignScheduler(window=100, max_impressions_per_window=50)
    s.create_campaign(0, "c1", "email", 5)
    s.set_budget(0, "c1", 30)
    assert s.serve(1, "c1", 30) is True  # remaining >= cost, exact match is OK
    assert s.remaining_budget(1, "c1") == 0
    assert s.serve(2, "c1", 1) is False  # exhausted


@pytest.mark.level3
def test_overspend_is_rejected_without_partial_delivery():
    s = CampaignScheduler(window=10, max_impressions_per_window=2)
    s.create_campaign(0, "c1", "email", 5)
    s.set_budget(0, "c1", 10)
    assert s.serve(1, "c1", 11) is False
    assert s.remaining_budget(1, "c1") == 10
    # A rejected serve must not burn a rate-limit slot either.
    assert s.serve(1, "c1", 5) is True
    assert s.serve(2, "c1", 5) is True
    assert s.serve(3, "c1", 1) is False  # now genuinely out of budget


@pytest.mark.level3
def test_non_positive_cost_is_rejected():
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(0, "c1", "email", 5)
    s.set_budget(0, "c1", 100)
    assert s.serve(1, "c1", 0) is False
    assert s.serve(1, "c1", -5) is False
    assert s.remaining_budget(1, "c1") == 100
    # No rate-limit slot consumed by the rejects.
    assert s.serve(1, "c1", 1) is True


@pytest.mark.level3
def test_exhausted_campaign_leaves_active_listings_but_keeps_active_status():
    s = CampaignScheduler(window=100, max_impressions_per_window=50)
    s.create_campaign(0, "a", "email", 9)
    s.create_campaign(0, "b", "email", 4)
    s.set_budget(0, "a", 10)
    assert s.count_active(0) == 2
    s.serve(1, "a", 10)  # drains a to exactly 0
    assert s.list_by_channel(2, "email") == "b(priority=4)"
    assert s.top_campaigns(2, 5) == "b(priority=4)"
    assert s.count_active(2) == 1
    # Exhaustion is NOT a lifecycle status change.
    assert s.get_campaign(2, "a") == "a(channel=email, priority=9, status=active)"
    # Refunding it brings it back.
    s.set_budget(3, "a", 5)
    assert s.count_active(3) == 2


@pytest.mark.level3
def test_zero_budget_campaign_is_immediately_ineligible():
    s = CampaignScheduler()
    s.create_campaign(0, "a", "web", 3)
    assert s.set_budget(0, "a", 0) is True
    assert s.count_active(1) == 0
    assert s.list_by_channel(1, "web") == ""
    assert s.serve(1, "a", 1) is False


@pytest.mark.level3
def test_rate_limit_blocks_the_n_plus_first_serve_in_window():
    s = CampaignScheduler(window=10, max_impressions_per_window=3)
    s.create_campaign(0, "c1", "email", 5)
    assert s.serve(1, "c1", 1) is True
    assert s.serve(2, "c1", 1) is True
    assert s.serve(3, "c1", 1) is True
    assert s.serve(4, "c1", 1) is False  # 3 already inside (4-10, 4]


@pytest.mark.level3
def test_window_boundary_is_half_open_left_exclusive():
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(0, "c1", "email", 5)
    assert s.serve(100, "c1", 1) is True
    # At t=110 the window is (100, 110]; the impression at exactly 100 has
    # aged out, so the serve is allowed.
    assert s.serve(110, "c1", 1) is True


@pytest.mark.level3
def test_window_boundary_one_tick_early_still_counts():
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(0, "c1", "email", 5)
    assert s.serve(100, "c1", 1) is True
    # At t=109 the window is (99, 109] which still contains 100.
    assert s.serve(109, "c1", 1) is False


@pytest.mark.level3
def test_rate_limits_are_per_campaign_not_global():
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(0, "a", "email", 5)
    s.create_campaign(0, "b", "email", 5)
    assert s.serve(1, "a", 1) is True
    assert s.serve(1, "b", 1) is True  # b has its own budget of impressions
    assert s.serve(1, "a", 1) is False


@pytest.mark.level3
def test_rate_limited_campaign_still_appears_in_listings():
    """Throttling is invisible to the Level 2 methods -- deliberately.

    They now receive a timestamp like every other method, so "they cannot see
    the window" is no longer an excuse: the rule is that listings report
    eligibility (active and funded) and never transient throttle state.
    """
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(0, "a", "email", 5)
    s.set_budget(0, "a", 100)
    s.serve(1, "a", 1)
    assert s.serve(2, "a", 1) is False  # throttled at t=2
    assert s.list_by_channel(2, "email") == "a(priority=5)"
    assert s.top_campaigns(2, 5) == "a(priority=5)"
    assert s.count_active(2) == 1


@pytest.mark.level3
def test_out_of_order_timestamps_are_judged_against_the_given_timestamp():
    """`serve` timestamps are not guaranteed to be non-decreasing.

    An implementation that prunes its impression log against the highest
    timestamp it has ever seen (rather than filtering against the timestamp it
    was handed) gets the second serve here wrong.
    """
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(0, "c", "web", 1)
    assert s.serve(100, "c", 1) is True
    # The clock jumps backwards. Window (40, 50] is empty -- the impression at
    # t=100 lies in the *future* of this call, not in its window.
    assert s.serve(50, "c", 1) is True
    # (45, 55] contains the impression at 50.
    assert s.serve(55, "c", 1) is False
    # (95, 105] contains the impression at 100: the old impression was never
    # discarded just because a lower timestamp came along afterwards.
    assert s.serve(105, "c", 1) is False
    # (101, 111] holds neither 50 nor 100.
    assert s.serve(111, "c", 1) is True


@pytest.mark.level3
def test_out_of_order_serve_respects_the_half_open_boundary_backwards():
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(0, "c", "web", 1)
    assert s.serve(100, "c", 1) is True
    assert s.serve(90, "c", 1) is True  # (80, 90] empty
    # (90, 100] excludes the impression at exactly 90 but includes the one at
    # 100, which is a same-tick earlier serve.
    assert s.serve(100, "c", 1) is False
    assert s.serve(99, "c", 1) is False  # (89, 99] contains 90


@pytest.mark.level3
def test_previous_means_previous_in_call_order_not_lower_timestamp():
    """Every impression recorded so far is a candidate; the window does the filtering.

    An impression recorded earlier but sitting at a *higher* timestamp is simply
    outside (t - W, t] and does not count -- it is not deleted, and it is not
    counted either.
    """
    s = CampaignScheduler(window=10, max_impressions_per_window=2)
    s.create_campaign(0, "c", "email", 1)
    assert s.serve(1000, "c", 1) is True
    assert s.serve(5, "c", 1) is True  # (-5, 5] empty; t=1000 is in the future
    assert s.serve(5, "c", 1) is True  # one prior impression at 5 -> still under 2
    assert s.serve(5, "c", 1) is False  # now two impressions sit in (-5, 5]
    # Back near the future impression: (990, 1000] holds only the t=1000 one.
    assert s.serve(1000, "c", 1) is True
    assert s.serve(1000, "c", 1) is False  # two now


@pytest.mark.level3
def test_constructor_rejects_non_positive_window_or_max_impressions():
    with pytest.raises(ValueError):
        CampaignScheduler(window=0, max_impressions_per_window=5)
    with pytest.raises(ValueError):
        CampaignScheduler(window=-1, max_impressions_per_window=5)
    with pytest.raises(ValueError):
        CampaignScheduler(window=10, max_impressions_per_window=0)
    with pytest.raises(ValueError):
        CampaignScheduler(window=10, max_impressions_per_window=-2)
    # The smallest legal configuration is fine.
    assert CampaignScheduler(window=1, max_impressions_per_window=1).count_active(0) == 0


@pytest.mark.level3
def test_no_argument_constructor_still_works_after_widening():
    """Levels 1 and 2 call `CampaignScheduler()`; both defaults must survive."""
    s = CampaignScheduler()
    s.create_campaign(0, "a", "email", 1)
    assert s.count_active(0) == 1
    for t in range(1, 6):
        assert s.serve(t, "a", 1) is True  # default max_impressions_per_window == 5
    assert s.serve(6, "a", 1) is False  # default window == 60, so all five count


@pytest.mark.level3
def test_delete_and_recreate_clears_budget_and_impressions():
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(0, "a", "email", 5)
    s.set_budget(0, "a", 10)
    s.serve(1, "a", 10)
    assert s.remaining_budget(1, "a") == 0
    s.delete_campaign(1, "a")
    s.create_campaign(1, "a", "email", 5)
    assert s.remaining_budget(1, "a") == -1
    assert s.serve(1, "a", 1) is True  # old impression log is gone


# ===================================================================== #
# Level 4 -- snapshot, restore and audit trail                           #
# ===================================================================== #


@pytest.mark.level4
def test_snapshot_and_restore_round_trip():
    s = CampaignScheduler(window=10, max_impressions_per_window=5)
    s.create_campaign(0, "a", "email", 5)
    s.set_budget(0, "a", 100)
    assert s.snapshot(0, "clean") is True
    s.serve(1, "a", 40)
    s.pause_campaign(2, "a")
    assert s.restore(3, "clean") is True
    assert s.remaining_budget(3, "a") == 100
    assert s.get_campaign(3, "a") == "a(channel=email, priority=5, status=active)"


@pytest.mark.level4
def test_restore_unknown_snapshot_is_false_and_changes_nothing():
    s = CampaignScheduler()
    s.create_campaign(0, "a", "email", 5)
    assert s.restore(1, "never-taken") is False
    assert s.get_campaign(1, "a") == "a(channel=email, priority=5, status=active)"
    assert s.count_active(1) == 1


@pytest.mark.level4
def test_snapshot_name_reused_overwrites_the_earlier_capture():
    s = CampaignScheduler()
    s.create_campaign(0, "a", "email", 5)
    s.snapshot(1, "pin")
    s.create_campaign(2, "b", "email", 3)
    s.snapshot(3, "pin")  # second capture of the same name wins
    s.create_campaign(4, "c", "email", 1)
    assert s.restore(5, "pin") is True
    assert s.count_active(5) == 2
    assert s.get_campaign(5, "b") is not None
    assert s.get_campaign(5, "c") is None


@pytest.mark.level4
def test_restore_to_snapshot_taken_before_campaign_existed():
    s = CampaignScheduler()
    s.snapshot(0, "empty")
    s.create_campaign(1, "a", "email", 5)
    s.set_budget(2, "a", 50)
    assert s.restore(3, "empty") is True
    assert s.get_campaign(3, "a") is None
    assert s.remaining_budget(3, "a") is None
    assert s.count_active(3) == 0
    assert s.history(3, "a") == ""


@pytest.mark.level4
def test_restore_rolls_back_the_sliding_window_impression_log():
    s = CampaignScheduler(window=10, max_impressions_per_window=2)
    s.create_campaign(0, "a", "email", 5)
    assert s.serve(1, "a", 1) is True
    s.snapshot(1, "one-impression")
    assert s.serve(2, "a", 1) is True
    assert s.serve(3, "a", 1) is False  # throttled: 2 impressions in window
    assert s.restore(3, "one-impression") is True
    # The impression at t=2 never happened, so t=3 now fits.
    assert s.serve(3, "a", 1) is True


@pytest.mark.level4
def test_restore_then_mutate_then_restore_again():
    s = CampaignScheduler(window=10, max_impressions_per_window=5)
    s.create_campaign(0, "a", "email", 5)
    s.set_budget(0, "a", 100)
    s.snapshot(0, "early")
    s.serve(1, "a", 30)
    s.create_campaign(1, "b", "push", 2)
    s.snapshot(1, "late")

    assert s.restore(2, "early") is True
    assert s.remaining_budget(2, "a") == 100
    assert s.get_campaign(2, "b") is None

    # Snapshots survive restores, so "late" is still reachable.
    assert s.restore(2, "late") is True
    assert s.remaining_budget(2, "a") == 70
    assert s.get_campaign(2, "b") == "b(channel=push, priority=2, status=active)"

    # Mutate after the second restore, then rewind once more.
    s.serve(2, "a", 20)
    assert s.remaining_budget(2, "a") == 50
    assert s.restore(3, "early") is True
    assert s.remaining_budget(3, "a") == 100
    assert s.count_active(3) == 1


@pytest.mark.level4
def test_history_records_every_state_change_in_order():
    s = CampaignScheduler(window=10, max_impressions_per_window=5)
    s.create_campaign(1, "a", "email", 8)
    s.set_budget(2, "a", 100)
    s.serve(3, "a", 25)
    s.pause_campaign(4, "a")
    s.resume_campaign(5, "a")
    s.delete_campaign(6, "a")
    assert s.history(7, "a") == (
        "create(channel=email, priority=8), set_budget(100), "
        "serve(t=3, cost=25), pause, resume, delete"
    )


@pytest.mark.level4
def test_history_of_unknown_campaign_is_empty_string():
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 1)
    assert s.history(2, "ghost") == ""
    assert isinstance(s.history(2, "ghost"), str)


@pytest.mark.level4
def test_history_survives_deletion_even_though_the_campaign_does_not():
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 1)
    s.delete_campaign(2, "a")
    assert s.get_campaign(3, "a") is None
    assert s.history(3, "a") == "create(channel=email, priority=1), delete"
    # Re-creating the id appends to the same trail.
    s.create_campaign(4, "a", "web", 2)
    assert s.history(5, "a") == (
        "create(channel=email, priority=1), delete, create(channel=web, priority=2)"
    )


@pytest.mark.level4
def test_failed_operations_are_not_recorded_in_history():
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(1, "a", "email", 1)
    s.create_campaign(1, "a", "push", 9)  # duplicate -> rejected
    s.resume_campaign(1, "a")  # already active -> rejected
    s.set_budget(1, "a", -5)  # negative -> rejected
    s.set_budget(2, "a", 10)
    s.serve(3, "a", 99)  # over budget -> rejected
    s.serve(3, "a", 4)
    s.serve(4, "a", 4)  # rate limited -> rejected
    assert s.history(5, "a") == (
        "create(channel=email, priority=1), set_budget(10), serve(t=3, cost=4)"
    )


@pytest.mark.level4
def test_history_is_rolled_back_by_restore():
    s = CampaignScheduler(window=10, max_impressions_per_window=5)
    s.create_campaign(1, "a", "email", 1)
    s.snapshot(2, "s")
    s.pause_campaign(3, "a")
    assert s.history(4, "a") == "create(channel=email, priority=1), pause"
    s.restore(5, "s")
    assert s.history(6, "a") == "create(channel=email, priority=1)"


@pytest.mark.level4
def test_history_is_scoped_per_campaign():
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 1)
    s.create_campaign(1, "b", "push", 2)
    s.pause_campaign(2, "b")
    assert s.history(3, "a") == "create(channel=email, priority=1)"
    assert s.history(3, "b") == "create(channel=push, priority=2), pause"


@pytest.mark.level4
def test_empty_snapshot_name_is_rejected():
    s = CampaignScheduler()
    s.create_campaign(1, "a", "email", 1)
    assert s.snapshot(2, "") is False
    assert s.restore(3, "") is False


@pytest.mark.level4
def test_restore_rolls_back_an_out_of_order_impression():
    """Snapshot/restore and backwards-moving serve timestamps must compose."""
    s = CampaignScheduler(window=10, max_impressions_per_window=1)
    s.create_campaign(0, "a", "email", 5)
    assert s.serve(100, "a", 1) is True
    s.snapshot(100, "after-future-serve")

    # The clock jumps backwards: (40, 50] is empty, so this must succeed.
    assert s.serve(50, "a", 1) is True
    assert s.serve(52, "a", 1) is False  # (42, 52] holds the impression at 50
    assert s.history(52, "a") == (
        "create(channel=email, priority=5), serve(t=100, cost=1), serve(t=50, cost=1)"
    )

    assert s.restore(52, "after-future-serve") is True
    # The t=50 impression never happened, so t=52 is now free...
    assert s.serve(52, "a", 1) is True
    # ...while the surviving t=100 impression still blocks its own window.
    assert s.serve(105, "a", 1) is False
    assert s.history(105, "a") == (
        "create(channel=email, priority=5), serve(t=100, cost=1), serve(t=52, cost=1)"
    )


# --------------------- backward-compatibility guards ------------------ #


@pytest.mark.level4
def test_backcompat_level1_behaviour_on_a_fully_featured_scheduler():
    """Every Level 1 contract must still hold after budgets and snapshots exist."""
    s = CampaignScheduler(window=10, max_impressions_per_window=2)
    s.create_campaign(0, "a", "email", 8)
    s.set_budget(0, "a", 50)
    s.serve(1, "a", 10)
    s.snapshot(1, "mid")
    s.serve(2, "a", 10)

    assert s.create_campaign(3, "a", "push", 1) is False
    assert s.get_campaign(3, "a") == "a(channel=email, priority=8, status=active)"
    assert s.get_campaign(3, "ghost") is None
    assert s.pause_campaign(4, "a") is True
    assert s.pause_campaign(4, "a") is False
    assert s.get_campaign(4, "a") == "a(channel=email, priority=8, status=paused)"
    assert s.resume_campaign(5, "a") is True
    assert s.resume_campaign(5, "a") is False
    assert s.delete_campaign(6, "a") is True
    assert s.get_campaign(6, "a") is None
    assert s.delete_campaign(6, "a") is False


@pytest.mark.level4
def test_backcompat_level2_ranking_after_budgets_and_a_restore():
    """Level 2 ordering and formatting must be unchanged by Levels 3 and 4."""
    s = CampaignScheduler(window=10, max_impressions_per_window=5)
    s.create_campaign(0, "zeta", "email", 5)
    s.create_campaign(0, "alpha", "email", 5)
    s.create_campaign(0, "top", "push", 9)
    s.snapshot(0, "before-spend")

    assert s.list_by_channel(0, "email") == "alpha(priority=5), zeta(priority=5)"
    assert s.top_campaigns(0, 2) == "top(priority=9), alpha(priority=5)"
    assert s.count_active(0) == 3

    s.set_budget(1, "alpha", 10)
    s.serve(1, "alpha", 10)  # alpha exhausted -> drops out
    assert s.list_by_channel(2, "email") == "zeta(priority=5)"
    assert s.count_active(2) == 2

    s.restore(3, "before-spend")
    assert s.list_by_channel(3, "email") == "alpha(priority=5), zeta(priority=5)"
    assert s.top_campaigns(3, 5) == (
        "top(priority=9), alpha(priority=5), zeta(priority=5)"
    )
    assert s.count_active(3) == 3


@pytest.mark.level4
def test_serving_after_restore_behaves_as_if_intervening_serves_never_happened():
    s = CampaignScheduler(window=5, max_impressions_per_window=2)
    s.create_campaign(0, "a", "email", 5)
    s.set_budget(0, "a", 100)
    s.snapshot(0, "t0")

    for t in (1, 2):
        assert s.serve(t, "a", 10) is True
    assert s.serve(3, "a", 10) is False  # throttled
    assert s.remaining_budget(3, "a") == 80

    assert s.restore(3, "t0") is True
    assert s.remaining_budget(3, "a") == 100
    # Full window budget available again, at the very same timestamps.
    assert s.serve(1, "a", 10) is True
    assert s.serve(2, "a", 10) is True
    assert s.serve(3, "a", 10) is False
    assert s.remaining_budget(3, "a") == 80
    assert s.history(3, "a") == (
        "create(channel=email, priority=5), set_budget(100), "
        "serve(t=1, cost=10), serve(t=2, cost=10)"
    )
