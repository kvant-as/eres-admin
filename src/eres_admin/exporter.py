"""Выгрузка всей базы данных: ZIP-архив, по CSV-файлу на каждую таблицу.

CSV — UTF-8 с BOM и разделителем «;», чтобы Excel открывал файл без
мастера импорта. Колонки из ``AdminSite.export_exclude_columns`` (хэши
паролей, токены сброса) в архив не попадают.
"""
import csv
import io
import json
import tempfile
import zipfile
from datetime import date, datetime
from decimal import Decimal

from flask import send_file
from flask_login import current_user
from sqlalchemy import inspect, text

from .site import current_site
from .views import bp


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


@bp.route("/_export/database.zip")
def export_database():
    site = current_site()
    engine = site.db.engine
    inspector = inspect(engine)
    quote = engine.dialect.identifier_preparer.quote
    excluded = site.export_exclude_columns
    summary = []

    buffer = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive, engine.connect() as conn:
        for table in sorted(inspector.get_table_names()):
            columns = [c["name"] for c in inspector.get_columns(table)]
            kept = [c for c in columns if c not in excluded]
            dropped = [c for c in columns if c in excluded]
            if not kept:
                continue
            sql = text(f"SELECT {', '.join(quote(c) for c in kept)} FROM {quote(table)}")
            result = conn.execution_options(stream_results=True).execute(sql)
            rows = 0
            with archive.open(f"{table}.csv", "w") as raw:
                stream = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                writer = csv.writer(stream, delimiter=";")
                writer.writerow(kept)
                for row in result:
                    writer.writerow([_cell(v) for v in row])
                    rows += 1
                stream.flush()
                stream.detach()
            summary.append((table, rows, dropped))

        stamp = site.now()
        lines = [
            f"Выгрузка базы данных: {site.brand}",
            f"Дата: {stamp:%d.%m.%Y %H:%M}",
            f"Выгрузил: {site.user_label(current_user)}",
            "",
            "Таблица; строк; исключённые колонки",
        ]
        lines += [f"{t}; {n}; {', '.join(d) or '—'}" for t, n, d in summary]
        archive.writestr("README.txt", "﻿" + "\n".join(lines) + "\n")

    total = sum(n for _, n, _ in summary)
    model = site.log_model
    if model is not None:
        try:
            site.db.session.add(model(
                site_code=site.code, created_at=site.now(),
                user_id=getattr(current_user, "id", None),
                user_label=site.user_label(current_user)[:255],
                model_key="_database", model_name="База данных",
                object_id=None, object_label="Выгрузка всей базы в CSV", action="export",
                changes=json.dumps([{"field": "Таблиц", "old": None, "new": str(len(summary))},
                                    {"field": "Строк", "old": None, "new": str(total)}], ensure_ascii=False),
            ))
            site.db.session.commit()
        except Exception:                                  # noqa: BLE001
            site.db.session.rollback()

    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{site.code}-database-{stamp:%Y%m%d-%H%M}.zip",
    )
