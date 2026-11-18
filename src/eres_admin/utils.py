import os
import re
from datetime import date, datetime

from werkzeug.utils import secure_filename


def slug(name):
    out = []
    for i, ch in enumerate(name):
        if ch == "_":
            out.append("-")
            continue
        if ch.isupper() and i and name[i - 1] not in "_-" and not name[i - 1].isupper():
            out.append("-")
        out.append(ch.lower())
    return "".join(out).strip("-")


_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya", "і": "i", "ў": "u",
}


def translit(text):
    out = []
    for ch in text or "":
        rep = _TRANSLIT.get(ch.lower())
        if rep is None:
            out.append(ch)
        elif ch.isupper() and rep:
            out.append(rep[0].upper() + rep[1:])
        else:
            out.append(rep)
    return "".join(out)


def safe_upload_name(original):
    """ASCII-имя файла для сохранения на диск (кириллица транслитерируется),
    расширение сохраняется."""
    original = original or "file"
    stem, ext = os.path.splitext(original)
    ext = "." + re.sub(r"[^A-Za-z0-9]", "", ext).lower()[:12] if ext else ""
    stem = secure_filename(translit(stem)).strip("._-")[:80]
    if not stem:
        stem = "file-" + os.urandom(4).hex()
    return stem + ext


def parse_dt(raw, fmt):
    try:
        return datetime.strptime(raw, fmt)
    except ValueError:
        return None


LABEL_ATTRS = (
    "full_name", "name", "title", "fio", "label", "login", "email", "code",
    "NameProduct", "NameUnit", "CodeUnit", "CodeProduct",
)


def smart_label(obj, prefer=None):
    if obj is None:
        return "—"
    for attr in ((prefer,) if prefer else ()) + LABEL_ATTRS:
        if not attr:
            continue
        try:
            value = getattr(obj, attr, None)
        except Exception:                                  # noqa: BLE001
            value = None
        if value:
            return str(value)
    try:
        pk = getattr(obj, obj.__mapper__.primary_key[0].name)
    except Exception:                                      # noqa: BLE001
        pk = "?"
    return f"{obj.__class__.__name__} #{pk}"


def is_model_instance(val):
    return hasattr(val, "__mapper__") and hasattr(val, "__table__")


def format_value(val, limit=80):
    if val is None or val == "":
        return "—"
    if isinstance(val, bool):
        return "Да" if val else "Нет"
    if isinstance(val, datetime):
        return val.strftime("%d.%m.%Y %H:%M")
    if isinstance(val, date):
        return val.strftime("%d.%m.%Y")
    text = smart_label(val) if is_model_instance(val) else str(val)
    if limit and len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def initials(text):
    parts = [p for p in re.split(r"[\s@._-]+", text or "") if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()
