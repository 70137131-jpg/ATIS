"""TTL cache behaviour tests."""

from services import cache


def test_cache_disabled_by_default_always_computes(app):
    cache.clear()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    with app.app_context():
        # Default STATS_CACHE_SECONDS is 0 -> caching bypassed.
        assert cache.get_or_compute("k", compute) == 1
        assert cache.get_or_compute("k", compute) == 2
        assert calls["n"] == 2


def test_cache_serves_within_ttl_and_expires(app):
    cache.clear()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    with app.app_context():
        app.config["STATS_CACHE_SECONDS"] = 30
        # Fixed clock: first computes, second is served from cache.
        assert cache.get_or_compute("k", compute, now=1000.0) == 1
        assert cache.get_or_compute("k", compute, now=1010.0) == 1
        assert calls["n"] == 1
        # After the TTL passes, it recomputes.
        assert cache.get_or_compute("k", compute, now=1031.0) == 2
        assert calls["n"] == 2


def test_cache_keys_are_independent(app):
    cache.clear()

    with app.app_context():
        app.config["STATS_CACHE_SECONDS"] = 30
        assert cache.get_or_compute("a", lambda: "A", now=1.0) == "A"
        assert cache.get_or_compute("b", lambda: "B", now=1.0) == "B"
        assert cache.get_or_compute("a", lambda: "X", now=2.0) == "A"
