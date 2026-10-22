# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent, opt-in mission bridge. Importing this package never registers Blender UI."""

__version__ = "0.25.0"


def register():
    """Explicitly enable the optional sidebar; no server is started on registration."""
    from . import connection_ui, reference_ui, versions_ui
    connection_ui.register()
    reference_ui.register()
    versions_ui.register()


def unregister():
    from . import connection_ui, reference_ui, versions_ui
    versions_ui.unregister()
    reference_ui.unregister()
    connection_ui.unregister()
