from pathlib import Path

from dash import Dash
from dotenv import load_dotenv

from backend.auth import register_auth_routes
from backend.db import init_db
from backend.session import configure_session, register_route_guards


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

app = Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    prevent_initial_callbacks="initial_duplicate",
)
server = app.server

configure_session(server)
init_db()
register_auth_routes(server)
register_route_guards(server)
