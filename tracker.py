import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import yfinance as yf
from streamlit_autorefresh import st_autorefresh
from streamlit_searchbox import st_searchbox
import requests
from datetime import date
from typing import List

# --- 1. CONFIG & AUTO-REFRESH ---
# Refreshes the app every 60 seconds to keep market prices live
st_autorefresh(interval=60000, key="pricerefresh")

st.set_page_config(page_title="Mum's Stock Tracker", layout="wide")
st.title("📈 Live Portfolio & Historical Performance")

# --- 2. CLOUD DATABASE CONNECTION ---
# Connects via the URL and Service Account in your Streamlit Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        return conn.read(ttl=0) # Pulls fresh data from Google Sheets
    except Exception:
        return pd.DataFrame(columns=["Date", "Ticker", "Type", "Qty", "Price", "Platform"])

@st.cache_data(ttl="1d") # Cache company names for 24 hours to keep the app fast
def get_company_name(ticker):
    try:
        return yf.Ticker(ticker).info.get('longName', ticker)
    except:
        return ticker

# --- 3. SEARCH FUNCTIONALITY ---
def search_stocks(search_term: str) -> List[str]:
    """Provides real-time autocomplete search for tickers."""
    if not search_term or len(search_term) < 2:
        return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={search_term}&quotes_count=5"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        return [f"{q['symbol']} ({q.get('longname', 'Unknown')})" for q in res.get('quotes', [])]
    except Exception:
        return []

# --- 4. SIDEBAR: KEYING IN TRADES ---
st.sidebar.header("➕ Add New Trade")

# Search box is OUTSIDE the form so it is live and intuitive
selected_result = st_searchbox(search_stocks, key="ticker_search", label="1. Search Ticker")

with st.sidebar.form("input_form", clear_on_submit=True):
    st.write("2. Enter Trade Details")
    t_date = st.date_input("Trade Date", date.today())
    t_type = st.selectbox("Type", ["Buy", "Sell"])
    t_platform = st.text_input("Platform", placeholder="e.g. Robinhood")
    t_qty = st.number_input("Quantity", min_value=0.0, step=0.1)
    t_price = st.number_input("Price Paid ($)", min_value=0.0, step=0.01)
    submitted = st.form_submit_button("Save to Cloud")

if submitted and selected_result:
    ticker = selected_result.split(" ")[0]
    existing_df = load_data()
    
    new_entry = pd.DataFrame([{
        "Date": str(t_date), "Ticker": ticker, "Type": t_type,
        "Qty": t_qty, "Price": t_price, "Platform": t_platform.strip() or "Direct"
    }])
    
    # Push updated list back to Google Sheets
    updated_df = pd.concat([existing_df, new_entry], ignore_index=True)
    conn.update(data=updated_df)
    st.sidebar.success(f"Successfully saved {ticker}!")
    st.rerun()

# --- 5. DATA PROCESSING & LIVE CALCULATIONS ---
df = load_data()

if not df.empty:
    df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce')
    df["Price"] = pd.to_numeric(df["Price"], errors='coerce')
    df["Date"] = pd.to_datetime(df["Date"])

    active_positions = []
    realized_trades = []
    total_market_val, total_unrealized_pnl, total_realized_profit = 0.0, 0.0, 0.0

    for ticker in df['Ticker'].unique():
        t_df = df[df['Ticker'] == ticker]
        buys = t_df[t_df['Type'] == 'Buy']
        sells = t_df[t_df['Type'] == 'Sell']
        net_qty = buys['Qty'].sum() - sells['Qty'].sum()
        
        # Realized Profit Calculation
        if not sells.empty:
            avg_buy_price = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
            for _, sell_row in sells.iterrows():
                profit = (sell_row['Price'] - avg_buy_price) * sell_row['Qty']
                total_realized_profit += profit
                realized_trades.append({"Date": sell_row['Date'], "Ticker": ticker, "Profit": profit})

        # Active Position Logic with Company Names
        if net_qty > 0:
            avg_cost = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
            try:
                live_price = yf.Ticker(ticker).fast_info['last_price']
            except:
                live_price = avg_cost
            
            comp_name = get_company_name(ticker)
            mkt_val = net_qty * live_price
            pnl = mkt_val - (net_qty * avg_cost)
            
            total_market_val += mkt_val
            total_unrealized_pnl += pnl

            active_positions.append({
                "Ticker": ticker,
                "Company": comp_name,
                "Shares": net_qty,
                "Avg Cost": avg_cost,
                "Live": live_price,
                "Value": mkt_val,
                "P/L": pnl
            })

    # --- 6. DISPLAY DASHBOARD ---
    # Top Metrics with Auto-Coloring
    c1, c2, c3 = st.columns(3)
    c1.metric("Portfolio Value", f"${total_market_val:,.2f}")
    c2.metric("Unrealized P/L", f"${total_unrealized_pnl:,.2f}", delta=f"${total_unrealized_pnl:,.2f}")
    c3.metric("Total Realized", f"${total_realized_profit:,.2f}", delta=f"${total_realized_profit:,.2f}")

    # Profit Chart
    if realized_trades:
        st.subheader("💰 Realized Profit Growth")
        chart_df = pd.DataFrame(realized_trades).sort_values("Date")
        chart_df["Cumulative Profit"] = chart_df["Profit"].cumsum()
        st.area_chart(data=chart_df, x="Date", y="Cumulative Profit")

    # Active Positions Table with Green/Red P/L
    st.subheader("📋 Active Positions")
    if active_positions:
        active_df = pd.DataFrame(active_positions)
        st.table(active_df.style.applymap(lambda x: 'color: green' if x > 0 else 'color: red', subset=['P/L'])
                 .format({"Avg Cost": "${:.2f}", "Live": "${:.2f}", "Value": "${:,.2f}", "P/L": "${:,.2f}"}))
else:
    st.info("The sidebar is ready! Add your first trade to get started.")