import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import yfinance as yf
import requests
from streamlit_searchbox import st_searchbox
from datetime import date
from typing import List

# --- APP CONFIG ---
st.set_page_config(page_title="Mum's Stock Tracker", layout="wide")
st.title("📈 Mum's Stock Tracker")

# --- GOOGLE SHEETS CONNECTION ---
# This connection automatically reads from the URL in your Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        # ttl=0 ensures we always get the latest data when the app refreshes
        return conn.read(ttl=0)
    except Exception:
        # Fallback if the sheet is empty
        return pd.DataFrame(columns=["Date", "Ticker", "Type", "Qty", "Price", "Platform"])

def search_stocks(search_term: str) -> List[str]:
    """Autocomplete search for company names and tickers."""
    if not search_term or len(search_term) < 2:
        return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={search_term}&quotes_count=5"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        return [f"{q['symbol']} ({q.get('longname', 'Unknown')})" for q in res.get('quotes', [])]
    except Exception:
        return []

# --- SIDEBAR: ADD TRADES ---
st.sidebar.header("➕ Add New Trade")
with st.sidebar.form("input_form", clear_on_submit=True):
    selected_result = st_searchbox(search_stocks, key="ticker_search", label="Search Company or Ticker")
    t_date = st.date_input("Trade Date", date.today())
    t_type = st.selectbox("Type", ["Buy", "Sell"])
    t_platform = st.text_input("Platform / Account", placeholder="e.g. Robinhood")
    t_qty = st.number_input("Quantity", min_value=0.0, step=0.1)
    t_price = st.number_input("Price Paid ($)", min_value=0.0, step=0.01)
    submitted = st.form_submit_button("Save to Cloud")

if submitted and selected_result:
    ticker = selected_result.split(" ")[0]
    existing_df = load_data()
    
    new_row = pd.DataFrame([{
        "Date": str(t_date),
        "Ticker": ticker,
        "Type": t_type,
        "Qty": t_qty,
        "Price": t_price,
        "Platform": t_platform.strip().title() if t_platform else "Direct"
    }])
    
    updated_df = pd.concat([existing_df, new_row], ignore_index=True)
    
    # Update the Google Sheet
    conn.update(data=updated_df)
    st.sidebar.success(f"Successfully added {ticker} to the cloud!")
    st.rerun()

# --- MAIN DASHBOARD ---
df = load_data()

if not df.empty:
    # --- SEARCH & FILTER ---
    search_query = st.text_input("🔍 Search your portfolio", "").upper()
    
    summary_list = []
    total_val, total_pnl = 0.0, 0.0

    # Ensure numeric types
    df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce')
    df["Price"] = pd.to_numeric(df["Price"], errors='coerce')

    for ticker in df['Ticker'].unique():
        t_df = df[df['Ticker'] == ticker]
        for plat in t_df['Platform'].unique():
            p_df = t_df[t_df['Platform'] == plat]
            
            if search_query and (search_query not in ticker and search_query not in plat.upper()):
                continue

            buys = p_df[p_df['Type'] == 'Buy']
            sells = p_df[p_df['Type'] == 'Sell']
            
            net_qty = buys['Qty'].sum() - sells['Qty'].sum()
            
            if net_qty > 0:
                avg_cost = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
                try:
                    live_price = yf.Ticker(ticker).fast_info['last_price']
                except:
                    live_price = avg_cost
                
                val = net_qty * live_price
                pnl = val - (net_qty * avg_cost)
                
                total_val += val
                total_pnl += pnl
                
                summary_list.append({
                    "Ticker": ticker, "Platform": plat, "Shares": net_qty,
                    "Avg Cost": f"${avg_cost:.2f}", "Live": f"${live_price:.2f}",
                    "Value": f"${val:,.2f}", "P/L": f"${pnl:,.2f}"
                })

    # Summary Metrics
    c1, c2 = st.columns(2)
    c1.metric("Total Portfolio Value", f"${total_val:,.2f}")
    c2.metric("Total Profit/Loss", f"${total_pnl:,.2f}", delta=f"${total_pnl:,.2f}")

    if summary_list:
        st.table(pd.DataFrame(summary_list))
    else:
        st.info("No active positions matching search.")
else:
    st.info("No trades recorded yet. Use the sidebar to start!")