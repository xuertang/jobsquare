import importlib, os
_impl = importlib.import_module(os.environ.get("ICF_IMPL", "solution"))
LocaleResolver = _impl.LocaleResolver

import pytest


# ==========================================================================
# Level 1 -- direct storage
# ==========================================================================

@pytest.mark.level1
def test_set_then_get_roundtrip():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    assert r.get_string(2, "en", "cta.book") == "Book now"


@pytest.mark.level1
def test_get_unknown_key_returns_none():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    assert r.get_string(2, "en", "cta.missing") is None


@pytest.mark.level1
def test_get_unknown_locale_returns_none():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    assert r.get_string(2, "ja", "cta.book") is None


@pytest.mark.level1
def test_set_overwrites_existing_value():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    r.set_string(2, "en", "cta.book", "Reserve")
    assert r.get_string(3, "en", "cta.book") == "Reserve"
    assert r.list_keys(4, "en") == "cta.book"


@pytest.mark.level1
def test_delete_removes_and_reports_true():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    assert r.delete_string(2, "en", "cta.book") is True
    assert r.get_string(3, "en", "cta.book") is None
    assert r.list_keys(4, "en") == ""


@pytest.mark.level1
def test_delete_missing_key_returns_false():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    assert r.delete_string(2, "en", "nope") is False


@pytest.mark.level1
def test_delete_on_unknown_locale_returns_false():
    r = LocaleResolver()
    assert r.delete_string(1, "ja", "cta.book") is False


@pytest.mark.level1
def test_list_keys_is_sorted_and_comma_space_joined():
    r = LocaleResolver()
    for t, k in enumerate(("zeta", "alpha", "Mid", "beta"), start=1):
        r.set_string(t, "en", k, "v")
    out = r.list_keys(5, "en")
    assert out == "Mid, alpha, beta, zeta"
    # The separator is a comma AND a space, with no trailing separator,
    # no brackets and no quoting.
    assert "[" not in out and "'" not in out and '"' not in out
    assert not out.endswith(",") and not out.endswith(" ")


@pytest.mark.level1
def test_list_keys_unknown_locale_is_the_empty_string():
    r = LocaleResolver()
    assert r.list_keys(1, "ja") == ""


@pytest.mark.level1
def test_list_keys_of_a_single_key_has_no_separator():
    r = LocaleResolver()
    r.set_string(1, "en", "only", "v")
    assert r.list_keys(2, "en") == "only"


@pytest.mark.level1
def test_locales_are_isolated():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    r.set_string(2, "fr", "cta.book", "Reserver")
    r.delete_string(3, "en", "cta.book")
    assert r.get_string(4, "fr", "cta.book") == "Reserver"
    assert r.list_keys(5, "fr") == "cta.book"


@pytest.mark.level1
def test_empty_string_is_a_real_value():
    r = LocaleResolver()
    r.set_string(1, "en", "footer.note", "")
    assert r.get_string(2, "en", "footer.note") == ""
    assert r.list_keys(3, "en") == "footer.note"


@pytest.mark.level1
def test_timestamps_are_accepted_but_semantically_unused():
    """Spec decision 1: no method reads its timestamp, at any level."""
    r = LocaleResolver()
    r.set_string(10**12, "en", "cta.book", "Book now")
    r.set_string(-100, "en", "cta.save", "Save")
    assert r.get_string(0, "en", "cta.book") == "Book now"
    assert r.get_string(-999, "en", "cta.save") == "Save"
    assert r.list_keys(10**12, "en") == "cta.book, cta.save"
    assert r.delete_string(0, "en", "cta.save") is True
    assert r.list_keys(-100, "en") == "cta.book"


# ==========================================================================
# Level 2 -- fallback chains, coverage
# ==========================================================================

@pytest.mark.level2
def test_resolve_prefers_exact_locale():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    r.set_string(2, "fr", "cta.book", "Reserver")
    r.set_string(3, "fr-CA", "cta.book", "Reserver (CA)")
    assert r.resolve(4, "fr-CA", "cta.book") == "Reserver (CA)"


@pytest.mark.level2
def test_resolve_falls_back_to_language_before_default():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    r.set_string(2, "fr", "cta.book", "Reserver")
    assert r.resolve(3, "fr-CA", "cta.book") == "Reserver"


