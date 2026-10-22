# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent, opt-in mission bridge. Importing this package never registers Blender UI."""

__version__ = "0.29.0"


def register():
    """Explicitly enable the optional sidebar; no server is started on registration."""
    from . import connection_ui, reference_ui, versions_ui, layers_ui, camera_ui, context_ui, modular_ui, wardrobe_ui
    connection_ui.register()
    reference_ui.register()
    versions_ui.register()
    layers_ui.register()
    camera_ui.register()
    context_ui.register()
    modular_ui.register()
    wardrobe_ui.register()


def unregister():
    from . import connection_ui, reference_ui, versions_ui, layers_ui, camera_ui, context_ui, modular_ui, wardrobe_ui
    wardrobe_ui.unregister()
    modular_ui.unregister()
    context_ui.unregister()
    camera_ui.unregister()
    layers_ui.unregister()
    versions_ui.unregister()
    reference_ui.unregister()
    connection_ui.unregister()
