"""Speks internationalisation (i18n) module.

Simple dictionary-based translation system.  The active locale is set once
at startup (from ``speks.toml`` or CLI) and the ``t()`` helper returns the
translated string for the current locale.

Usage::

    from speks.i18n import t, set_locale

    set_locale("fr")
    print(t("cli.building_site"))  # "Construction du site pour"
"""

from __future__ import annotations

import contextvars
from typing import Any

from speks.i18n.en import STRINGS as EN_STRINGS
from speks.i18n.fr import STRINGS as FR_STRINGS

_CATALOGS: dict[str, dict[str, str]] = {
    "en": EN_STRINGS,
    "fr": FR_STRINGS,
}

DEFAULT_LOCALE = "fr"

_locale: contextvars.ContextVar[str] = contextvars.ContextVar(
    "speks_locale", default=DEFAULT_LOCALE,
)


def set_locale(locale: str) -> None:
    """Set the active locale for the current context."""
    if locale not in _CATALOGS:
        locale = DEFAULT_LOCALE
    _locale.set(locale)


def get_locale() -> str:
    """Return the active locale."""
    return _locale.get()


def t(key: str, **kwargs: Any) -> str:
    """Return the translated string for *key* in the current locale.

    Supports ``str.format`` placeholders — pass values as keyword arguments.
    Falls back to English, then to the raw key.
    """
    locale = _locale.get()
    catalog = _CATALOGS.get(locale, EN_STRINGS)
    template = catalog.get(key) or EN_STRINGS.get(key) or key
    if kwargs:
        return template.format(**kwargs)
    return template
