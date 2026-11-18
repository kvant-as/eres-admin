"""Раздел «Файлы»: просмотр и правка папки на диске из админки.

Подключение: ``site.files("uploads", root="/path/to/uploads", name="Файлы")``.
``describe(folder, names) -> {name: {"label", "url", "in_use"}}`` — по желанию:
приложение сообщает, к каким записям привязаны файлы. Привязанный файл
нельзя переименовать (оборвётся ссылка), но можно заменить его содержимое.
"""
import json
import mimetypes
import os
import shutil
from datetime import datetime

from flask import (
    abort, flash, redirect, render_template, request, send_file, url_for,
)
from flask_login import current_user

from .site import BLUEPRINT, current_site
from .views import bp

TEXT_EXTENSIONS = {".txt", ".csv", ".json", ".md", ".log", ".xml", ".html", ".htm", ".css", ".js", ".ini", ".cfg", ".yml", ".yaml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
EDIT_LIMIT = 1024 * 1024
FORBIDDEN_CHARS = set('<>:"/\\|?*')

KIND_ICONS = {
    "folder": "folder", "image": "image", "pdf": "file", "doc": "file", "sheet": "chart",
    "archive": "layers", "text": "file", "other": "file",
}


class FileSection:
    is_link = True

    def __init__(self, key, root, name, group, icon, describe, max_upload_mb):
        self.key = key
        self.root = root
        self.name = name
        self.group = group
        self.icon = icon
        self.describe = describe
        self.max_upload_mb = max_upload_mb
        self.endpoint = f"{BLUEPRINT}.files_view"

    @property
    def url(self):
        return url_for(f"{BLUEPRINT}.files_view", key=self.key)

    def root_path(self):
        root = self.root() if callable(self.root) else self.root
        return os.path.realpath(root)


def _section(key):
    site = current_site()
    section = site._files.get(key)
    if section is None:
        abort(404)
    return site, section


def _clean_rel(rel):
    parts = [p for p in (rel or "").replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        abort(400)
    return "/".join(parts)


def _resolve(section, rel):
    root = section.root_path()
    rel = _clean_rel(rel)
    full = os.path.realpath(os.path.join(root, *rel.split("/"))) if rel else root
    if full != root and not full.startswith(root + os.sep):
        abort(400)
    return root, rel, full


def _valid_name(name):
    name = (name or "").strip().strip(".")
    if not name or name in (".", "..") or len(name) > 200:
        return None
    if any(ch in FORBIDDEN_CHARS or ord(ch) < 32 for ch in name):
        return None
    return name


def _unique(folder, name):
    stem, ext = os.path.splitext(name)
    candidate, i = name, 1
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = f"{stem} ({i}){ext}"
        i += 1
    return candidate


def _kind(name, is_dir):
    if is_dir:
        return "folder"
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in (".doc", ".docx", ".odt", ".rtf"):
        return "doc"
    if ext in (".xls", ".xlsx", ".ods"):
        return "sheet"
    if ext in (".zip", ".rar", ".7z", ".gz", ".tar"):
        return "archive"
    if ext in TEXT_EXTENSIONS:
        return "text"
    return "other"


def human_size(n):
    if n is None:
        return "—"
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return str(n)


def _log(site, section, action, label, changes=None):
    model = site.log_model
    if model is None:
        return
    try:
        site.db.session.add(model(
            site_code=site.code, created_at=site.now(),
            user_id=getattr(current_user, "id", None),
            user_label=site.user_label(current_user)[:255],
            model_key=f"files:{section.key}"[:64], model_name=section.name[:255],
            object_id=None, object_label=label[:255], action=action,
            changes=json.dumps(changes or [], ensure_ascii=False),
        ))
        site.db.session.commit()
    except Exception:                                      # noqa: BLE001
        site.db.session.rollback()


def _back(section, rel):
    return redirect(url_for(f"{BLUEPRINT}.files_view", key=section.key, path=rel or None))


def _parent(rel):
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


def _usage(section, rel, names):
    if not section.describe or not names:
        return {}
    try:
        return section.describe(rel, names) or {}
    except Exception:                                      # noqa: BLE001
        current_site().db.session.rollback()
        return {}


@bp.route("/_files/<key>/")
def files_view(key):
    site, section = _section(key)
    root, rel, full = _resolve(section, request.args.get("path"))
    if not os.path.isdir(full):
        if os.path.exists(full):
            return _back(section, _parent(rel))
        os.makedirs(full, exist_ok=True) if not rel else abort(404)

    entries = []
    with os.scandir(full) as it:
        for e in it:
            try:
                st = e.stat()
            except OSError:
                continue
            is_dir = e.is_dir()
            child_count = None
            if is_dir:
                try:
                    child_count = len(os.listdir(e.path))
                except OSError:
                    child_count = None
            entries.append({
                "name": e.name,
                "rel": f"{rel}/{e.name}" if rel else e.name,
                "is_dir": is_dir,
                "size": None if is_dir else st.st_size,
                "size_label": f"{child_count} шт." if is_dir and child_count is not None else human_size(None if is_dir else st.st_size),
                "mtime": datetime.fromtimestamp(st.st_mtime),
                "kind": _kind(e.name, is_dir),
                "editable": (not is_dir) and os.path.splitext(e.name)[1].lower() in TEXT_EXTENSIONS and st.st_size <= EDIT_LIMIT,
                "viewable": (not is_dir) and _kind(e.name, False) in ("image", "pdf", "text"),
            })
    usage = _usage(section, rel, [e["name"] for e in entries if not e["is_dir"]])
    for e in entries:
        info = usage.get(e["name"])
        e["usage"] = info
        e["in_use"] = bool(info and info.get("in_use", True))
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))

    crumbs = [{"name": section.name, "rel": ""}]
    acc = []
    for part in rel.split("/") if rel else []:
        acc.append(part)
        crumbs.append({"name": part, "rel": "/".join(acc)})

    files = [e for e in entries if not e["is_dir"]]
    try:
        disk = shutil.disk_usage(root)
        disk_free = human_size(disk.free)
    except OSError:
        disk_free = None

    return render_template(
        "eres_admin/files.html",
        section=section, rel=rel, entries=entries, crumbs=crumbs,
        total_files=len(files), total_size=human_size(sum(e["size"] or 0 for e in files)),
        disk_free=disk_free, has_usage=bool(section.describe),
        kind_icons=KIND_ICONS,
        **site.nav_context(),
    )


