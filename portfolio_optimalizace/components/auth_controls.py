from dash import html


def build_auth_controls(auth_data):
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
                html.Span("Continue with Google"),
            ],
        )

    name = auth_data.get("name") or auth_data.get("email") or "User"
    return html.Div(
        className="auth-controls",
        children=[
            html.Span(f"Přihlášen jako {name}", className="auth-user"),
            html.A("Odhlásit se", href="/auth/logout", className="auth-button logout-button"),
        ],
    )
