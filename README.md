# eres-admin

Движок административной панели для Flask-приложений EnPlans и ErespondentN.
Приложение описывает свои модели в `website/admin.py`. Движок даёт:

- боковую панель с группами разделов и быстрым переходом (Ctrl+K);
- обзор: счётчики, панели «требует внимания», действия, последние изменения;
- списки: поиск, сортировка по колонкам, фильтры по логическим полям,
  выбор числа строк, выделение и массовое удаление, выгрузку в CSV;
- форму записи: поля по карточкам, переключатели, поиск связанной записи,
  предпросмотр картинки, Ctrl+S, предупреждение о несохранённых изменениях;
- журнал изменений: кто, когда и что поменял через админку;
- светлую и тёмную тему, мобильную вёрстку.

Оформление единое для всех приложений: фиолетовая палитра в духе Grav
(акцент `#7c5cf0`), скруглённые карточки, по умолчанию тёмная тема. Палитра
задаётся в `admin.css`, приложения её не переопределяют. Выбранная тема
хранится в localStorage под ключом `eres-admin-theme`.

## Установка

```
pip install -e D:\work\eres\eres-admin
```

Зависимости: Flask, Flask-Login, Flask-SQLAlchemy.

## Подключение

```python
from eres_admin import AdminSite, Field as F
from common_models import db, current_utc_time

site = AdminSite(
    brand="EnPlans",
    db=db,
    code="enplans",                  # у журнала каждой админки свои записи
    site_endpoint="views.begin_page",
    login_endpoint="auth.login",
    logout_endpoint="auth.logout",
    now=current_utc_time,
)

site.register(
    User, name="Пользователи", group="Основные",
    list_display=["id", "login", "email", "organization"],
    list_badges=["is_admin", ("has_approver_access", "Утверждающая организация")],
    search=["login", "email", "last_name"],
    scope_query=lambda q: q.filter(User.application_id == app_id),
    on_save=lambda obj, creating: ...,
    fields=[
        F("email", "Email", type="email"),
        F("org_role", "Роль", type="select", choices=[("executor", "Исполнитель")]),
        F("organization_id", "Организация", type="fk-search", target=Organization),
        F("password", "Пароль", type="password", skip_if_blank=True, transform=generate_password_hash),
        F("telephone", "Телефон", section="Контакты"),
    ],
)

site.link("Тестовые пользователи", "admin_test_users.index", group="Вспомогательные", icon="users")
site.dashboard(greeting_attr="first_name", stats=["user", "plan"], online_count=..., actions=[...], panels=[...])

def init_admin(app):
    site.init_app(app)               # /admin, доступ — current_user.is_admin
```

### AdminSite

| Параметр | Назначение |
|---|---|
| `brand` | название приложения в боковой панели |
| `db` | экземпляр Flask-SQLAlchemy (обязателен) |
| `code` | код приложения для журнала изменений |
| `url_prefix` | адрес панели, по умолчанию `/admin` |
| `site_endpoint`, `login_endpoint`, `logout_endpoint` | ссылки «Сайт», вход и выход |
| `theme_storage_key` | ключ localStorage для темы, по умолчанию `eres-admin-theme` |
| `now` | функция текущего времени для журнала |
| `is_admin` | проверка доступа `fn(user) -> bool` |
| `user_label` | подпись пользователя в журнале `fn(user) -> str` |

### register(model, ...)

`name`, `group`, `key`, `icon`, `list_display` (имя или пара «имя, подпись»),
`list_badges` (имя или пара «имя, подпись»), `list_format`, `search`,
`order_by`, `per_page`, `fields`, `readonly`, `can_create`, `can_edit`,
`can_delete`, `stat_label`, `stat_count`, `on_save(obj, creating)`,
`scope_query(query)` — ограничивает список, поиск, открытие по ссылке и счётчик.

У модели без полей (`readonly=True`) карточка записи показывает все колонки.

### Field

Типы: `str`, `text`, `email`, `int`, `float`, `bool`, `date`, `datetime`,
`select`, `fk`, `fk-search`, `password`, `file`.

Параметры: `label`, `required`, `choices`, `target`, `target_label`, `blank`,
`create_only`, `skip_if_blank`, `transform`, `help`, `rows`, `accept`,
`upload_to`, `default`, `readonly`, `display`, `section`, `placeholder`.

Поля с `choices` показываются в списке подписью варианта, а не кодом.

## Свои страницы в стиле панели

Шаблон наследует `eres_admin/base.html` и заполняет блоки `title`, `crumbs`,
`page_title`, `page_actions`, `content`. Маршрут передаёт `**site.nav_context()`.
Готовые классы: `ea-card`, `ea-card-head`, `ea-card-title`, `ea-list`,
`ea-list-row`, `ea-table`, `ea-fields`, `ea-field`, `ea-label`, `ea-input`,
`ea-hint`, `ea-btn` (`--primary`, `--ghost`, `--danger`), `ea-alert`,
`ea-badge`, `ea-empty`, `ea-thread`, `ea-msg`, `ea-composer`.
В шаблоне доступна функция `icon(name)`; из JS — `EA.toast(text, kind)` и
`EA.confirm(text)`. Форма с атрибутом `data-confirm` спрашивает подтверждение.

## Выгрузка базы

Кнопка «Скачать базу (CSV)» на обзоре (`/admin/_export/database.zip`) отдаёт
ZIP-архив: по CSV-файлу на каждую таблицу базы и `README.txt` с числом строк.
CSV — UTF-8 с BOM, разделитель «;». Колонки из `export_exclude_columns`
(по умолчанию `password`, `reset_password_token`) не выгружаются. Каждая
выгрузка записывается в журнал.

## Файлы на диске

```python
site.files("uploads", root=lambda: current_app.config["ATTACHMENTS_UPLOAD_FOLDER"],
           name="Файлы (uploads)", group="Служебные", describe=describe, max_upload_mb=100)
```

Раздел умеет: просмотр папок, загрузку (кнопкой и перетаскиванием), создание
папок, переименование, замену содержимого с сохранением имени, правку
текстовых файлов до 1 МБ, скачивание и удаление (в том числе нескольких сразу).
Выход за пределы `root` запрещён.

`describe(folder, names)` возвращает `{имя: {"label", "title", "url", "in_use"}}` —
исходное имя файла и запись, к которой он привязан. Привязанный файл нельзя
переименовать; перед его удалением показывается отдельное предупреждение.

## Журнал изменений

Таблица `eres_admin_log` создаётся при подключении, если её нет. Пароли в
журнал не пишутся: вместо значения стоит «скрыто».