@bp.route("/_files/<key>/download")
def files_download(key):
    _, section = _section(key)
    _, rel, full = _resolve(section, request.args.get("path"))
    if not os.path.isfile(full):
        abort(404)
    inline = request.args.get("inline") == "1"
    name = request.args.get("as") or os.path.basename(full)
    mimetype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    if inline and _kind(full, False) == "text":
        mimetype = "text/plain; charset=utf-8"
    return send_file(full, mimetype=mimetype, as_attachment=not inline, download_name=name)


@bp.route("/_files/<key>/upload", methods=["POST"])
def files_upload(key):
    site, section = _section(key)
    _, rel, folder = _resolve(section, request.form.get("path"))
    if not os.path.isdir(folder):
        abort(400)
    saved = []
    limit = section.max_upload_mb * 1024 * 1024
    for f in request.files.getlist("files"):
        if not f or not f.filename:
            continue
        name = _valid_name(os.path.basename(f.filename.replace("\\", "/")))
        if not name:
            flash(f"Имя «{f.filename}» недопустимо — файл пропущен", "error")
            continue
        f.stream.seek(0, os.SEEK_END)
        size = f.stream.tell()
        f.stream.seek(0)
        if size > limit:
            flash(f"«{name}» больше {section.max_upload_mb} МБ — файл пропущен", "error")
            continue
        name = _unique(folder, name)
        f.save(os.path.join(folder, name))
        saved.append(name)
    if saved:
        _log(site, section, "create", f"{rel}/" if rel else "/",
             [{"field": "Загружено", "old": None, "new": ", ".join(saved)[:400]}])
        flash(f"Загружено файлов: {len(saved)}", "success")
    return _back(section, rel)


@bp.route("/_files/<key>/mkdir", methods=["POST"])
def files_mkdir(key):
    site, section = _section(key)
    _, rel, folder = _resolve(section, request.form.get("path"))
    name = _valid_name(request.form.get("name"))
    if not name:
        flash("Укажите имя папки без символов < > : \" / \\ | ? *", "error")
        return _back(section, rel)
    target = os.path.join(folder, name)
    if os.path.exists(target):
        flash(f"«{name}» уже есть в этой папке", "error")
        return _back(section, rel)
    os.makedirs(target)
    _log(site, section, "create", f"{rel}/{name}" if rel else name, [{"field": "Папка", "old": None, "new": name}])
    flash(f"Папка «{name}» создана", "success")
    return _back(section, rel)


