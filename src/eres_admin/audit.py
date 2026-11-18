"""Журнал изменений, сделанных через админку.

Таблица ``eres_admin_log`` создаётся движком при подключении (если её нет).
Оба приложения могут работать с одной базой, поэтому у каждой записи
есть ``site_code`` — журнал каждой админки показывает только свои записи.
"""
import json
import logging
from datetime import datetime

from .utils import format_value

log = logging.getLogger(__name__)

_MODELS = {}

ACTION_LABELS = {
    "create": "Создание",
    "update": "Изменение",
    "delete": "Удаление",
    "export": "Выгрузка",
}

SECRET_MARK = "скрыто"


def get_log_model(db):
    key = id(db)
    if key in _MODELS:
        return _MODELS[key]

    class EresAdminLog(db.Model):
        __tablename__ = "eres_admin_log"
        __table_args__ = {"extend_existing": True}

        id = db.Column(db.Integer, primary_key=True)
        site_code = db.Column(db.String(64), nullable=False, index=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
        user_id = db.Column(db.Integer, nullable=True)
        user_label = db.Column(db.String(255), nullable=True)
        model_key = db.Column(db.String(64), nullable=False, index=True)
        model_name = db.Column(db.String(255), nullable=True)
        object_id = db.Column(db.String(64), nullable=True, index=True)
        object_label = db.Column(db.String(255), nullable=True)
        action = db.Column(db.String(16), nullable=False)
        changes = db.Column(db.Text, nullable=True)

        @property
        def action_label(self):
            return ACTION_LABELS.get(self.action, self.action)

        @property
        def change_list(self):
            try:
                return json.loads(self.changes or "[]")
            except ValueError:
                return []

    _MODELS[key] = EresAdminLog
    return EresAdminLog


def ensure_table(app, db, model):
    with app.app_context():
        try:
            model.__table__.create(bind=db.engine, checkfirst=True)
        except Exception as exc:                           # noqa: BLE001
            log.warning("eres-admin: журнал изменений недоступен: %s", exc)


def snapshot(obj, fields):
    return {f.name: getattr(obj, f.name, None) for f in fields if not f.readonly}


def describe_value(field, value):
    if field.is_secret:
        return SECRET_MARK if value else "—"
    return format_value(value, limit=200)


def diff(fields, before, obj, creating):
    changes = []
    for f in fields:
        if f.readonly:
            continue
        new = getattr(obj, f.name, None)
        if creating:
            if new in (None, "", False):
                continue
            changes.append({"field": f.label, "old": None, "new": describe_value(f, new)})
            continue
        old = before.get(f.name)
        if old == new:
            continue
        changes.append({"field": f.label, "old": describe_value(f, old), "new": describe_value(f, new)})
    return changes
