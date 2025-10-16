from dash import html, dcc, page_container
import dash
from app import app

navbar = html.Nav(
    [
        dcc.Link("Přehled", href="/", className="NavbarButton"),
        dcc.Link("Predikce", href="/predikce", className="NavbarButton"),
        dcc.Link("Rebalance", href="/contact", className="NavbarButton"),
    ],
    className="NavbarContainer"
)

app.layout = html.Div([
    dcc.Location(id="url"),
    dcc.Store(id="stored-data", storage_type="session"),
    navbar,
    html.Div(page_container, className="p-4")
])

if __name__ == "__main__":
    app.run(debug=True)