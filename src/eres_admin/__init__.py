"""eres-admin — движок административной панели для Flask-приложений.

Приложение описывает модели декларативно (``AdminSite.register``), движок
даёт списки с поиском, сортировкой и фильтрами, формы, журнал изменений
и обзорную страницу.
"""

from .fields import Field
from .site import AdminSite

__all__ = ["AdminSite", "Field"]
__version__ = "0.1.0"
