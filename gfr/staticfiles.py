"""
Static files storage for production.

Hashed-manifest storage raises when an asset is missing from the manifest,
which turns any un-collected file into a 500 for the whole page. Serving the
plain path instead keeps the site usable when collectstatic has not run.
"""

import logging

from django.conf import settings
from whitenoise.storage import CompressedManifestStaticFilesStorage

logger = logging.getLogger(__name__)


class ResilientManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    manifest_strict = False

    def url(self, name, force=False):
        try:
            return super().url(name, force)
        except ValueError:
            logger.warning('Static asset "%s" is missing; serving the unhashed path.', name)
            return f'{settings.STATIC_URL}{name}'