@pytest.mark.level2
def test_resolve_falls_back_to_default():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    assert r.resolve(2, "fr-CA", "cta.book") == "Book now"
    assert r.resolve(3, "fr", "cta.book") == "Book now"


@pytest.mark.level2
def test_resolve_key_that_exists_nowhere_is_none():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    assert r.resolve(2, "fr-CA", "cta.ghost") is None
    assert r.resolve_with_source(3, "fr-CA", "cta.ghost") is None


@pytest.mark.level2
def test_resolve_when_default_lacks_the_key_but_region_has_it():
    r = LocaleResolver()
    r.set_string(1, "fr-CA", "promo.only", "Promo CA")
    assert r.resolve(2, "fr-CA", "promo.only") == "Promo CA"
    assert r.resolve(3, "fr", "promo.only") is None  # chain never walks downward


@pytest.mark.level2
def test_resolve_with_source_names_the_supplying_locale():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    r.set_string(2, "fr", "cta.book", "Reserver")
    assert r.resolve_with_source(3, "fr-CA", "cta.book") == "Reserver|fr"
    assert r.resolve_with_source(4, "fr", "cta.book") == "Reserver|fr"
    assert r.resolve_with_source(5, "de", "cta.book") == "Book now|en"


@pytest.mark.level2
def test_resolve_with_source_handles_empty_string_value():
    r = LocaleResolver()
    r.set_string(1, "fr", "footer.note", "")
    r.set_string(2, "en", "footer.note", "Fallback")
    assert r.resolve(3, "fr-CA", "footer.note") == ""
    assert r.resolve_with_source(4, "fr-CA", "footer.note") == "|fr"


@pytest.mark.level2
def test_multi_segment_locale_generalizes_step_by_step():
    r = LocaleResolver()
    r.set_string(1, "zh", "cta.book", "zh value")
    assert r.resolve_with_source(2, "zh-Hant-TW", "cta.book") == "zh value|zh"
    r.set_string(3, "zh-Hant", "cta.book", "zh-Hant value")
    assert r.resolve_with_source(4, "zh-Hant-TW", "cta.book") == "zh-Hant value|zh-Hant"


@pytest.mark.level2
def test_default_locale_not_duplicated_when_already_on_chain():
    r = LocaleResolver("fr")
    r.set_string(1, "en", "cta.book", "Book now")
    r.set_string(2, "fr", "cta.book", "Reserver")
    # chain is fr-CA -> fr; "en" is not the default, so it is never consulted
    assert r.resolve_with_source(3, "fr-CA", "cta.book") == "Reserver|fr"
    r.delete_string(4, "fr", "cta.book")
    assert r.resolve(5, "fr-CA", "cta.book") is None


@pytest.mark.level2
def test_set_default_locale_changes_resolution():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    r.set_string(2, "es", "cta.book", "Reservar")
    assert r.resolve_with_source(3, "de", "cta.book") == "Book now|en"
    r.set_default_locale(4, "es")
    assert r.get_default_locale(5) == "es"
    assert r.resolve_with_source(6, "de", "cta.book") == "Reservar|es"


@pytest.mark.level2
def test_default_locale_region_is_not_generalized():
    r = LocaleResolver("en-US")
    r.set_string(1, "en", "cta.book", "Generic english")
    r.set_string(2, "en-US", "cta.book", "US english")
    # chain for fr-CA is fr-CA -> fr -> en-US ; bare "en" is NOT appended
    assert r.resolve_with_source(3, "fr-CA", "cta.book") == "US english|en-US"
    r.delete_string(4, "en-US", "cta.book")
    assert r.resolve(5, "fr-CA", "cta.book") is None


@pytest.mark.level2
def test_coverage_floors_the_percentage():
    r = LocaleResolver()
    for t, k in enumerate(("a", "b", "c"), start=1):
        r.set_string(t, "en", k, "v")
    r.set_string(4, "fr", "a", "v")
    r.set_string(5, "fr", "b", "v")
    assert r.coverage(6, "fr") == 66


@pytest.mark.level2
def test_coverage_ignores_extra_keys_and_fallback():
    r = LocaleResolver()
    r.set_string(1, "en", "a", "v")
    r.set_string(2, "en", "b", "v")
    r.set_string(3, "fr", "a", "v")
    r.set_string(4, "fr", "zz.extra", "v")
    assert r.coverage(5, "fr") == 50


