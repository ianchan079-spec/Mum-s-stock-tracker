import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import yfinance as yf
from streamlit_autorefresh import st_autorefresh
import requests
from streamlit_searchbox import st_searchbox
from datetime import date
from typing import List

# --- 1. HEARTBEAT & PAGE CONFIG ---
# Wakes the app up every 60 seconds to update live prices automatically
st_autorefresh(interval=60000, key="pricerefresh") 

st.set_page_config(page_title="Mum's Stock Tracker", layout="wide")
st.title("📈 Live Portfolio Dashboard")

# --- 2. CLOUD DATABASE CONNECTION ---
# Connects using the URL and Service Account in your Streamlit Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        # ttl=0 ensures we don't show "old" data during the auto-refresh
        return conn.read(ttl=0)
    except Exception:
        return pd.DataFrame(columns=["Date", "Ticker", "Type", "Qty", "Price", "Platform"])

# --- 3. SEARCH & INPUT TOOLS ---
def search_stocks(search_term: str) -> List[str]:
    """Provides the autocomplete dropdown for the sidebar."""
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
with st.sidebar.form("input_form", clear_on_submit=True):
    selected_result = st_searchbox(search_stocks, key="ticker_search", label="Search Company/Ticker")
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

# --- 5. REAL-TIME CALCULATIONS & DASHBOARD ---
df = load_data()

if not df.empty:
    # Clean numeric data for math
    df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce')
    df["Price"] = pd.to_numeric(df["Price"], errors='coerce')

    summary_list = []
    port_val, port_pnl = 0.0, 0.0

    for ticker in df['Ticker'].unique():
        t_df = df[df['Ticker'] == ticker]
        
        buys = t_df[t_df['Type'] == 'Buy']
        sells = t_df[t_df['Type'] == 'Sell']
        net_qty = buys['Qty'].sum() - sells['Qty'].sum()

        if net_qty > 0:
            # Weighted average cost math
            avg_cost = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
            
            # Fetch live price from Yahoo
            try:
                live_price = yf.Ticker(ticker).fast_info['last_price']
            except:
                live_price = avg_cost
            
            mkt_val = net_qty * live_price
            pnl = mkt_val - (net_qty * avg_cost)
            
            port_val += mkt_val
            port_pnl += pnl

            summary_list.append({
                "Ticker": ticker, "Shares": net_qty,
                "Avg Cost": f"${avg_cost:.2f}", "Live": f"${live_price:.2f}",
                "Value": f"${mkt_val:,.2f}", "P/L": f"${pnl:,.2f}"
            })

    # Portfolio Metrics
    c1, c2 = st.columns(2)
    c1.metric("Total Portfolio Value", f"${port_val:,.2f}")
    c2.metric("Total Unrealized P/L", f"${port_pnl:,.2f}", delta=f"${port_pnl:,.2f}")

    st.table(pd.DataFrame(summary_list))
else:
    st.info("No trades found. Use the sidebar to add your first stock!")