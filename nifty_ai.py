import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import matplotlib.pyplot as plt

# --- Fetch Nifty Spot with NSE API + Fallback ---
def fetch_nifty_spot():
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/"
    }
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=headers)
        response = session.get(url, headers=headers)
        data = response.json()
        if "records" in data and "underlyingValue" in data["records"]:
            return data["records"]["underlyingValue"]
    except Exception:
        pass

    # Fallback to Yahoo Finance
    try:
        df = yf.download("^NSEI", period="1d", interval="1d")
        if not df.empty:
            return df['Close'].iloc[-1].item()
    except Exception:
        pass

    return None

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
        if gift and spot and gift > spot: score += 25
        if dow and nasdaq and dow > 0 and nasdaq > 0: score += 15
        if nikkei and nikkei > 0: score += 10
        score += 40
    elif signal == "PUT":
        if gift and spot and gift < spot: score += 25
        if dow and nasdaq and dow < 0 and nasdaq < 0: score += 15
        if nikkei and nikkei < 0: score += 10
        score += 40
    return score

# --- Option Chain (Safe with Fallback to NIFTY.NS) ---
def fetch_option_chain(symbol="NIFTY.NS"):
    # Try NSE API first
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/"
    }
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=headers)
        data = session.get(url, headers=headers).json()
        if "records" in data and "data" in data["records"]:
            return data["records"]["data"]
    except Exception:
        pass

    # Fallback to Yahoo Finance option chain
    try:
        ticker = yf.Ticker(symbol)
        expiry = ticker.options[0]  # nearest expiry
        chain = ticker.option_chain(expiry)
        records = []
        for _, row in chain.calls.iterrows():
            records.append({"strikePrice": row['strike'], "CE": {"lastPrice": row['lastPrice']}})
        for _, row in chain.puts.iterrows():
            match = next((r for r in records if r['strikePrice'] == row['strike']), None)
            if match:
                match["PE"] = {"lastPrice": row['lastPrice']}
            else:
                records.append({"strikePrice": row['strike'], "PE": {"lastPrice": row['lastPrice']}})
        return records
    except Exception:
        return []

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

mode = st.radio(
    "Select Mode:",
    ["Live Trade Plan", "Backtest CALL", "Backtest PUT"],
    key="mode_selector"
)

spot, dow, nasdaq, nikkei = fetch_indices()
gift = None  # Placeholder until Gift Nifty API is added

if spot is None:
    st.error("⚠️ Nifty Spot data not available. NSE API and Yahoo Finance both failed.")
    st.stop()

nifty = yf.download("^NSEI", period="1mo", interval="15m")

signal = check_signal(nifty) if mode == "Live Trade Plan" else ("CALL" if mode == "Backtest CALL" else "PUT")
confidence = calculate_confidence(signal, spot, gift, dow, nasdaq, nikkei)

st.write(f"**Nifty Spot:** {spot}")
st.write(f"**Dow:** {dow}, **Nasdaq:** {nasdaq}, **Nikkei:** {nikkei}")
st.write(f"**Technical Signal:** {signal}")
st.write(f"**Confidence Score:** {confidence}%")

# --- Option Chain Fetch ---
records = fetch_option_chain()
if not records:
    st.error("⚠️ Option chain data not available from NSE or Yahoo Finance (NIFTY.NS).")
    st.stop()

# --- Premium Filter (₹80–₹200) ---
filtered_strikes = []
for item in records:
    try:
        premium = item['CE']['lastPrice'] if signal == "CALL" else item['PE']['lastPrice']
        if 80 <= premium <= 200:
            filtered_strikes.append(item['strikePrice'])
    except Exception:
        continue

if not filtered_strikes:
    st.warning("No strikes found in ₹80–₹200 premium range.")
else:
    selected_strike = st.selectbox(
        "Select Strike Price (Premium ₹80–₹200):",
        sorted(set(filtered_strikes)),
        key="strike_selector"
    )

    if selected_strike:
        strike_data = next((item for item in records if item['strikePrice'] == selected_strike), None)
        if strike_data:
            premium = strike_data['CE']['lastPrice'] if signal == "CALL" else strike_data['PE']['lastPrice']
            st.write(f"**Selected Strike:** {selected_strike}")
            st.write(f"**Current Premium:** ₹{premium}")
            st.write(f"**Cost to Buy (Lot Size 50):** ₹{premium * 50}")
            payoff_diagram(signal, selected_strike, premium, spot)