@pytest.mark.level2
def test_coverage_of_empty_and_default_locales():
    r = LocaleResolver()
    r.set_string(1, "en", "a", "v")
    assert r.coverage(2, "ja") == 0          # locale with zero keys
    assert r.coverage(3, "en") == 100        # default covers itself


@pytest.mark.level2
def test_coverage_is_100_when_default_locale_is_empty():
    r = LocaleResolver()
    r.set_string(1, "fr", "a", "v")
    assert r.coverage(2, "fr") == 100
    assert r.coverage(3, "ja") == 100
    assert r.missing_keys(4, "ja") == ""


@pytest.mark.level2
def test_missing_keys_sorted_and_empty_for_default():
    r = LocaleResolver()
    for t, k in enumerate(("delta", "alpha", "charlie", "bravo"), start=1):
        r.set_string(t, "en", k, "v")
    r.set_string(5, "fr", "alpha", "v")
    assert r.missing_keys(6, "fr") == "bravo, charlie, delta"
    assert r.missing_keys(7, "en") == ""


@pytest.mark.level2
def test_missing_keys_is_a_comma_space_joined_string():
    r = LocaleResolver()
    r.set_string(1, "en", "a", "v")
    r.set_string(2, "en", "b", "v")
    out = r.missing_keys(3, "fr")
    assert out == "a, b"
    assert "[" not in out and "'" not in out
    assert not out.endswith(",") and not out.endswith(" ")


# ==========================================================================
# Level 3 -- bounded LRU resolution cache
# ==========================================================================

def _seeded():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    r.set_string(2, "en", "cta.save", "Save")
    r.set_string(3, "fr", "cta.book", "Reserver")
    return r


@pytest.mark.level3
def test_cache_stats_start_at_zero():
    r = LocaleResolver()
    assert r.cache_stats(1) == "hits=0,misses=0,size=0"


@pytest.mark.level3
def test_cache_is_disabled_until_configure_cache_is_called():
    # Capacity is 0 before configure_cache is ever called: nothing is stored,
    # so a repeated lookup misses every single time.
    r = _seeded()
    for t in range(10, 13):
        assert r.resolve(t, "fr-CA", "cta.book") == "Reserver"
    assert r.cache_stats(20) == "hits=0,misses=3,size=0"


@pytest.mark.level3
def test_negative_capacity_raises_value_error():
    r = _seeded()
    with pytest.raises(ValueError):
        r.configure_cache(10, -1)


@pytest.mark.level3
def test_capacity_zero_disables_caching():
    r = _seeded()
    r.configure_cache(10, 0)
    for t in range(11, 14):
        assert r.resolve(t, "fr-CA", "cta.book") == "Reserver"
    assert r.cache_stats(20) == "hits=0,misses=3,size=0"


@pytest.mark.level3
def test_miss_then_hit():
    r = _seeded()
    r.configure_cache(10, 4)
    assert r.resolve(11, "fr-CA", "cta.book") == "Reserver"
    assert r.cache_stats(12) == "hits=0,misses=1,size=1"
    assert r.resolve(13, "fr-CA", "cta.book") == "Reserver"
    assert r.cache_stats(14) == "hits=1,misses=1,size=1"


@pytest.mark.level3
def test_resolve_with_source_shares_the_same_cache_entry():
    r = _seeded()
    r.configure_cache(10, 4)
    r.resolve(11, "fr-CA", "cta.book")
    assert r.resolve_with_source(12, "fr-CA", "cta.book") == "Reserver|fr"
    assert r.cache_stats(13) == "hits=1,misses=1,size=1"


@pytest.mark.level3
def test_capacity_one_evicts_every_time():
    r = _seeded()
    r.configure_cache(10, 1)
    r.resolve(11, "fr-CA", "cta.book")            # miss, size 1
    r.resolve(12, "fr-CA", "cta.save")            # miss, evicts previous
    assert r.cache_stats(13) == "hits=0,misses=2,size=1"
    r.resolve(14, "fr-CA", "cta.book")            # miss again
    assert r.cache_stats(15) == "hits=0,misses=3,size=1"


