from dash import html

from utils.i18n import t


def build_auth_controls(auth_data, language="cs"):
    authenticated = bool(auth_data and auth_data.get("authenticated"))
    if not authenticated:
        return html.A(
            href="/auth/login/google",
            className="google-btn google-top-btn",
            children=[
                html.Img(
                    src="/assets/google-g.svg",
                    className="google-icon",
                ),
                html.Span(t(language, "auth.continue_google")),
            ],
        )

    name = auth_data.get("name") or auth_data.get("email") or t(language, "auth.user")
    return html.Div(
        className="auth-controls",
        children=[
            html.Span(t(language, "auth.signed_in_as", name=name), className="auth-user"),
            html.A(t(language, "auth.logout"), href="/auth/logout", className="auth-button logout-button"),
        ],
    )
