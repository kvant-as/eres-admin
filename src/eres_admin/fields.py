import os

from flask import current_app

from .utils import parse_dt, safe_upload_name, smart_label

MISSING = object()

TEXT_INPUT_TYPES = {
    "str": "text", "email": "email", "password": "password",
    "int": "number", "float": "number",
}


class Field:
    """Поле формы создания и редактирования записи.

    type: str | text | email | int | float | bool | date | datetime |
          select | fk | fk-search | password | file

    section — заголовок карточки, в которую попадает поле; поля без
    section идут в первую карточку «Основное».
    """

    def __init__(self, name, label=None, type="str", required=False,
                 choices=None, target=None, target_label=None, blank=True,
                 create_only=False, skip_if_blank=False, transform=None,
                 help=None, rows=5, accept=None, upload_to=None, default=None,
                 readonly=False, display=None, section=None, placeholder=None):
        self.name = name
        self.label = label or name.replace("_", " ").capitalize()
        self.type = type
        self.required = required
        self.choices = choices or []
        self.target = target
        self.target_label = target_label
        self.blank = blank
        self.create_only = create_only
        self.skip_if_blank = skip_if_blank
        self.transform = transform
        self.help = help
        self.rows = rows
        self.accept = accept
        self.upload_to = upload_to
        self.default = default
        self.readonly = readonly
        self.display = display
        self.section = section
        self.placeholder = placeholder

    @property
    def is_secret(self):
        return self.type == "password"

    @property
    def input_type(self):
        return TEXT_INPUT_TYPES.get(self.type, "text")

    @property
    def is_image(self):
        return self.type == "file" and (self.accept or "").startswith("image")

    def upload_url(self, value):
        """Публичный адрес загруженного файла, если он лежит в static."""
        if not value or not self.upload_to:
            return None
        folder = self.upload_to.replace("\\", "/").strip("/")
        if not folder.startswith("static/"):
            return None
        return "/" + folder + "/" + value

    def extract(self, form, files):
        if self.readonly:
            return MISSING
        if self.type == "bool":
            return self.name in form
        if self.type == "file":
            file = files.get(self.name)
            if not file or not file.filename:
                return MISSING
            dest_dir = os.path.join(current_app.root_path, self.upload_to or "static/uploads")
            os.makedirs(dest_dir, exist_ok=True)
            fname = safe_upload_name(file.filename)
            root, ext = os.path.splitext(fname)
            i = 1
            while os.path.exists(os.path.join(dest_dir, fname)):
                fname = f"{root}-{i}{ext}"
                i += 1
            file.save(os.path.join(dest_dir, fname))
            return fname

        raw = (form.get(self.name) or "").strip()
        if raw == "":
            if self.skip_if_blank:
                return MISSING
            return None if self.blank or not self.required else ""

        if self.type in ("int", "fk", "fk-search"):
            try:
                return int(raw)
            except ValueError:
                return None
        if self.type == "float":
            try:
                return float(raw.replace(",", ".").replace(" ", ""))
            except ValueError:
                return None
        if self.type == "date":
            return parse_dt(raw, "%Y-%m-%d")
        if self.type == "datetime":
            return parse_dt(raw, "%Y-%m-%dT%H:%M")
        return raw

    def options(self):
        if self.type == "select":
            return list(self.choices)
        if self.type == "fk" and self.target is not None:
            pk = self.target.__mapper__.primary_key[0].name
            rows = self.target.query.all()
            rows.sort(key=lambda o: smart_label(o, self.target_label).lower())
            return [(getattr(o, pk), smart_label(o, self.target_label)) for o in rows]
        return []
