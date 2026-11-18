from datetime import datetime

from flask import abort, current_app, request, url_for
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, or_

from . import icons
from .audit import ensure_table, get_log_model
from .utils import format_value, slug, smart_label

BLUEPRINT = "eres_admin"
PER_PAGE_CHOICES = (25, 50, 100)

COLUMN_LABELS = {
    "id": "ID", "email": "Email", "login": "Логин", "organization": "Организация",
    "org_role": "Роль", "begin_time": "Создан", "created_time": "Создана",
    "created_at": "Создано", "title": "Заголовок", "views_count": "Просмотры",
    "year": "Год", "quarter": "Квартал", "user": "Пользователь", "code": "Код",
    "name": "Название", "full_name": "Название", "okpo": "ОКПО", "ynp": "УНП",
    "region": "Регион", "ministry": "Министерство", "status": "Статус",
    "number": "Номер", "note": "Примечание", "app": "Приложение",
    "first_seen": "Впервые", "last_active": "Последняя активность",
}


class ModelAdmin:
    def __init__(self, site, model, name, group="Прочее", key=None,
                 list_display=None, list_badges=(), list_format=None,
                 search=(), order_by="-id", per_page=25,
                 can_create=True, can_edit=True, can_delete=True,
                 fields=(), readonly=False, stat_label=None, stat_count=None,
                 on_save=None, scope_query=None, icon=None, description=None):
        self.site = site
        self.model = model
        self.name = name
        self.group = group
        self.key = key or slug(model.__name__)
        self.is_link = False
        self.pk_name = model.__mapper__.primary_key[0].name
        self.list_display = [
            tuple(d) if isinstance(d, (tuple, list)) else (d, self._column_label(d))
            for d in (list_display or [self.pk_name])
        ]
        self._badge_labels = {}
        names = []
        for badge in list_badges:
            if isinstance(badge, (tuple, list)):
                names.append(badge[0])
                self._badge_labels[badge[0]] = badge[1]
            else:
                names.append(badge)
        self.list_badges = tuple(names)
        self.list_format = dict(list_format or {})
        self.search = tuple(search)
        self.order_by = order_by
        self.per_page = per_page
        self.readonly = readonly
        self.can_create = can_create and not readonly
        self.can_edit = can_edit and not readonly
        self.can_delete = can_delete and not readonly
        self.fields = list(fields)
        self.stat_label = stat_label
        self.stat_count = stat_count
        self.on_save = on_save
        self.scope_query = scope_query
        self.icon = icon or icons.guess_for_key(self.key)
        self.description = description

    def _column_label(self, name):
        for f in getattr(self, "fields", []) or []:
            if f.name == name:
                return f.label
        return name

    def finalize(self):
        labels = {f.name: f.label for f in self.fields}
        self.list_display = [
            (name, labels.get(name) or COLUMN_LABELS.get(name, name) if label == name else label)
            for name, label in self.list_display
        ]

    @property
    def columns(self):
        return self.model.__table__.columns

    def is_column(self, name):
        return self.columns.get(name) is not None

    def is_compact(self, name):
        col = self.columns.get(name)
        return col is not None and isinstance(col.type, (Integer, Numeric, Float, Date, DateTime))

    @property
    def sortable(self):
        return {name for name, _ in self.list_display if self.is_column(name)}

    @property
    def filters(self):
        out = []
        for name in self.list_badges:
            col = self.columns.get(name)
            if col is not None and isinstance(col.type, Boolean):
                out.append((name, self.badge_label(name)))
        return out

    def scoped(self):
        q = self.model.query
        if self.scope_query:
            q = self.scope_query(q)
        return q

    def base_query(self, sort=None):
        q = self.scoped()
        order = sort or self.order_by
        col = order.lstrip("-")
        if self.is_column(col) or hasattr(self.model, col):
            attr = getattr(self.model, col)
            q = q.order_by(attr.desc().nullslast() if order.startswith("-") else attr.asc().nullsfirst())
        if sort and col != self.pk_name:
            pk = getattr(self.model, self.pk_name)
            q = q.order_by(pk.desc())
        return q

    def search_query(self, q, term):
        if not term or not self.search:
            return q
        clauses = []
        for name in self.search:
            col = self.columns.get(name)
            if col is not None and isinstance(col.type, (String, Text)):
                clauses.append(getattr(self.model, name).ilike(f"%{term}%"))
        return q.filter(or_(*clauses)) if clauses else q

    def filter_query(self, q, values):
        for name, _ in self.filters:
            value = values.get(name)
            if value == "1":
                q = q.filter(getattr(self.model, name).is_(True))
            elif value == "0":
                q = q.filter(or_(getattr(self.model, name).is_(False), getattr(self.model, name).is_(None)))
        return q

    def form_fields(self, creating):
        if creating:
            return [f for f in self.fields if not f.readonly]
        return [f for f in self.fields if not f.create_only]

    def sections(self, field_views):
        out, index = [], {}
        for fv in field_views:
            title = fv["spec"].section or "Основное"
            if title not in index:
                index[title] = {"title": title, "fields": []}
                out.append(index[title])
            index[title]["fields"].append(fv)
        return out

    def cell(self, obj, name):
        if name in self.list_format:
            return self.list_format[name](obj)
        try:
            value = getattr(obj, name, None)
        except Exception:                                  # noqa: BLE001
            value = None
        field = self._field(name)
        if field is not None and field.choices and value not in (None, ""):
            labels = {str(v): label for v, label in field.choices}
            return labels.get(str(value), format_value(value))
        return format_value(value)

    def _field(self, name):
        return next((f for f in self.fields if f.name == name), None)

    def badge_label(self, name):
        if name in self._badge_labels:
            return self._badge_labels[name]
        field = self._field(name)
        return field.label if field else COLUMN_LABELS.get(name, name)

    def badge_on(self, obj, name):
        try:
            return bool(getattr(obj, name, False))
        except Exception:                                  # noqa: BLE001
            return False

    def title(self, obj):
        return smart_label(obj)

    def pk(self, obj):
        return getattr(obj, self.pk_name)

    def count(self):
        if self.stat_count:
            return self.stat_count()
        return self.scoped().count()

    def get_obj(self, pk):
        pk_col = getattr(self.model, self.pk_name)
        return self.scoped().filter(pk_col == pk).first()

    def detail_rows(self, obj):
        rows = []
        for col in self.columns:
            rows.append((col.name, format_value(getattr(obj, col.name, None), limit=400)))
        return rows

    @property
    def url(self):
        return url_for(f"{BLUEPRINT}.list_view", key=self.key)