@pytest.mark.level3
def test_lru_eviction_order_is_exact():
    r = _seeded()
    r.configure_cache(10, 2)
    r.resolve(11, "fr", "cta.book")               # miss -> [fr/book]
    r.resolve(12, "de", "cta.book")               # miss -> [fr/book, de/book]
    r.resolve(13, "fr", "cta.book")               # hit  -> [de/book, fr/book]
    assert r.cache_stats(14) == "hits=1,misses=2,size=2"
    r.resolve(15, "es", "cta.book")               # miss -> evicts de/book
    assert r.cache_stats(16) == "hits=1,misses=3,size=2"
    r.resolve(17, "fr", "cta.book")               # still cached -> hit
    assert r.cache_stats(18) == "hits=2,misses=3,size=2"
    r.resolve(19, "de", "cta.book")               # was evicted -> miss
    assert r.cache_stats(20) == "hits=2,misses=4,size=2"


@pytest.mark.level3
def test_set_on_parent_locale_invalidates_child_resolution():
    r = _seeded()
    r.configure_cache(10, 8)
    assert r.resolve_with_source(11, "fr-CA", "cta.save") == "Save|en"
    assert r.cache_stats(12) == "hits=0,misses=1,size=1"
    # "fr" sits on fr-CA's chain even though the value came from "en"
    r.set_string(13, "fr", "cta.save", "Enregistrer")
    assert r.cache_stats(14) == "hits=0,misses=1,size=0"
    assert r.resolve_with_source(15, "fr-CA", "cta.save") == "Enregistrer|fr"
    assert r.cache_stats(16) == "hits=0,misses=2,size=1"


@pytest.mark.level3
def test_invalidation_is_scoped_to_key_and_chain():
    r = _seeded()
    r.configure_cache(10, 8)
    r.resolve(11, "fr-CA", "cta.book")
    r.set_string(12, "de", "cta.book", "Buchen")       # de is not on fr-CA's chain
    r.set_string(13, "fr", "cta.save", "Enregistrer")  # different key
    assert r.cache_stats(14) == "hits=0,misses=1,size=1"
    r.resolve(15, "fr-CA", "cta.book")
    assert r.cache_stats(16) == "hits=1,misses=1,size=1"


@pytest.mark.level3
def test_set_string_invalidates_even_when_value_is_unchanged():
    r = _seeded()
    r.configure_cache(10, 8)
    r.resolve(11, "fr", "cta.book")
    r.set_string(12, "fr", "cta.book", "Reserver")
    assert r.cache_stats(13) == "hits=0,misses=1,size=0"


@pytest.mark.level3
def test_delete_invalidates_only_when_it_removed_something():
    r = _seeded()
    r.configure_cache(10, 8)
    assert r.resolve(11, "fr-CA", "cta.book") == "Reserver"
    assert r.delete_string(12, "fr", "nope") is False   # no change -> no invalidation
    assert r.cache_stats(13) == "hits=0,misses=1,size=1"
    assert r.delete_string(14, "fr", "cta.book") is True
    assert r.cache_stats(15) == "hits=0,misses=1,size=0"
    assert r.resolve_with_source(16, "fr-CA", "cta.book") == "Book now|en"


@pytest.mark.level3
def test_negative_results_are_cached_and_invalidated():
    r = _seeded()
    r.configure_cache(10, 8)
    assert r.resolve(11, "fr-CA", "cta.ghost") is None
    assert r.cache_stats(12) == "hits=0,misses=1,size=1"
    assert r.resolve(13, "fr-CA", "cta.ghost") is None
    assert r.cache_stats(14) == "hits=1,misses=1,size=1"
    r.set_string(15, "en", "cta.ghost", "Ghost")      # end of the chain
    assert r.cache_stats(16) == "hits=1,misses=1,size=0"
    assert r.resolve(17, "fr-CA", "cta.ghost") == "Ghost"


@pytest.mark.level3
def test_set_default_locale_clears_cache_but_keeps_stats():
    r = _seeded()
    r.set_string(10, "es", "cta.book", "Reservar")
    r.configure_cache(11, 8)
    r.resolve(12, "de", "cta.book")
    r.resolve(13, "de", "cta.book")
    assert r.cache_stats(14) == "hits=1,misses=1,size=1"
    r.set_default_locale(15, "es")
    assert r.cache_stats(16) == "hits=1,misses=1,size=0"
    assert r.resolve_with_source(17, "de", "cta.book") == "Reservar|es"


