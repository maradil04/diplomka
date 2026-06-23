import os
from pathlib import Path

from dash import Dash
from dotenv import load_dotenv

from backend.auth import register_auth_routes
from backend.db import init_db
from backend.session import configure_session, register_route_guards


PROJECT_ROOT = Path(__file__).resolve().parent
if not os.getenv("RENDER"):
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / "backend" / ".env")

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    prevent_initial_callbacks="initial_duplicate",
    meta_tags=[
        {
            "name": "viewport",
            "content": "width=device-width, initial-scale=1, viewport-fit=cover",
        }
    ],
)
server = app.server

configure_session(server)
init_db()
register_auth_routes(server)
register_route_guards(server)

if __name__ == "__main__":
    import index  # noqa: F401,E402
    app.run(debug=True)
