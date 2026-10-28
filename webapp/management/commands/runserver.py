"""Run Django locally after validating secrets and preserving/initializing legacy tables."""
from django.conf import settings
from django.core.management.base import CommandError
from django.contrib.staticfiles.management.commands.runserver import Command as StaticRunserver

def local_addrport(requested):
    """Allow an optional port while pinning the development server to loopback."""
    if requested in (None, ""):
        return "127.0.0.1:8000"
    if str(requested).isdigit():
        port = str(requested)
    else:
        host, separator, port = str(requested).rpartition(":")
        if not separator or host.lower() not in ("127.0.0.1", "localhost"):
            raise CommandError("The local development server must bind to 127.0.0.1 or localhost")
    try:
        number = int(port)
    except ValueError as error:
        raise CommandError("Port must be a number between 1 and 65535") from error
    if not 1 <= number <= 65535:
        raise CommandError("Port must be a number between 1 and 65535")
    return f"127.0.0.1:{number}"

class Command(StaticRunserver):
    def inner_run(self, *args, **options):
        from backend.config import settings as app_settings
        from backend.db import init_db
        try:
            app_settings.validate_secrets()
            init_db()  # create missing tables and apply only the existing additive SQLite fixes
        except Exception as error:
            raise CommandError(f"Workforce360 startup validation failed: {error}") from error
        options["addrport"] = local_addrport(options.get("addrport"))
        return super().inner_run(*args, **options)
