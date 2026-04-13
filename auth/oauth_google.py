"""Google OAuth2 (OpenID Connect) client registration for Authlib."""

import os

from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
_google_registered = False


def google_oauth_configured() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID", "").strip())


def ensure_google_client() -> bool:
    """Register the Google provider once. Returns False if env is not set."""
    global _google_registered
    if not google_oauth_configured():
        return False
    if _google_registered:
        return True
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    _google_registered = True
    return True
