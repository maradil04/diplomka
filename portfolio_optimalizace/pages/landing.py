from dash import html, register_page


register_page(__name__, path="/")


def _vertical_word(word, class_name):
    return html.Div(
        className=f"landing-word-column {class_name}",
        children=[html.Span(letter, className="landing-word-letter") for letter in word],
    )


layout = html.Div(
    className="landing-page",
    children=[
        html.Div(
            className="landing-words",
            children=[
                _vertical_word("ANALYSE", "landing-word-primary"),
                _vertical_word("REBALANCE", "landing-word-outline landing-word-second"),
                _vertical_word("PREDICT", "landing-word-outline landing-word-third"),
            ],
        ),
    ],
)
