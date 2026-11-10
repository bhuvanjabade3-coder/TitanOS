from __future__ import annotations

from . import apps, browser, desktop, dev, files, memory, misc, security_centre, system_settings, terminal


def register_all(reg) -> None:
    for mod in (files, terminal, apps, desktop, browser, memory, misc, security_centre, system_settings, dev):
        mod.register(reg)
    from .. import voice
    voice.register(reg)
