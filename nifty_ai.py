import pandas as pd
import numpy as np
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt

# Step 1: Fetch Spot & Global Indices
def fetch_indices():
    spot = fetch_nifty_spot()
    # Keep global indices with yfinance (Dow, Nasdaq, Nikkei)
    dow = safe_download("^DJI")
    nasdaq = safe_download("^IXIC")
    nikkei = safe_download("^N225")
    return spot, dow, nasdaq, nikkei


# Step 2: Scrape Gift Nifty from Angel One
def fetch_gift_nifty():
    url = "https://www.angelone.in/markets/indices/gift-nifty"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # Adjust selector after inspecting Angel One’s Gift Nifty page
    price_tag = soup.find("span", {"class": "gift-nifty-price"})
    if price_tag:
        return float(price_tag.text.replace(",", "").strip())
    else:
        return None

def safe_download(symbol, period="1d", interval="1d"):
    try:
        df = yf.download(symbol, period=period, interval=interval)
        if not df.empty:
            return df['Close'].iloc[-1].item()
        else:
            return None
    except Exception:
        return None
spot, dow, nasdaq, nikkei = fetch_indices()

if spot is None:
    st.error("Nifty Spot data not available. Please try again later.")
    st.stop()


# Step 3: Technical Indicators
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

# Step 4: Confidence Scoring
def calculate_confidence(signal, spot, gift, dow, nasdaq, nikkei):
    score = 0
    if signal == "CALL":
        if gift and gift > spot: score += 25
        if dow > 0 and nasdaq > 0: score += 15
        if nikkei > 0: score += 10
        score += 40
    elif signal == "PUT":
        if gift and gift < spot: score += 25
        if dow < 0 and nasdaq < 0: score += 15
        if nikkei < 0: score += 10
        score += 40
    return score

# Step 5: Option Chain
def fetch_option_chain(symbol="NIFTY"):
    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    data = session.get(url, headers=headers).json()
    return data

# Step 6: Payoff Diagram
def payoff_diagram(signal, strike, premium, spot, lot_size=50):
    prices = np.arange(spot-300, spot+300, 50)
    payoff = []
    for p in prices:
        if signal == "CALL":
            payoff.append((max(p - strike, 0) - premium) * lot_size)
        else:
            payoff.append((max(strike - p, 0) - premium) * lot_size)
    plt.plot(prices, payoff, label=f"Buy {signal}")
    plt.axhline(0, color="black", linestyle="--")
    plt.xlabel("Nifty Spot Price")
    plt.ylabel("Profit / Loss (₹)")
    plt.title(f"{signal} Option Payoff Diagram")
    plt.legend()
    plt.show()

# Step 7: Trade Plan
def trading_plan():
    spot, dow, nasdaq, nikkei = fetch_indices()
    gift = fetch_gift_nifty()
    nifty = yf.download("^NSEI", period="1mo", interval="15m")
    signal = check_signal(nifty)
    atm_strike = round(spot / 50) * 50

    print(f"Nifty Spot: {spot}, Gift Nifty: {gift}, Dow: {dow}, Nasdaq: {nasdaq}, Nikkei: {nikkei}")
    print(f"Technical Signal: {signal}, ATM Strike: {atm_strike}")

    if signal in ["CALL", "PUT"]:
        confidence = calculate_confidence(signal, spot, gift, dow, nasdaq, nikkei)
        print(f"Confidence Score: {confidence}%")
        if confidence >= 70:
            chain = fetch_option_chain()
            records = chain['records']['data']
            atm_data = next((item for item in records if item['strikePrice'] == atm_strike), None)
            if atm_data:
                premium = atm_data['CE']['lastPrice'] if signal == "CALL" else atm_data['PE']['lastPrice']
                print(f"Suggested Trade: Buy {signal} at {atm_strike} strike")
                print(f"Entry Premium: ₹{premium}")
                print("Target Profit: ₹3000 | Stop-Loss: ₹1500")
                payoff_diagram(signal, atm_strike, premium, spot)
            else:
                print("ATM strike not found in option chain.")
        else:
            print("Confidence too low. No trade today.")
    else:
        print("No trade today. Stay disciplined.")

if __name__ == "__main__":
    trading_plan()
