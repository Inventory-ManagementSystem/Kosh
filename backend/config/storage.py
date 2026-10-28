from storages.backends.s3 import S3Storage
from whitenoise.storage import CompressedManifestStaticFilesStorage


class SafeManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except (ValueError, OSError):
            return name


class PrivateMediaStorage(S3Storage):
    location = "chat-attachments"
    default_acl = "private"
    querystring_auth = True
    querystring_expire = 3600
    file_overwrite = False
