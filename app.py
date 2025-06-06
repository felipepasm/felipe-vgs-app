import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="VGS Buy Signal Tracker", layout="wide")
st.title("VGS Buy Signal Tracker")

# Download historical VGS data
ticker = "VGS.AX"
end_date = datetime.today()
start_date = end_date - timedelta(days=365)

st.sidebar.header("Parameters")
sma_window = st.sidebar.slider("SMA Window (days)", 5, 60, 20)
threshold = st.sidebar.slider("% Below SMA to Trigger", -10.0, -1.0, -3.0)
investment_amount = st.sidebar.number_input("Investment per Trigger (AUD)", 500, 10000, 1500)

@st.cache_data
def load_data():
    return yf.download(ticker, start=start_date, end=end_date)

data = load_data()

# Flatten multi-indexed columns if needed
if isinstance(data.columns, pd.MultiIndex):
    data.columns = data.columns.get_level_values(0)

# Fallback to demo data if needed
if data.empty or 'Close' not in data.columns:
    st.warning("Falling back to demo data.")
    dates = pd.date_range(start=start_date, end=end_date)
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(len(dates)))
    data = pd.DataFrame({'Close': prices}, index=dates)
st.write("Loaded columns:", data.columns.tolist())

# Ensure necessary columns exist
if data.empty or 'Close' not in data.columns:
    st.error("No valid price data available for VGS. Please try again later.")
    st.stop()

# Calculate SMA and % deviation
sma_column = 'SMA'
data[sma_column] = data['Close'].rolling(window=sma_window).mean()

# Drop rows with missing Close or SMA values
required_columns = ['Close', sma_column]
try:
    if all(col in data.columns for col in required_columns):
        data = data.dropna(subset=required_columns).copy()
    else:
        raise KeyError("Required columns not found.")
except KeyError:
    st.error("One or more required columns were not found in the dataset. This may be a temporary issue with the data source.")
    st.stop()


# Calculate % Below SMA
data['% Below SMA'] = ((data['Close'] - data[sma_column]) / data[sma_column]) * 100

# Generate 3-week downtrend
weekly = data['Close'].resample('W-FRI').last()
weekly_returns = weekly.pct_change() * 100
weekly_flags = []
for i in range(len(weekly_returns)):
    if i >= 2 and weekly_returns[i] < 0 and weekly_returns[i-1] < 0 and weekly_returns[i-2] < 0:
        weekly_flags.append(1)
    else:
        weekly_flags.append(0)
weekly_flags = pd.Series(weekly_flags, index=weekly_returns.index)

# Map weekly flags to daily
data['3-Week Downtrend'] = 0
for date in weekly_flags[weekly_flags == 1].index:
    if date in data.index:
        data.loc[date, '3-Week Downtrend'] = 1

# Combined Trigger
data['BUY'] = ((data['% Below SMA'] < threshold) | (data['3-Week Downtrend'] == 1)).astype(int)
data['BUY Flag'] = data['BUY'].apply(lambda x: 'BUY' if x == 1 else '')

# Simulate investment
data['Units Bought'] = np.where(data['BUY'] == 1, investment_amount / data['Close'], 0)
data['Investment'] = np.where(data['BUY'] == 1, investment_amount, 0)
total_invested = data['Investment'].sum()
total_units = data['Units Bought'].sum()
current_price = data['Close'].iloc[-1]
current_value = total_units * current_price
gain = current_value - total_invested

# Display results
st.metric("Total Invested (AUD)", f"${total_invested:,.2f}")
st.metric("Current Value (AUD)", f"${current_value:,.2f}")
st.metric("Total Gain (AUD)", f"${gain:,.2f}", delta=f"{(gain/total_invested)*100:.2f}%")

st.dataframe(data[['Close', sma_column, '% Below SMA', '3-Week Downtrend', 'BUY Flag']].tail(90))

import plotly.graph_objects as go

# Plot with BUY markers and adjustable Y-axis
fig = go.Figure()
fig.add_trace(go.Scatter(x=data.index, y=data['Close'], mode='lines', name='Close'))
fig.add_trace(go.Scatter(x=data.index, y=data[sma_column], mode='lines', name=f'{sma_window}-day SMA'))

# Add BUY markers
buy_dates = data[data['BUY'] == 1].index
buy_prices = data.loc[buy_dates, 'Close']
fig.add_trace(go.Scatter(x=buy_dates, y=buy_prices, mode='markers', name='BUY Signal', marker=dict(color='green', size=10, symbol='triangle-up')))

# Let user set Y-axis bounds
st.sidebar.subheader("Chart Y-Axis Range")
y_min = st.sidebar.number_input("Min Y", value=float(data['Close'].min()) * 0.95)
y_max = st.sidebar.number_input("Max Y", value=float(data['Close'].max()) * 1.05)
fig.update_layout(title="VGS Close Price & SMA with BUY Signals",
                  yaxis=dict(title='Price (AUD)', range=[y_min, y_max]),
                  xaxis_title='Date')
st.plotly_chart(fig, use_container_width=True)
