# Default to local settings when importing `gfr.settings`.
# Prefer explicit modules: gfr.settings.local / gfr.settings.production.
from .local import *  # noqa: F401,F403
