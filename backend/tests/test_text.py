import pytest

from app.core.text import slugify


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pastel Ngọt Ngào", "pastel-ngot-ngao"),
        ("Đỏ Rực Đam Mê", "do-ruc-dam-me"),
        ("  Hồng   &  Baby!! ", "hong-baby"),
        ("Tulip Hà Lan 2026", "tulip-ha-lan-2026"),
        ("Cẩm tú cầu – Ước nguyện", "cam-tu-cau-uoc-nguyen"),
        ("!!!", ""),
    ],
)
def test_slugify_vietnamese(text, expected):
    assert slugify(text) == expected


def test_slugify_respects_max_length_without_trailing_dash():
    assert slugify("a b c d e f", max_length=4) == "a-b"
