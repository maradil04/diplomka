from dash import html, register_page


register_page(__name__, path="/")


layout = html.Div(
    className="landing-page",
    children=[
        html.Div(
            className="landing-words",
            children=[
                html.H1("ANALYSE", className="landing-word landing-word-primary"),
                html.H1("REBALANCE", className="landing-word landing-word-outline landing-word-second"),
                html.H1("PREDICT", className="landing-word landing-word-outline landing-word-third"),
            ],
        ),
    ],
)
