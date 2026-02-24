from mealie_to_cart.normalize import normalize_line


def test_fraction_and_grams_and_or_split():
    raw = "1/3 cup (75 grams) melted coconut oil or extra-virgin olive oil"
    n = normalize_line(raw)

    assert n.quantity == 1 / 3
    assert n.unit == "cup"
    assert n.grams == 75.0
    assert n.alt_query == "extra-virgin olive oil"


def test_unicode_fraction():
    raw = "½ teaspoon salt"
    n = normalize_line(raw)
    assert n.quantity == 0.5
    assert n.unit == "tsp"


def test_mixed_number():
    raw = "1 3/4 cups (220 grams) flour"
    n = normalize_line(raw)
    assert n.quantity == 1.75
    assert n.unit == "cup"
    assert n.grams == 220.0
