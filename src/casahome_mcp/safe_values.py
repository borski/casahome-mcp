"""Conservative text checks for exact values used in document write previews."""

from unicodedata import category

from .projections import _URL_VALUE

UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})


def exact_safe_text(value: object, *, maximum: int, nonblank: bool = False) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= maximum
        and (not nonblank or bool(value.strip()))
        and not _URL_VALUE.search(value)
        and not any(category(char) in UNSAFE_CATEGORIES for char in value)
    )
