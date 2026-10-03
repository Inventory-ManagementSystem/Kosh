from whitenoise.storage import CompressedManifestStaticFilesStorage


class SafeManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except (ValueError, OSError):
            return name
