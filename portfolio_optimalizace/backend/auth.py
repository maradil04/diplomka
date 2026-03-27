import json
import os
import secrets
import urllib.parse
import urllib.request
from urllib.parse import urlparse

from flask import redirect, request, session

from backend.db import close_db
from backend.repositories.users import upsert_google_user
from backend.services.portfolio_service import resolve_active_portfolio
from backend.session import clear_session


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _env(name, default=None):
    return os.getenv(name, default)


def _get_redirect_uri():
    return _env("GOOGLE_REDIRECT_URI", "http://localhost:8050/auth/callback/google")


def _oauth_is_configured():
    return bool(_env("GOOGLE_CLIENT_ID") and _env("GOOGLE_CLIENT_SECRET"))


def _redirect_host():
    parsed = urlparse(_get_redirect_uri())
    return parsed.netloc


def _json_request(url, *, method="GET", data=None, headers=None):
    request_data = None
    request_headers = headers or {}
    if data is not None:
        request_data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=request_data, method=method, headers=request_headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _exchange_code_for_tokens(code):
    return _json_request(
        GOOGLE_TOKEN_URL,
        method="POST",
        data={
            "code": code,
            "client_id": _env("GOOGLE_CLIENT_ID"),
            "client_secret": _env("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": _get_redirect_uri(),
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def _verify_id_token(id_token):
    token_info = _json_request(f"{GOOGLE_TOKENINFO_URL}?id_token={urllib.parse.quote(id_token)}")
    if token_info.get("aud") != _env("GOOGLE_CLIENT_ID"):
        raise ValueError("Google token audience mismatch.")
    return token_info


def _load_google_profile(access_token):
    return _json_request(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )


def register_auth_routes(server):
    server.teardown_appcontext(close_db)

    @server.route("/auth/login/google")
    def auth_login_google():
        if not _oauth_is_configured():
            return (
                "Google OAuth is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI.",
                503,
            )

        state = secrets.token_urlsafe(24)
        session["oauth_state"] = state
        session["oauth_redirect_host"] = _redirect_host()
        query = urllib.parse.urlencode(
            {
                "client_id": _env("GOOGLE_CLIENT_ID"),
                "redirect_uri": _get_redirect_uri(),
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "offline",
                "prompt": "select_account",
            }
        )
        return redirect(f"{GOOGLE_AUTH_URL}?{query}")

    @server.route("/auth/callback/google")
    def auth_callback_google():
        state = request.args.get("state")
        code = request.args.get("code")
        error = request.args.get("error")
        expected_state = session.get("oauth_state")
        expected_host = session.get("oauth_redirect_host")
        actual_host = request.host

        if error:
            return redirect("/")
        if not code or not state or state != expected_state:
            details = [
                "Invalid OAuth callback state.",
                f"Expected host: {expected_host or 'unknown'}",
                f"Actual host: {actual_host or 'unknown'}",
                "Use the same host as GOOGLE_REDIRECT_URI when opening the app.",
            ]
            return ("\n".join(details), 400)

        tokens = _exchange_code_for_tokens(code)
        id_token = tokens.get("id_token")
        access_token = tokens.get("access_token")
        if not id_token or not access_token:
            return ("Google OAuth token exchange failed.", 400)

        token_info = _verify_id_token(id_token)
        profile = _load_google_profile(access_token)
        user = upsert_google_user(
            google_sub=token_info.get("sub"),
            email=profile.get("email") or token_info.get("email") or "",
            name=profile.get("name") or profile.get("email") or "Google User",
            avatar_url=profile.get("picture"),
        )

        session["user_id"] = user["id"]
        session.pop("oauth_state", None)
        session.pop("oauth_redirect_host", None)
        resolve_active_portfolio(user["id"])
        return redirect("/dashboard")

    @server.route("/auth/logout")
    def auth_logout():
        clear_session()
        return redirect("/")