@pytest.mark.level3
def test_setting_the_default_to_its_current_value_is_a_noop():
    r = _seeded()
    r.configure_cache(10, 8)
    r.resolve(11, "fr-CA", "cta.book")
    r.set_default_locale(12, r.get_default_locale(12))  # no chain changed -> keep cache
    assert r.cache_stats(13) == "hits=0,misses=1,size=1"
    assert r.resolve(14, "fr-CA", "cta.book") == "Reserver"
    assert r.cache_stats(15) == "hits=1,misses=1,size=1"


@pytest.mark.level3
def test_configure_cache_resets_stats_and_entries():
    r = _seeded()
    r.configure_cache(10, 8)
    r.resolve(11, "fr-CA", "cta.book")
    r.resolve(12, "fr-CA", "cta.book")
    assert r.cache_stats(13) == "hits=1,misses=1,size=1"
    r.configure_cache(14, 2)
    assert r.cache_stats(15) == "hits=0,misses=0,size=0"


@pytest.mark.level3
def test_read_only_methods_do_not_touch_the_cache():
    r = _seeded()
    r.configure_cache(10, 8)
    r.resolve(11, "fr-CA", "cta.book")
    before = r.cache_stats(12)
    r.get_string(13, "fr", "cta.book")
    r.list_keys(14, "en")
    r.coverage(15, "fr")
    r.missing_keys(16, "fr")
    r.get_default_locale(17)
    assert r.cache_stats(18) == before == "hits=0,misses=1,size=1"


@pytest.mark.level3
def test_evicted_entries_do_not_resurrect_after_invalidation():
    r = _seeded()
    r.configure_cache(10, 1)
    r.resolve(11, "fr-CA", "cta.book")     # cached
    r.resolve(12, "de", "cta.book")        # evicts fr-CA entry
    r.set_string(13, "fr", "cta.book", "Reserver v2")  # invalidates a gone entry
    assert r.cache_stats(14) == "hits=0,misses=2,size=1"
    assert r.resolve(15, "de", "cta.book") == "Book now"
    assert r.cache_stats(16) == "hits=1,misses=2,size=1"
    assert r.resolve(17, "fr-CA", "cta.book") == "Reserver v2"


# ==========================================================================
# Level 4 -- bulk merge, diff, backward compatibility
# ==========================================================================

@pytest.mark.level4
def test_merge_into_new_locale_adds_everything():
    r = LocaleResolver()
    assert r.merge_bundle(1, "it", {"a": "1", "b": "2"}, "overwrite") == "added=2,updated=0,skipped=0"
    assert r.list_keys(2, "it") == "a, b"


@pytest.mark.level4
def test_merge_empty_mapping_is_a_noop():
    r = LocaleResolver()
    r.set_string(1, "fr", "a", "v")
    assert r.merge_bundle(2, "fr", {}, "prefer_longer") == "added=0,updated=0,skipped=0"
    assert r.merge_bundle(3, "ja", {}, "overwrite") == "added=0,updated=0,skipped=0"
    assert r.list_keys(4, "fr") == "a"
    assert r.list_keys(5, "ja") == ""


@pytest.mark.level4
def test_overwrite_counts_identical_values_as_skipped():
    r = LocaleResolver()
    r.set_string(1, "fr", "a", "same")
    r.set_string(2, "fr", "b", "old")
    out = r.merge_bundle(3, "fr", {"a": "same", "b": "new", "c": "fresh"}, "overwrite")
    assert out == "added=1,updated=1,skipped=1"
    assert r.get_string(4, "fr", "b") == "new"


@pytest.mark.level4
def test_keep_existing_never_updates():
    r = LocaleResolver()
    r.set_string(1, "fr", "a", "old")
    out = r.merge_bundle(2, "fr", {"a": "new", "b": "brand new"}, "keep_existing")
    assert out == "added=1,updated=0,skipped=1"
    assert r.get_string(3, "fr", "a") == "old"
    assert r.get_string(4, "fr", "b") == "brand new"


