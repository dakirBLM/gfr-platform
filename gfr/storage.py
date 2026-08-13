"""
Media storage backends for GFR.

SupabaseStorage stores media files in Supabase Storage through its
S3-compatible gateway and exposes public object URLs (requires a public
bucket, e.g. "gfr-media").
"""

from urllib.parse import quote, urlparse

from storages.backends.s3boto3 import S3Boto3Storage


class SupabaseStorage(S3Boto3Storage):
    """S3-compatible storage backend for Supabase Storage (public buckets)."""

    def url(self, name, parameters=None, expire=None):
        parsed = urlparse(self.endpoint_url)
        host = parsed.netloc
        if host.endswith('.storage.supabase.co'):
            host = host[: -len('.storage.supabase.co')] + '.supabase.co'
        return (
            f'{parsed.scheme}://{host}'
            f'/storage/v1/object/public/{self.bucket_name}/{quote(name)}'
        )
