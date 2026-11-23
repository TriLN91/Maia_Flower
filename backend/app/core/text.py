import re
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_length: int = 120) -> str:
    """Tạo slug từ tiếng Việt: "Pastel Ngọt Ngào" -> "pastel-ngot-ngao".

    NFKD tách dấu ra khỏi chữ cái, nhưng "đ/Đ" là chữ cái riêng (không phải d + dấu)
    nên phải thay tay trước.
    """
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    slug = _NON_SLUG.sub("-", text.lower()).strip("-")
    return slug[:max_length].rstrip("-")
