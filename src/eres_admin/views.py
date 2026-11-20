import csv
import io
import json
import logging

from flask import (
    Blueprint, Response, abort, flash, jsonify, redirect, render_template,
    request, url_for,
)
from flask_login import current_user

from .audit import diff, snapshot
from .fields import MISSING
from .site import BLUEPRINT, PER_PAGE_CHOICES, current_site
from .stats import TONES, breakdown, daily_series, system_info
from .utils import format_value, initials, smart_label

log = logging.getLogger(__name__)

bp = Blueprint(
    BLUEPRINT, __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/eres-admin-static",
)


@bp.before_request
def _guard():
    site = current_site()
    if not current_user.is_authenticated or not site.is_admin(current_user):
        flash("Войдите под учётной записью администратора", "error")
        return redirect(url_for(site.login_endpoint))


@bp.app_template_global("ea_version")
def _ea_version():
    from . import __version__
    return __version__


@bp.app_template_global("ea_user_initials")
def _user_initials():
    site = current_site()
    return initials(site.user_label(current_user)) if current_user.is_authenticated else "?"


def _record_log(site, ma, obj, action, changes=None, object_id=None, object_label=None):
    model = site.log_model
    if model is None:
        return
    try:
        site.db.session.add(model(
            site_code=site.code,
            created_at=site.now(),
            user_id=getattr(current_user, "id", None),
            user_label=site.user_label(current_user)[:255],
            model_key=ma.key,
            model_name=ma.name[:255],
            object_id=str(object_id if object_id is not None else ma.pk(obj))[:64],
            object_label=(object_label or ma.title(obj))[:255],
            action=action,
            changes=json.dumps(changes or [], ensure_ascii=False),
        ))
        site.db.session.commit()
    except Exception as exc:                               # noqa: BLE001
        site.db.session.rollback()
        log.warning("eres-admin: не удалось записать журнал: %s", exc)


def _recent_log(site, limit=8, model_key=None, object_id=None):
    model = site.log_model
    if model is None:
        return []
    try:
        q = model.query.filter(model.site_code == site.code)
        if model_key:
            q = q.filter(model.model_key == model_key)
        if object_id is not None:
            q = q.filter(model.object_id == str(object_id))
        return q.order_by(model.created_at.desc(), model.id.desc()).limit(limit).all()
    except Exception:                                      # noqa: BLE001
        site.db.session.rollback()
        return []


@bp.route("/")
def dashboard():
    site = current_site()
    dash = site._dash
    cards = []
    for key in dash["stats"]:
        ma = site._models.get(key)
        if ma:
            try:
                value = ma.count()
            except Exception:                              # noqa: BLE001
                site.db.session.rollback()
                value = "—"
            cards.append({"label": ma.stat_label or ma.name, "value": value, "key": key, "icon": ma.icon, "url": ma.url})

    online = None
    fn = dash.get("online_count")
    if callable(fn):
        try:
            online = int(fn())
        except Exception:                                  # noqa: BLE001
            online = None

    greeting = None
    if dash["greeting_attr"]:
        greeting = getattr(current_user, dash["greeting_attr"], None)
    greeting = greeting or getattr(current_user, "first_name", None) or site.user_label(current_user)

    actions = []
    for a in dash.get("actions", []):
        try:
            url = a.get("url") or url_for(a["endpoint"])
        except Exception:                                  # noqa: BLE001
            continue
        actions.append({
            "label": a.get("label", "Действие"),
            "description": a.get("description"),
            "url": url,
            "method": (a.get("method") or "post").upper(),
            "confirm": a.get("confirm"),
            "type": a.get("type", "click"),
            "field": a.get("field", "file"),
            "accept": a.get("accept"),
        })

    panels = []
    for p in dash.get("panels", []):
        rows_src = p.get("rows")
        try:
            rows = rows_src() if callable(rows_src) else list(rows_src or [])
        except Exception:                                  # noqa: BLE001
            site.db.session.rollback()
            rows = []
        more_url = p.get("more_url")
        if not more_url and p.get("more_endpoint"):
            try:
                more_url = url_for(p["more_endpoint"])
            except Exception:                              # noqa: BLE001
                more_url = None
        panels.append({
            "title": p.get("title", ""),
            "rows": rows,
            "empty": p.get("empty", "Пусто"),
            "more_url": more_url,
            "more_label": p.get("more_label"),
        })

    for i, card in enumerate(cards):
        card["tone"] = TONES[i % len(TONES)]

    charts = []
    for spec in dash.get("charts", []):
        try:
            charts.append(daily_series(site, spec))
        except Exception as exc:                           # noqa: BLE001
            site.db.session.rollback()
            log.warning("eres-admin: график «%s» не построен: %s", spec.get("title"), exc)

    breakdowns = []
    for spec in dash.get("breakdowns", []):
        try:
            breakdowns.append(breakdown(spec))
        except Exception as exc:                           # noqa: BLE001
            site.db.session.rollback()
            log.warning("eres-admin: распределение «%s» не построено: %s", spec.get("title"), exc)

    system = system_info(site)
    if online is not None:
        system.append(("Сейчас онлайн", str(online)))

    return render_template(
        "eres_admin/dashboard.html",
        cards=cards, greeting=greeting, online=online, actions=actions, panels=panels,
        charts=charts, breakdowns=breakdowns, system=system,
        recent=_recent_log(site, limit=8),
        **site.nav_context(),
    )


