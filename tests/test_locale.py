import pytest

from ops_common.locale import normalize_locale


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "en-US"), ("zh", "zh-CN"), ("zh_cn", "zh-CN"), ("en", "en-US"), ("en-US", "en-US")],
)
def test_normalize_locale(value: str | None, expected: str) -> None:
    assert normalize_locale(value) == expected


def test_normalize_locale_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Unsupported locale"):
        normalize_locale("fr-FR")
