"""Статистика для обзорной страницы: ряды по дням, распределения, сведения
о системе и счётчики разделов для боковой панели."""
import logging
import platform
import time
from datetime import datetime, timedelta
from importlib.metadata import PackageNotFoundError, version

from sqlalchemy import Date, DateTime, func

log = logging.getLogger(__name__)

TONES = ("violet", "blue", "teal", "amber", "rose")
COUNTS_TTL = 60


def daily_series(site, spec):
    """Количество записей по дням за ``days`` дней и итоги за сегодня,
    7 и 30 дней. spec: title, model, date_attr, scope (callable), days,
    distinct — имя колонки: считать разные значения (например, user_id —
    уникальные пользователи; итоги за 7 и 30 дней тогда тоже уникальные,
    а не сумма по дням)."""
    model = spec["model"]
    column = getattr(model, spec["date_attr"])
    days = int(spec.get("days", 14))
    today = site.now().date()
    since = today - timedelta(days=max(days, 30) - 1)
    is_date = isinstance(column.type, Date) and not isinstance(column.type, DateTime)

    def bound(d):
        return d if is_date else datetime.combine(d, datetime.min.time())

    def base():
        query = model.query
        if spec.get("scope"):
            query = spec["scope"](query)
        return query

    distinct_col = getattr(model, spec["distinct"]) if spec.get("distinct") else None
    counter = func.count(func.distinct(distinct_col)) if distinct_col is not None else func.count()
    day = column if is_date else func.date(column)
    rows = (
        base().filter(column >= bound(since))
        .with_entities(day.label("day"), counter.label("n"))
        .group_by(day)
        .all()
    )
    by_day = {}
    for d, n in rows:
        if isinstance(d, str):
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        elif isinstance(d, datetime):
            d = d.date()
        by_day[d] = int(n)

    points = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        points.append({"label": d.strftime("%d.%m"), "value": by_day.get(d, 0)})

    def total(last):
        start = today - timedelta(days=last - 1)
        if distinct_col is None:
            return sum(n for d, n in by_day.items() if d >= start)
        return int(base().filter(column >= bound(start)).with_entities(counter).scalar() or 0)

    return {
        "title": spec.get("title", ""),
        "points": points,
        "today": by_day.get(today, 0),
        "week": total(7),
        "month": total(30),
    }


def breakdown(spec):
    rows = spec["rows"]() if callable(spec["rows"]) else list(spec["rows"])
    rows = [(str(label), int(value or 0)) for label, value in rows]
    top = max([v for _, v in rows] or [0])
    return {
        "title": spec.get("title", ""),
        "icon": spec.get("icon", "chart"),
        "rows": [
            {"label": label, "value": value, "pct": round(value * 100 / top) if top else 0}
            for label, value in rows
        ],
        "total": sum(v for _, v in rows),
    }


def _pkg_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return "—"


def system_info(site):
    rows = [
        ("Приложение", site.brand),
        ("Python", platform.python_version()),
        ("Flask", _pkg_version("flask")),
        ("eres-admin", _pkg_version("eres-admin")),
    ]
    try:
        engine = site.db.engine
        dialect = engine.dialect.name
        info = getattr(engine.dialect, "server_version_info", None)
        if info is None:
            with engine.connect() as conn:
                engine.dialect.initialize(conn)
            info = engine.dialect.server_version_info
        db_version = ".".join(str(x) for x in (info or ())[:2])
        name = {"postgresql": "PostgreSQL", "sqlite": "SQLite", "mysql": "MySQL"}.get(dialect, dialect)
        rows.append(("База данных", f"{name} {db_version}".strip()))
    except Exception:                                      # noqa: BLE001
        rows.append(("База данных", "—"))
    return rows


def nav_counts(site):
    cached = getattr(site, "_nav_counts", None)
    if cached and time.monotonic() - cached[0] < COUNTS_TTL:
        return cached[1]
    counts = {}
    for key, ma in site._models.items():
        try:
            counts[key] = ma.count()
        except Exception:                                  # noqa: BLE001
            site.db.session.rollback()
    site._nav_counts = (time.monotonic(), counts)
    return counts


def short_number(n):
    if n is None:
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    return str(n)