@bp.route("/_fk-search")
def fk_search_view():
    site = current_site()
    ma = site._models.get(request.args.get("target", ""))
    if ma is None:
        return jsonify([])
    term = request.args.get("q", "").strip()
    rows = ma.search_query(ma.base_query(), term).limit(20).all()
    return jsonify([{"id": ma.pk(o), "label": ma.title(o)} for o in rows])


def _list_state(ma):
    term = request.args.get("q", "").strip()
    page = max(1, request.args.get("page", 1, type=int))
    per = request.args.get("per", ma.per_page, type=int)
    if per not in PER_PAGE_CHOICES and per != ma.per_page:
        per = ma.per_page
    sort = request.args.get("sort", "")
    if sort.lstrip("-") not in ma.sortable:
        sort = ""
    filters = {name: request.args.get(f"f_{name}", "") for name, _ in ma.filters}
    filters = {k: v for k, v in filters.items() if v in ("0", "1")}
    return term, page, per, sort, filters


def _list_query(ma, term, sort, filters):
    q = ma.base_query(sort or None)
    q = ma.search_query(q, term)
    return ma.filter_query(q, filters)


@bp.route("/<key>/")
def list_view(key):
    site = current_site()
    ma = site.get(key)
    term, page, per, sort, filters = _list_state(ma)
    q = _list_query(ma, term, sort, filters)
    total = q.count()
    pages = max(1, (total + per - 1) // per)
    page = min(page, pages)
    rows = q.offset((page - 1) * per).limit(per).all()

    base_args = {"q": term or None, "per": per if per != ma.per_page else None, "sort": sort or None}
    base_args.update({f"f_{k}": v for k, v in filters.items()})

    def link(**changes):
        args = {k: v for k, v in {**base_args, **changes}.items() if v not in (None, "")}
        return url_for(f"{BLUEPRINT}.list_view", key=ma.key, **args)

    def sort_link(name):
        if sort == name:
            return link(sort="-" + name, page=None)
        if sort == "-" + name:
            return link(sort=None, page=None)
        return link(sort=name, page=None)

    export_args = {k: v for k, v in base_args.items() if v not in (None, "") and k != "per"}
    return render_template(
        "eres_admin/list.html",
        ma=ma, rows=rows, term=term, page=page, pages=pages, total=total, per=per,
        sort=sort, filters=filters, per_choices=sorted(set(PER_PAGE_CHOICES) | {ma.per_page}),
        link=link, sort_link=sort_link, pager=_pager(page, pages),
        export_url=url_for(f"{BLUEPRINT}.export_view", key=ma.key, **export_args),
        **site.nav_context(),
    )


def _pager(page, pages):
    if pages <= 1:
        return []
    keep = {1, pages, page - 1, page, page + 1}
    out, prev = [], 0
    for p in sorted(x for x in keep if 1 <= x <= pages):
        if p - prev > 1:
            out.append(None)
        out.append(p)
        prev = p
    return out


@bp.route("/<key>/export.csv")
def export_view(key):
    site = current_site()
    ma = site.get(key)
    term, _, _, sort, filters = _list_state(ma)
    rows = _list_query(ma, term, sort, filters).limit(20000).all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([label for _, label in ma.list_display] + [ma.badge_label(n) for n in ma.list_badges])
    for row in rows:
        cells = [_plain(ma.cell(row, name)) for name, _ in ma.list_display]
        cells += ["Да" if ma.badge_on(row, n) else "Нет" for n in ma.list_badges]
        writer.writerow(cells)

    filename = f"{ma.key}-{site.now():%Y%m%d-%H%M}.csv"
    return Response(
        "﻿" + buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _plain(value):
    text = str(value)
    return "" if text == "—" else text


@bp.route("/<key>/new", methods=["GET", "POST"])
def create_view(key):
    site = current_site()
    ma = site.get(key)
    if not ma.can_create:
        abort(403)
    return _edit(site, ma, obj=ma.model(), creating=True)


@bp.route("/<key>/<int:pk>/edit", methods=["GET", "POST"])
def edit_view(key, pk):
    site = current_site()
    ma = site.get(key)
    obj = ma.get_obj(pk) or abort(404)
    if request.method == "POST" and not ma.can_edit:
        abort(403)
    return _edit(site, ma, obj=obj, creating=False)


def _delete_one(site, ma, obj):
    label, pk = ma.title(obj), ma.pk(obj)
    site.db.session.delete(obj)
    site.db.session.commit()
    _record_log(site, ma, None, "delete", object_id=pk, object_label=label)
    return label


@bp.route("/<key>/<int:pk>/delete", methods=["POST"])
def delete_view(key, pk):
    site = current_site()
    ma = site.get(key)
    if not ma.can_delete:
        abort(403)
    obj = ma.get_obj(pk) or abort(404)
    try:
        label = _delete_one(site, ma, obj)
        flash(f"«{label}» удалено", "success")
    except Exception as exc:                               # noqa: BLE001
        site.db.session.rollback()
        flash(f"Не удалось удалить: {exc}", "error")
        return redirect(url_for(f"{BLUEPRINT}.edit_view", key=key, pk=pk))
    return redirect(request.form.get("next") or url_for(f"{BLUEPRINT}.list_view", key=key))


@bp.route("/<key>/<int:pk>/action/<name>", methods=["POST"])
def object_action_view(key, pk, name):
    """Действие над записью из карточки (ModelAdmin.object_actions),
    например «Обновить из ЕГР» у организации."""
    site = current_site()
    ma = site.get(key)
    action = ma.object_action(name) or abort(404)
    if not ma.can_edit:
        abort(403)
    obj = ma.get_obj(pk) or abort(404)
    label = action.get("label", name)
    back = url_for(f"{BLUEPRINT}.edit_view", key=key, pk=pk, next=request.form.get("next") or None)
    try:
        result = action["handler"](obj) or []
        site.db.session.commit()
    except Exception as exc:                               # noqa: BLE001
        site.db.session.rollback()
        flash(f"{label}: {exc}", "error")
        return redirect(back)

    changes = []
    for item in result:
        if isinstance(item, dict):
            changes.append({"field": item.get("field"), "old": item.get("old"), "new": item.get("new")})
        else:
            field, old, new = item
            changes.append({"field": field,
                            "old": None if old in (None, "") else format_value(old, limit=200),
                            "new": format_value(new, limit=200)})
    if changes:
        _record_log(site, ma, obj, "update", changes)
        flash(f"{label}: обновлено — " + ", ".join(c["field"] for c in changes), "success")
    else:
        flash(f"{label}: изменений нет, данные актуальны", "success")
    return redirect(back)


@bp.route("/<key>/bulk-delete", methods=["POST"])
def bulk_delete_view(key):
    site = current_site()
    ma = site.get(key)
    if not ma.can_delete:
        abort(403)
    ids = [int(x) for x in request.form.getlist("ids") if str(x).isdigit()]
    done, failed = 0, []
    for pk in ids:
        obj = ma.get_obj(pk)
        if obj is None:
            continue
        label = ma.title(obj)
        try:
            _delete_one(site, ma, obj)
            done += 1
        except Exception:                                  # noqa: BLE001
            site.db.session.rollback()
            failed.append(label)
    if done:
        flash(f"Удалено записей: {done}", "success")
    if failed:
        shown = ", ".join(failed[:5]) + ("…" if len(failed) > 5 else "")
        flash(f"Не удалось удалить (есть связанные данные): {shown}", "error")
    return redirect(request.form.get("next") or url_for(f"{BLUEPRINT}.list_view", key=key))


def _edit(site, ma, obj, creating):
    fields = ma.form_fields(creating)
    errors = {}
    before = {} if creating else snapshot(obj, fields)

    if request.method == "POST":
        for f in fields:
            value = f.extract(request.form, request.files)
            if value is MISSING:
                continue
            if f.required and value in (None, ""):
                errors[f.name] = "Заполните поле"
                continue
            if f.transform and value not in (None, ""):
                value = f.transform(value)
            setattr(obj, f.name, value)

        if not errors:
            try:
                if ma.on_save:
                    ma.on_save(obj, creating)
                if creating:
                    site.db.session.add(obj)
                changes = diff(fields, before, obj, creating)
                site.db.session.commit()
            except Exception as exc:                       # noqa: BLE001
                site.db.session.rollback()
                errors["__all__"] = str(exc)
            else:
                if creating or changes:
                    _record_log(site, ma, obj, "create" if creating else "update", changes)
                flash("Запись создана" if creating else ("Изменения сохранены" if changes else "Изменений нет"), "success")
                if request.form.get("_continue"):
                    return redirect(url_for(f"{BLUEPRINT}.edit_view", key=ma.key, pk=ma.pk(obj)))
                return redirect(request.form.get("next") or url_for(f"{BLUEPRINT}.list_view", key=ma.key))

    def value_for(f):
        v = getattr(obj, f.name, None)
        if v is None and creating and f.default is not None:
            return f.default
        return v

    def fk_target_key(f):
        target = site.model_admin_for(f.target) if f.target is not None else None
        return target.key if target else None

    def fk_current_label(f, value):
        if f.target is None or value in (None, ""):
            return ""
        related = site.db.session.get(f.target, value)
        return smart_label(related, f.target_label) if related else ""

    field_views = []
    for f in fields:
        value = f.display(obj) if (f.readonly and f.display) else value_for(f)
        if f.readonly and not f.display:
            value = format_value(value, limit=None)
        field_views.append({
            "spec": f,
            "value": value,
            "options": f.options(),
            "error": errors.get(f.name),
            "target_key": fk_target_key(f) if f.type == "fk-search" else None,
            "current_label": fk_current_label(f, value) if f.type == "fk-search" else None,
        })

    return render_template(
        "eres_admin/form.html",
        ma=ma, obj=obj, creating=creating,
        sections=ma.sections(field_views),
        details=ma.detail_rows(obj) if not fields and not creating else [],
        form_error=errors.get("__all__"), has_errors=bool(errors),
        history=[] if creating else _recent_log(site, limit=12, model_key=ma.key, object_id=ma.pk(obj)),
        back_url=request.args.get("next") or url_for(f"{BLUEPRINT}.list_view", key=ma.key),
        **site.nav_context(),
    )


@bp.route("/_log/")
def log_view():
    site = current_site()
    model = site.log_model
    model_key = request.args.get("model", "")
    action = request.args.get("action", "")
    page = max(1, request.args.get("page", 1, type=int))
    per = 50
    q = model.query.filter(model.site_code == site.code)
    if model_key:
        q = q.filter(model.model_key == model_key)
    if action in ("create", "update", "delete", "export"):
        q = q.filter(model.action == action)
    total = q.count()
    pages = max(1, (total + per - 1) // per)
    page = min(page, pages)
    entries = q.order_by(model.created_at.desc(), model.id.desc()).offset((page - 1) * per).limit(per).all()

    def link(**changes):
        args = {"model": model_key or None, "action": action or None, **changes}
        return url_for(f"{BLUEPRINT}.log_view", **{k: v for k, v in args.items() if v})

    return render_template(
        "eres_admin/log.html",
        entries=entries, total=total, page=page, pages=pages, pager=_pager(page, pages),
        model_key=model_key, action=action, link=link,
        models=sorted(site._models.values(), key=lambda m: m.name),
        **site.nav_context(),
    )