@pytest.mark.level4
def test_prefer_longer_picks_longer_and_ties_go_to_existing():
    r = LocaleResolver()
    r.set_string(1, "fr", "long", "aaaa")
    r.set_string(2, "fr", "tie", "abcd")
    r.set_string(3, "fr", "short", "ab")
    out = r.merge_bundle(
        4, "fr", {"long": "bb", "tie": "wxyz", "short": "abcdef"}, "prefer_longer"
    )
    assert out == "added=0,updated=1,skipped=2"
    assert r.get_string(5, "fr", "long") == "aaaa"     # incoming was shorter
    assert r.get_string(6, "fr", "tie") == "abcd"      # tie -> existing wins
    assert r.get_string(7, "fr", "short") == "abcdef"  # incoming longer


@pytest.mark.level4
def test_unknown_strategy_raises_value_error_and_changes_nothing():
    r = LocaleResolver()
    r.set_string(1, "fr", "a", "old")
    with pytest.raises(ValueError):
        r.merge_bundle(2, "fr", {"a": "new", "b": "brand new"}, "newest_wins")
    assert r.list_keys(3, "fr") == "a"            # "b" was never added
    assert r.get_string(4, "fr", "a") == "old"    # "a" was never updated
    with pytest.raises(ValueError):
        r.merge_bundle(5, "it", {"x": "1"}, "newest_wins")   # all-new keys still raise
    assert r.list_keys(6, "it") == ""


@pytest.mark.level4
def test_merge_invalidates_cached_resolutions():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    r.configure_cache(2, 8)
    assert r.resolve_with_source(3, "fr-CA", "cta.book") == "Book now|en"
    assert r.cache_stats(4) == "hits=0,misses=1,size=1"
    assert r.merge_bundle(5, "fr", {"cta.book": "Reserver"}, "overwrite") == "added=1,updated=0,skipped=0"
    assert r.cache_stats(6) == "hits=0,misses=1,size=0"
    assert r.resolve_with_source(7, "fr-CA", "cta.book") == "Reserver|fr"


@pytest.mark.level4
def test_fully_skipped_merge_leaves_cache_intact():
    r = LocaleResolver()
    r.set_string(1, "en", "cta.book", "Book now")
    r.set_string(2, "fr", "cta.book", "Reserver")
    r.configure_cache(3, 8)
    r.resolve(4, "fr-CA", "cta.book")
    assert r.merge_bundle(5, "fr", {"cta.book": "x"}, "keep_existing") == "added=0,updated=0,skipped=1"
    assert r.cache_stats(6) == "hits=0,misses=1,size=1"
    r.resolve(7, "fr-CA", "cta.book")
    assert r.cache_stats(8) == "hits=1,misses=1,size=1"


@pytest.mark.level4
def test_diff_locales_does_not_touch_the_cache():
    r = LocaleResolver()
    r.set_string(1, "en", "a", "1")
    r.set_string(2, "fr", "a", "2")
    r.configure_cache(3, 8)
    r.resolve(4, "fr-CA", "a")
    assert r.diff_locales(5, "en", "fr") == "a|differs|1|2"
    assert r.cache_stats(6) == "hits=0,misses=1,size=1"


@pytest.mark.level4
def test_diff_reports_all_three_categories():
    r = LocaleResolver()
    r.set_string(1, "en", "same", "v")
    r.set_string(2, "fr", "same", "v")
    r.set_string(3, "en", "only_a", "A only")
    r.set_string(4, "fr", "only_b", "B only")
    r.set_string(5, "en", "both", "english")
    r.set_string(6, "fr", "both", "french")
    out = r.diff_locales(7, "en", "fr")
    assert out == (
        "both|differs|english|french, "
        "only_a|only_in_a|A only, "
        "only_b|only_in_b|B only"
    )
    # Records are joined with ", " -- no brackets, no quoting, no trailing sep.
    assert "[" not in out and "'" not in out
    assert not out.endswith(",") and not out.endswith(" ")


@pytest.mark.level4
def test_diff_is_direction_sensitive():
    r = LocaleResolver()
    r.set_string(1, "en", "k", "english")
    r.set_string(2, "fr", "j", "french")
    assert r.diff_locales(3, "fr", "en") == "j|only_in_a|french, k|only_in_b|english"


@pytest.mark.level4
def test_diff_against_itself_and_unknown_locales_is_empty():
    r = LocaleResolver()
    r.set_string(1, "en", "a", "v")
    assert r.diff_locales(2, "en", "en") == ""
    assert r.diff_locales(3, "ja", "ko") == ""
    assert r.diff_locales(4, "ja", "en") == "a|only_in_b|v"


