import streamlit as st
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LinearRegression
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import pandas_ta
from streamlit_option_menu import option_menu

st.set_page_config(layout="wide")
st.title("Supr čupr webová aplikace - nezodpovídám za špatné predikce")

print('H')

ticker = option_menu(
    "Choose your stock",
    ["MSFT", "AAPL", "GOOGL"],
    icons=['microsoft', 'apple', 'google'],  # ikony pro tickery
    menu_icon="cast",  # ikona menu
    default_index=0,   # Výchozí výběr
    styles={
        "container": {"padding": "50px", "background-color": "#12131B", "width":"300px"},
        "icon": {"color": "white", "font-size": "11px"}, 
        "nav-link": {"font-size": "18px", "color": "white", "text-align": "left", "margin": "0px", "--hover-color": "#964D03"},
        "nav-link-selected": {"background-color": "#FD8207"},
    }
)

toggle = st.radio("Prediction", ("Show price", "Show statistics"))

data = yf.download(ticker, start="2024-01-09", end="2024-10-09")
data.head()

rsi = pandas_ta.rsi(data["Adj Close"], length=20)
garman_klass_volatility = ((np.log(data["High"])-np.log(data["Low"]))**2)/2-(2*np.log(2)-1)*(np.log(data["Adj Close"])-np.log(data["Open"]))
dollar_volume = (data["Adj Close"] * data["Volume"])/1e6






def single_graph(data, y, text, color_graph):
    fig = go.Figure()
    fig = px.line(data, y=y, title=f"{text} {ticker}")
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Open Price",
        title_font_size=24,
        template="plotly_dark",
        showlegend=False
    )
    fig.update_traces(line=dict(width=3, color=color_graph))
    
    st.plotly_chart(fig)

col1, col2 = st.columns(2)
if toggle == "Show price":
    with col1:
        statistic = option_menu(
        "Choose your stock",
        ["Boolinger bands", "Moving average"],
        default_index=0,
        styles={
            "container": {"padding": "50px", "background-color": "#12131B", "width":"300px"},
            "icon": {"color": "white", "font-size": "11px"}, 
            "nav-link": {"font-size": "18px", "color": "white", "text-align": "left", "margin": "0px", "--hover-color": "#964D03"},
            "nav-link-selected": {"background-color": "#FD8207"},
        }
        )
    if statistic == "Boolinger bands":
        with col2:
            period = st.slider("Choose the period", 1, 100)
            multiplier = st.slider("Choose standard deviation", 1, 50)
            middle_band = data['Close'].rolling(window=period).mean()
            std_dev = data['Close'].rolling(window=period).std()
            bollinger_bands = pd.DataFrame({
            "Middle Band": middle_band,
            "Upper Band": middle_band + (multiplier * std_dev),
            "Lower Band": middle_band - (multiplier * std_dev)
            }, index=data.index)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data.index, y=data["Open"], mode = "lines", name=f"Stock prices {ticker}", line=dict(color="#F803D4")))
        fig.add_trace(go.Scatter(x=data.index, y=bollinger_bands["Upper Band"],mode = "lines", name=f"Moving average for {ticker}", line=dict(color="orange")))
        fig.add_trace(go.Scatter(x=data.index, y=bollinger_bands["Lower Band"],mode = "lines", name=f"Moving average for {ticker}", line=dict(color="orange")))
        fig.update_layout(
            title=f"Customized Stock Prices for {ticker}",
            xaxis_title="Date",
            yaxis_title="Open Price",
            title_font_size=24,
            template="plotly_dark",
            showlegend=False
        )
        fig.update_traces(line=dict(width=3))
        
        st.plotly_chart(fig)
    elif statistic == "Moving average":
        with col2:
            period = st.slider("Choose the period", 1, 100)
            average = data["Open"].rolling(window = period).mean()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data.index, y=data["Open"], mode = "lines", name=f"Stock prices {ticker}", line=dict(color="#F803D4")))
        fig.add_trace(go.Scatter(x=data.index, y=average,mode = "lines", name=f"Moving average for {ticker}", line=dict(color="orange")))
        fig.update_layout(
            title=f"Customized Stock Prices for {ticker}",
            xaxis_title="Date",
            yaxis_title="Open Price",
            title_font_size=24,
            template="plotly_dark",
            showlegend=False
        )
        fig.update_traces(line=dict(width=3))
        
        st.plotly_chart(fig)
else:
    rsi_text = "RSI for"
    single_graph(data, rsi, rsi_text, "#157B07")
    
    garman_klass_volatility_text = "Garman klass volatility for"
    single_graph(data, garman_klass_volatility, garman_klass_volatility_text,"#F85002")
    
    dollar_volume_text = "Dollar volume for"
    single_graph(data, dollar_volume, dollar_volume_text, "#0213F8")

col1, col2 = st.columns(2)
with col1:
    st.header("Step 1: Select a Stock")
    st.text("This section will allow the user to choose a stock.")

with col2:
    st.header("Step 2: View Statistical Indicators")
    st.text("This section will display statistical indicators for the selected stock.")

st.header("Step 3: View Predictions")
st.text("This section will show predictions based on different models.")


import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

def single_graph(data, y, text, color_graph, ticker):
    # Inicializace grafu pomocí go.Figure
    fig = go.Figure()
    
    # Přidání čárového grafu s vlastní barvou
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data[y],
        mode="lines",
        name=text,
        line=dict(width=3, color=color_graph)
    ))
    
    # Vlastnosti grafu
    fig.update_layout(
        title=f"{text} {ticker}",
        xaxis_title="Date",
        yaxis_title=y,
        title_font_size=24,
        template="plotly_dark",
        dragmode="pan",  # Umožňuje pohyb po grafu tažením myší
        hovermode="x unified",  # Zobrazí hodnoty v jednom bodě pro všechny osy
        height=600  # Zvýšení výšky grafu pro větší přehlednost
    )
    
    # Zobrazit legendu a další možnosti
    fig.update_layout(showlegend=True)

    # Zobrazení grafu ve Streamlitu
    st.plotly_chart(fig, use_container_width=True)

# Testovací příklad
import pandas as pd
import numpy as np
import datetime

# Simulovaná data
np.random.seed(0)
dates = pd.date_range(start="2023-01-01", end="2023-12-31", freq="D")
data = pd.DataFrame({
    "Open": np.random.uniform(100, 200, len(dates))
}, index=dates)

ticker = "MSFT"
single_graph(data, y="Open", text="Stock Prices", color_graph="orange", ticker=ticker)