class NavLink:
    def __init__(self, label, endpoint, group, icon=None):
        self.name = label
        self.group = group
        self.endpoint = endpoint
        self.is_link = True
        self.icon = icon or "dot"
        self.key = None

    @property
    def url(self):
        try:
            return url_for(self.endpoint)
        except Exception:                                  # noqa: BLE001
            return "#"


class AdminSite:
    """Административная панель приложения.

    db — экземпляр Flask-SQLAlchemy приложения; now — функция текущего
    времени для журнала (по умолчанию datetime.utcnow); is_admin — проверка
    доступа, по умолчанию атрибут ``is_admin`` текущего пользователя.
    """

    def __init__(self, brand, db=None,
                 url_prefix="/admin", site_endpoint=None,
                 login_endpoint="auth.login", logout_endpoint="auth.logout",
                 code=None, theme_storage_key="eres-admin-theme", now=None,
                 is_admin=None, user_label=None,
                 export_exclude_columns=("password", "reset_password_token"),
                 title="eres-admin"):
        self.brand = brand
        self.title = title
        self.db = db
        self.url_prefix = url_prefix
        self.site_endpoint = site_endpoint
        self.login_endpoint = login_endpoint
        self.logout_endpoint = logout_endpoint
        self.code = code or slug(brand)
        self.theme_storage_key = theme_storage_key
        self.now = now or datetime.utcnow
        self.is_admin = is_admin or (lambda user: bool(getattr(user, "is_admin", False)))
        self.user_label = user_label or _default_user_label
        self.export_exclude_columns = set(export_exclude_columns or ())

        self._models = {}
        self._links = []
        self._files = {}
        self._dash = {"greeting_attr": None, "stats": [], "online_count": None, "actions": [], "panels": [],
                      "charts": [], "breakdowns": []}
        self.log_model = None

    def register(self, model, **kw):
        ma = ModelAdmin(self, model, **kw)
        ma.finalize()
        self._models[ma.key] = ma
        return ma

    def link(self, label, endpoint, group="Прочее", icon=None):
        self._links.append(NavLink(label, endpoint, group, icon=icon))

    def files(self, key, root, name="Файлы", group="Служебные", icon="folder", describe=None, max_upload_mb=50):
        """Раздел для работы с папкой на диске: просмотр, загрузка, создание
        папок, переименование, замена, правка текстовых файлов, удаление.
        root — путь или функция, возвращающая путь (например, из app.config)."""
        from .files import FileSection
        self._files[key] = FileSection(key, root, name, group, icon, describe, max_upload_mb)

    def dashboard(self, greeting_attr=None, stats=(), online_count=None, actions=(), panels=(),
                  charts=(), breakdowns=()):
        """charts — ряды по дням для графика (вкладки):
        {"title", "model", "date_attr", "scope"=None, "days"=14};
        breakdowns — распределения с полосками:
        {"title", "rows": callable -> [(подпись, число)], "icon"="chart"}."""
        self._dash.update(
            greeting_attr=greeting_attr,
            stats=list(stats),
            online_count=online_count,
            actions=[dict(a) for a in actions],
            panels=[dict(p) for p in panels],
            charts=[dict(c) for c in charts],
            breakdowns=[dict(b) for b in breakdowns],
        )

    def init_app(self, app):
        if self.db is None:
            raise RuntimeError("eres-admin: передайте db в AdminSite(db=...)")
        from .views import bp
        from . import exporter, files  # noqa: F401  — регистрируют свои маршруты в bp

        app.extensions["eres_admin"] = self
        self.log_model = get_log_model(self.db)
        if BLUEPRINT not in app.blueprints:
            app.register_blueprint(bp, url_prefix=self.url_prefix)
        ensure_table(app, self.db, self.log_model)

    def get(self, key):
        ma = self._models.get(key)
        if ma is None:
            abort(404)
        return ma

    def model_admin_for(self, model):
        for ma in self._models.values():
            if ma.model is model:
                return ma
        return None

    def groups(self):
        out = {}
        for ma in self._models.values():
            out.setdefault(ma.group, []).append(ma)
        for link in self._links:
            out.setdefault(link.group, []).append(link)
        for section in self._files.values():
            out.setdefault(section.group, []).append(section)
        return out

    def nav_context(self):
        groups = self.groups()
        active_key = (request.view_args or {}).get("key") if request.blueprint == BLUEPRINT else None
        endpoint = request.endpoint
        palette = [{"label": "Обзор", "group": "", "url": url_for(f"{BLUEPRINT}.dashboard")}]
        for group, items in groups.items():
            for item in items:
                palette.append({"label": item.name, "group": group, "url": item.url})
        palette.append({"label": "Журнал изменений", "group": "Служебные", "url": url_for(f"{BLUEPRINT}.log_view")})
        from .stats import nav_counts, short_number
        return {
            "site": self,
            "nav_counts": nav_counts(self),
            "short_number": short_number,
            "groups": groups,
            "group_icon": icons.guess_for_group,
            "icon": icons.svg,
            "active_key": active_key,
            "active_endpoint": endpoint,
            "palette_items": palette,
        }


def _default_user_label(user):
    for attr in ("full_name", "email", "login"):
        try:
            value = getattr(user, attr, None)
        except Exception:                                  # noqa: BLE001
            value = None
        if value:
            return str(value)
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    return (f"{last} {first}".strip()) or f"#{getattr(user, 'id', '?')}"


def current_site():
    site = current_app.extensions.get("eres_admin")
    if site is None:
        abort(404)
    return site