@pytest.mark.level4
def test_diff_sorts_by_key_not_by_formatted_record():
    """The trap survives the change from a list return to a ", "-joined string.

    Sorting happens *before* the join, so the join never enters the comparison:
    what a naive implementation sorts is still the record strings themselves.
    With keys "a" and "ab" the records are "a|only_in_a|1" and "ab|only_in_a|2",
    and they disagree at index 1, where '|' (0x7C) sorts after 'b' (0x62). So
    sorted(records) puts "ab" first while sorting by key puts "a" first, and the
    two orders produce two different output strings. The assertions below pin
    the correct one and prove the naive one is genuinely different.
    """
    r = LocaleResolver()
    r.set_string(1, "en", "a", "1")
    r.set_string(2, "en", "ab", "2")
    out = r.diff_locales(3, "en", "fr")
    assert out == "a|only_in_a|1, ab|only_in_a|2"
    # The divergence is real, not hypothetical: sorting the rendered records
    # would have produced the other string.
    naive = ", ".join(sorted(["a|only_in_a|1", "ab|only_in_a|2"]))
    assert naive == "ab|only_in_a|2, a|only_in_a|1"
    assert out != naive


@pytest.mark.level4
def test_diff_treats_empty_string_as_a_difference():
    r = LocaleResolver()
    r.set_string(1, "en", "note", "")
    r.set_string(2, "fr", "note", "x")
    assert r.diff_locales(3, "en", "fr") == "note|differs||x"


@pytest.mark.level4
def test_timestamp_is_unused_at_level_4_too():
    """Spec decision 1: still no time semantics anywhere, Level 4 included."""
    def run(t):
        r = LocaleResolver()
        r.configure_cache(t, 4)
        r.merge_bundle(t, "en", {"a": "1", "b": "22"}, "overwrite")
        r.merge_bundle(t, "fr", {"a": "1", "b": "3"}, "prefer_longer")
        return (
            r.resolve_with_source(t, "fr-CA", "b"),
            r.coverage(t, "fr"),
            r.missing_keys(t, "fr"),
            r.list_keys(t, "fr"),
            r.diff_locales(t, "en", "fr"),
            r.cache_stats(t),
        )

    assert run(-100) == run(0) == run(10**12)
    assert run(0) == ("3|fr", 100, "", "a, b", "b|differs|22|3", "hits=0,misses=1,size=1")


@pytest.mark.level4
def test_backward_compatible_level1_behaviour():
    r = LocaleResolver()
    r.configure_cache(1, 4)
    r.merge_bundle(2, "en", {"a": "1", "b": "2"}, "overwrite")
    r.resolve(3, "fr-CA", "a")
    # Level 1 contract must be untouched by caching and merging
    r.set_string(4, "en", "c", "3")
    assert r.get_string(5, "en", "c") == "3"
    assert r.get_string(6, "fr", "a") is None
    assert r.list_keys(7, "en") == "a, b, c"
    assert r.delete_string(8, "en", "b") is True
    assert r.delete_string(9, "en", "b") is False
    assert r.list_keys(10, "en") == "a, c"


@pytest.mark.level4
def test_backward_compatible_level2_behaviour():
    r = LocaleResolver()
    r.configure_cache(1, 2)
    r.merge_bundle(2, "en", {"a": "en-a", "b": "en-b", "c": "en-c"}, "overwrite")
    r.merge_bundle(3, "fr", {"a": "fr-a"}, "keep_existing")
    r.merge_bundle(4, "fr-CA", {"b": "frca-b"}, "prefer_longer")
    assert r.resolve_with_source(5, "fr-CA", "a") == "fr-a|fr"
    assert r.resolve_with_source(6, "fr-CA", "b") == "frca-b|fr-CA"
    assert r.resolve_with_source(7, "fr-CA", "c") == "en-c|en"
    assert r.resolve(8, "fr-CA", "zzz") is None
    assert r.coverage(9, "fr") == 33
    assert r.missing_keys(10, "fr") == "b, c"
    r.set_default_locale(11, "fr")
    assert r.coverage(12, "fr") == 100
    assert r.resolve_with_source(13, "fr-CA", "c") is None