@bp.route("/_files/<key>/rename", methods=["POST"])
def files_rename(key):
    site, section = _section(key)
    _, rel, full = _resolve(section, request.form.get("path"))
    parent_rel = _parent(rel)
    if not rel or not os.path.exists(full):
        abort(404)
    name = _valid_name(request.form.get("name"))
    if not name:
        flash("Недопустимое имя: уберите символы < > : \" / \\ | ? *", "error")
        return _back(section, parent_rel)
    old = os.path.basename(full)
    if name == old:
        return _back(section, parent_rel)
    if os.path.isfile(full) and _usage(section, parent_rel, [old]).get(old):
        flash("Файл привязан к записи в базе — переименование оборвёт ссылку. Замените содержимое вместо переименования.", "error")
        return _back(section, parent_rel)
    target = os.path.join(os.path.dirname(full), name)
    if os.path.exists(target):
        flash(f"«{name}» уже есть в этой папке", "error")
        return _back(section, parent_rel)
    os.rename(full, target)
    _log(site, section, "update", f"{parent_rel}/{name}" if parent_rel else name, [{"field": "Имя", "old": old, "new": name}])
    flash(f"«{old}» переименован в «{name}»", "success")
    return _back(section, parent_rel)


@bp.route("/_files/<key>/replace", methods=["POST"])
def files_replace(key):
    site, section = _section(key)
    _, rel, full = _resolve(section, request.form.get("path"))
    if not os.path.isfile(full):
        abort(404)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Выберите файл для замены", "error")
        return _back(section, _parent(rel))
    tmp = full + ".uploading"
    f.save(tmp)
    if os.path.getsize(tmp) > section.max_upload_mb * 1024 * 1024:
        os.remove(tmp)
        flash(f"Файл больше {section.max_upload_mb} МБ", "error")
        return _back(section, _parent(rel))
    os.replace(tmp, full)
    _log(site, section, "update", rel, [{"field": "Содержимое", "old": None, "new": f"заменено файлом {f.filename}"[:200]}])
    flash(f"Содержимое «{os.path.basename(full)}» заменено", "success")
    return _back(section, _parent(rel))


@bp.route("/_files/<key>/delete", methods=["POST"])
def files_delete(key):
    site, section = _section(key)
    paths = request.form.getlist("paths")
    back_rel = _clean_rel(request.form.get("back", ""))
    removed = []
    for p in paths:
        _, rel, full = _resolve(section, p)
        if not rel or not os.path.exists(full):
            continue
        try:
            if os.path.isdir(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
            removed.append(rel)
        except OSError as exc:
            flash(f"Не удалось удалить «{rel}»: {exc.strerror or exc}", "error")
    if removed:
        _log(site, section, "delete", removed[0] if len(removed) == 1 else f"{len(removed)} объектов",
             [{"field": "Удалено", "old": None, "new": ", ".join(removed)[:400]}])
        flash(f"Удалено: {len(removed)}", "success")
    return _back(section, back_rel)


@bp.route("/_files/<key>/edit", methods=["GET", "POST"])
def files_edit(key):
    site, section = _section(key)
    _, rel, full = _resolve(section, request.args.get("path") or request.form.get("path"))
    if not os.path.isfile(full) or os.path.splitext(full)[1].lower() not in TEXT_EXTENSIONS:
        abort(404)
    if os.path.getsize(full) > EDIT_LIMIT:
        flash("Файл больше 1 МБ — откройте его на компьютере", "error")
        return _back(section, _parent(rel))
    if request.method == "POST":
        content = request.form.get("content", "").replace("\r\n", "\n")
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        _log(site, section, "update", rel, [{"field": "Содержимое", "old": None, "new": "текст изменён"}])
        flash("Файл сохранён", "success")
        if request.form.get("_continue"):
            return redirect(url_for(f"{BLUEPRINT}.files_edit", key=key, path=rel))
        return _back(section, _parent(rel))
    raw = open(full, "rb").read()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = raw.decode("utf-8", errors="replace")
    return render_template(
        "eres_admin/file_edit.html",
        section=section, rel=rel, name=os.path.basename(full), parent=_parent(rel), content=content,
        **site.nav_context(),
    )
