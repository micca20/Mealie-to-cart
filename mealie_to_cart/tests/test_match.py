from mealie_to_cart.match import parse_size, score_relevance, choose_best, ChosenProduct
from mealie_to_cart.models import NormalizedItem, WalmartCandidate


def _item(query="honey", ounces=None, grams=None):
    return NormalizedItem(raw=query, query=query, ounces=ounces, grams=grams)


def _cand(title="Honey", size_text=None, url="https://walmart.com/p/1"):
    return WalmartCandidate(title=title, url=url, size_text=size_text)


def test_parse_size_oz():
    assert parse_size("12 oz") is not None
    assert abs(parse_size("12 oz") - 12.0) < 0.01


def test_parse_size_lb():
    assert abs(parse_size("2 lb") - 32.0) < 0.01


def test_parse_size_grams():
    result = parse_size("500 g")
    assert result is not None
    assert abs(result - (500 / 28.3495)) < 0.1


def test_parse_size_none():
    assert parse_size(None) is None
    assert parse_size("no size here") is None


def test_exact_size_match():
    item = _item("honey", ounces=12.0)
    candidates = [
        _cand("Honey Bear", "8 oz", "https://walmart.com/p/1"),
        _cand("Honey Jar", "12 oz", "https://walmart.com/p/2"),
        _cand("Honey Tub", "24 oz", "https://walmart.com/p/3"),
    ]
    result = choose_best(item, candidates)
    assert result is not None
    assert abs(result.size_oz - 12.0) < 0.01
    assert not result.undersized


def test_closest_bigger_size():
    item = _item("honey", ounces=10.0)
    candidates = [
        _cand("Honey Small", "8 oz", "https://walmart.com/p/1"),
        _cand("Honey Medium", "16 oz", "https://walmart.com/p/2"),
        _cand("Honey Large", "32 oz", "https://walmart.com/p/3"),
    ]
    result = choose_best(item, candidates)
    assert result is not None
    assert abs(result.size_oz - 16.0) < 0.01
    assert not result.undersized


def test_undersized_fallback():
    item = _item("honey", ounces=48.0)
    candidates = [
        _cand("Honey Small", "8 oz", "https://walmart.com/p/1"),
        _cand("Honey Medium", "16 oz", "https://walmart.com/p/2"),
    ]
    result = choose_best(item, candidates)
    assert result is not None
    assert result.undersized


def test_no_size_uses_relevance():
    item = _item("organic honey")
    candidates = [
        _cand("Sugar Syrup", None, "https://walmart.com/p/1"),
        _cand("Organic Honey Raw", None, "https://walmart.com/p/2"),
    ]
    result = choose_best(item, candidates)
    assert result is not None
    assert "organic" in result.candidate.title.lower() or "honey" in result.candidate.title.lower()


def test_empty_candidates():
    item = _item("honey")
    assert choose_best(item, []) is None
