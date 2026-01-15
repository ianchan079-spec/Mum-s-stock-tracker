import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import yfinance as yf
from streamlit_autorefresh import st_autorefresh
from streamlit_searchbox import st_searchbox
import requests
from datetime import date
from typing import List

@st.cache_data(ttl="1d") # Only look up names once a day to keep it fast
def get_company_name(ticker):
    try:
        return yf.Ticker(ticker).info.get('longName', ticker)
    except:
        return ticker
    
# --- 1. HEARTBEAT & CONFIG ---
# Automatically refreshes the app every 60 seconds to update live prices
st_autorefresh(interval=60000, key="pricerefresh")

st.set_page_config(page_title="Mum's Stock Tracker", layout="wide")
st.title("📈 Live Portfolio & Historical Performance")

# --- 2. CLOUD DATABASE CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        return conn.read(ttl=0)
    except Exception:
        return pd.DataFrame(columns=["Date", "Ticker", "Type", "Qty", "Price", "Platform"])

# --- 3. SEARCH FUNCTIONALITY ---
def search_stocks(search_term: str) -> List[str]:
    """Provides autocomplete for the sidebar trade entry."""
    if not search_term or len(search_term) < 2:
        return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={search_term}&quotes_count=5"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        return [f"{q['symbol']} ({q.get('longname', 'Unknown')})" for q in res.get('quotes', [])]
    except Exception:
        return []

# --- 4. SIDEBAR: KEYING IN TRADES (FIXED FOR LIVE SEARCH) ---
st.sidebar.header("➕ Add New Trade")

# 1. Search Box is OUTSIDE the form so it is "Live"
selected_result = st_searchbox(
    search_stocks, 
    key="ticker_search", 
    label="1. Search Company/Ticker"
)

# 2. The rest of the details are INSIDE the form
with st.sidebar.form("input_form", clear_on_submit=True):
    st.write("2. Enter Trade Details")
    t_date = st.date_input("Trade Date", date.today())
    t_type = st.selectbox("Type", ["Buy", "Sell"])
    t_platform = st.text_input("Platform", placeholder="e.g. Robinhood")
    t_qty = st.number_input("Quantity", min_value=0.0, step=0.1)
    t_price = st.number_input("Price Paid ($)", min_value=0.0, step=0.01)
    
    submitted = st.form_submit_button("Save to Cloud")

# 3. Final Check: Only save if both the search result and the button are clicked
if submitted:
    if not selected_result:
        st.sidebar.error("Please select a ticker from the search results first!")
    else:
        ticker = selected_result.split(" ")[0]
        existing_df = load_data()
        
        new_entry = pd.DataFrame([{
            "Date": str(t_date), "Ticker": ticker, "Type": t_type,
            "Qty": t_qty, "Price": t_price, "Platform": t_platform.strip() or "Direct"
        }])
        
        updated_df = pd.concat([existing_df, new_entry], ignore_index=True)
        conn.update(data=updated_df)
        st.sidebar.success(f"Saved {ticker}!")
        st.rerun()

# --- 5. DATA PROCESSING & CALCULATIONS ---
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
        
        # Realized Profit Logic
        if not sells.empty:
            avg_buy_price = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
            for _, sell_row in sells.iterrows():
                profit = (sell_row['Price'] - avg_buy_price) * sell_row['Qty']
                total_realized_profit += profit
                realized_trades.append({"Date": sell_row['Date'], "Ticker": ticker, "Profit": profit})

        # Active (Unrealized) Position Logic
        if net_qty > 0:
        avg_cost = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
        
        # 1. Fetch Company Name (New)
        name = get_company_name(ticker)

            try:
                live_price = yf.Ticker(ticker).fast_info['last_price']
            except:
                live_price = avg_cost
            
            cur_val = net_qty * live_price
            un_pnl = cur_val - (net_qty * avg_cost)
            total_market_val += cur_val
            total_unrealized_pnl += un_pnl

            active_positions.append({
            "Ticker": ticker,
            "Company": name, # New Column added here
            "Shares": net_qty,
            "Avg Cost": avg_cost,
            "Live": live_price,
            "Value": cur_val,
            "P/L": un_pnl
        })
            })

    # --- 6. DASHBOARD DISPLAY ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Portfolio Value", f"${total_market_val:,.2f}")
    c2.metric("Unrealized P/L", f"${total_unrealized_pnl:,.2f}", delta=f"${total_unrealized_pnl:,.2f}")
    c3.metric("Total Realized", f"${total_realized_profit:,.2f}", delta=f"${total_realized_profit:,.2f}")

    # Cumulative Profit Chart
    if realized_trades:
        st.subheader("💰 Realized Profit Over Time")
        chart_df = pd.DataFrame(realized_trades).sort_values("Date")
        chart_df["Cumulative Profit"] = chart_df["Profit"].cumsum()
        st.area_chart(data=chart_df, x="Date", y="Cumulative Profit")

    # Table for Active Positions with Color
    st.subheader("📋 Active Positions")
    if active_positions:
        active_df = pd.DataFrame(active_positions)
        st.table(active_df.style.applymap(lambda x: 'color: green' if x > 0 else 'color: red', subset=['P/L'])
                 .format({"Avg Cost": "${:.2f}", "Live": "${:.2f}", "Value": "${:,.2f}", "P/L": "${:,.2f}"}))
else:
    st.info("The sidebar is ready! Add your first trade to get started.")