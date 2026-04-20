import os
from urllib.parse import urlparse

from flask import redirect, request, session

from backend.repositories.users import get_user_by_id


PROTECTED_PATHS = {"/dashboard", "/predikce", "/rebalance"}
PUBLIC_PREFIXES = ("/assets/", "/_dash-", "/favicon.ico", "/auth/")


def configure_session(server):
    is_production = os.getenv("APP_ENV", "").lower() == "production" or os.getenv("RENDER", "").lower() == "true"
    server.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    server.config["SESSION_COOKIE_HTTPONLY"] = True
    server.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    server.config["SESSION_COOKIE_SECURE"] = is_production
    server.config["PREFERRED_URL_SCHEME"] = "https" if is_production else "http"


def _canonical_redirect_base():
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        return None
    parsed = urlparse(redirect_uri)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_local_host(hostname):
    return hostname in {"localhost", "127.0.0.1"}


def is_authenticated() -> bool:
    return bool(session.get("user_id"))


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def clear_session():
    session.pop("user_id", None)
    session.pop("active_portfolio_id", None)
    session.pop("oauth_state", None)


def register_route_guards(server):
    @server.before_request
    def _protect_routes():
        path = request.path or "/"
        canonical_base = _canonical_redirect_base()

        if canonical_base:
            canonical = urlparse(canonical_base)
            if (
                canonical.hostname
                and request.host
                and _is_local_host(canonical.hostname)
                and _is_local_host(request.host.split(":")[0])
                and request.host != canonical.netloc
            ):
                query = request.query_string.decode("utf-8")
                target = f"{canonical_base}{path}"
                if query:
                    target = f"{target}?{query}"
                return redirect(target, code=302)

        if path.startswith(PUBLIC_PREFIXES):
            return None

        if path in PROTECTED_PATHS and request.method == "GET" and not is_authenticated():
            return redirect("/")

        return None
