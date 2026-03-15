import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import matplotlib.pyplot as plt

# --- Fetch Nifty Spot from NSE India API ---
def fetch_nifty_spot():
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    data = session.get(url, headers=headers).json()
    spot = data['records']['underlyingValue']
    return spot

# --- Safe Yahoo Finance Download ---
def safe_download(symbol, period="1d", interval="1d"):
    try:
        df = yf.download(symbol, period=period, interval=interval)
        if not df.empty:
            return df['Close'].iloc[-1].item()
        else:
            return None
    except Exception:
        return None

# --- Fetch Indices ---
def fetch_indices():
    spot   = fetch_nifty_spot()
    dow    = safe_download("^DJI")
    nasdaq = safe_download("^IXIC")
    nikkei = safe_download("^N225")
    return spot, dow, nasdaq, nikkei

# --- Technical Indicators ---
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_signal(df):
    df['EMA20'] = df['Close'].ewm(span=20).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['RSI'] = compute_rsi(df['Close'])
    ema20 = df['EMA20'].iloc[-1].item()
    ema50 = df['EMA50'].iloc[-1].item()
    rsi   = df['RSI'].iloc[-1].item()
    if ema20 > ema50 and rsi > 55:
        return "CALL"
    elif ema20 < ema50 and rsi < 45:
        return "PUT"
    else:
        return "NO TRADE"

# --- Confidence Scoring ---
def calculate_confidence(signal, spot, gift, dow, nasdaq, nikkei):
    score = 0
    if signal == "CALL":
        if gift and gift > spot: score += 25
        if dow and nasdaq and dow > 0 and nasdaq > 0: score += 15
        if nikkei and nikkei > 0: score += 10
        score += 40
    elif signal == "PUT":
        if gift and gift < spot: score += 25
        if dow and nasdaq and dow < 0 and nasdaq < 0: score += 15
        if nikkei and nikkei < 0: score += 10
        score += 40
    return score

# --- Option Chain ---
def fetch_option_chain(symbol="NIFTY"):
    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    data = session.get(url, headers=headers).json()
    return data

# --- Strike Selection ---
def select_strike(records, signal, spot):
    atm_strike = round(spot / 50) * 50
    candidate_strikes = [atm_strike-100, atm_strike-50, atm_strike, atm_strike+50, atm_strike+100, atm_strike+150]
    for strike in candidate_strikes:
        atm_data = next((item for item in records if item['strikePrice'] == strike), None)
        if atm_data:
            premium = atm_data['CE']['lastPrice'] if signal == "CALL" else atm_data['PE']['lastPrice']
            if 80 <= premium <= 200:
                return strike, premium
    return None, None

# --- Payoff Diagram ---
def payoff_diagram(signal, strike, premium, spot, lot_size=50):
    prices = np.arange(spot-300, spot+300, 50)
    payoff = []
    for p in prices:
        if signal == "CALL":
            payoff.append((max(p - strike, 0) - premium) * lot_size)
        else:
            payoff.append((max(strike - p, 0) - premium) * lot_size)
    fig, ax = plt.subplots()
    ax.plot(prices, payoff, label=f"Buy {signal}")
    ax.axhline(0, color="black", linestyle="--")
    ax.set_xlabel("Nifty Spot Price")
    ax.set_ylabel("Profit / Loss (₹)")
    ax.set_title(f"{signal} Option Payoff Diagram")
    ax.legend()
    st.pyplot(fig)

# --- Streamlit UI ---
st.title("📈 Nifty AI Trading Assistant")
st.write("Capital: ₹10,000 | Target Profit: ₹3,000 | Premium Range: ₹80–₹200")

mode = st.radio("Select Mode:", ["Live Trade Plan", "Backtest CALL", "Backtest PUT"])

spot, dow, nasdaq, nikkei = fetch_indices()
gift = None  # Placeholder until Angel One API is added
nifty = yf.download("^NSEI", period="1mo", interval="15m")

signal = check_signal(nifty) if mode == "Live Trade Plan" else ("CALL" if mode == "Backtest CALL" else "PUT")
confidence = calculate_confidence(signal, spot, gift, dow, nasdaq, nikkei)

st.write(f"**Nifty Spot:** {spot}")
st.write(f"**Dow:** {dow}, **Nasdaq:** {nasdaq}, **Nikkei:** {nikkei}")
st.write(f"**Technical Signal:** {signal}")
st.write(f"**Confidence Score:** {confidence}%")

if signal in ["CALL", "PUT"] and confidence >= 70:
    chain = fetch_option_chain()
    records = chain['records']['data']
    strike, premium = select_strike(records, signal, spot)
    if strike and premium:
        st.success(f"Suggested Trade: Buy {signal} at {strike} strike")
        st.write(f"Entry Premium: ₹{premium}")
        st.write("Target Profit: ₹3000 | Stop-Loss: ₹1500")
        payoff_diagram(signal, strike, premium, spot)
    else:
        st.warning("No strike found in ₹80–₹200 range. No trade today.")
else:
    st.warning("Confidence too low or no signal. No trade today.")
