import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from streamlit_searchbox import st_searchbox
from datetime import date
import os

CSV_FILE = "trade_history.csv"

def load_data():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE)
    return pd.DataFrame(columns=["Date", "Ticker", "Type", "Qty", "Price", "Platform"])

def search_stocks(search_term: str):
    if not search_term or len(search_term) < 2: return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={search_term}&quotes_count=5"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        return [f"{q['symbol']} ({q.get('longname', 'Unknown')})" for q in res['quotes']]
    except: return []

st.set_page_config(page_title="Mum's Portfolio", layout="wide")
st.title("📈 Mum's Stock Tracker")

# --- SIDEBAR INPUT ---
st.sidebar.header("➕ Add New Trade")
with st.sidebar.form("input_form", clear_on_submit=True):
    selected_result = st_searchbox(search_stocks, key="ticker_search", label="Search Company or Ticker")
    t_date = st.date_input("Trade Date", date.today())
    t_type = st.selectbox("Type", ["Buy", "Sell"])
    t_platform = st.text_input("Platform / Account", placeholder="e.g. Robinhood")
    t_qty = st.number_input("Quantity", min_value=0.0, step=0.1)
    t_price = st.number_input("Price Paid ($)", min_value=0.0, step=0.01)
    submitted = st.form_submit_button("Save Trade")

if submitted and selected_result:
    ticker = selected_result.split(" ")[0]
    df = load_data()
    new_row = {"Date": t_date, "Ticker": ticker, "Type": t_type, "Qty": t_qty, "Price": t_price, "Platform": t_platform.title()}
    pd.concat([df, pd.DataFrame([new_row])]).to_csv(CSV_FILE, index=False)
    st.sidebar.success(f"Added {ticker}!")
    st.rerun()

# --- MAIN DASHBOARD ---
df = load_data()
if not df.empty:
    summary = []
    for ticker in df['Ticker'].unique():
        t_df = df[df['Ticker'] == ticker]
        for plat in t_df['Platform'].unique():
            p_df = t_df[t_df['Platform'] == plat]
            buys = p_df[p_df['Type'] == 'Buy']
            sells = p_df[p_df['Type'] == 'Sell']
            net_qty = buys['Qty'].sum() - sells['Qty'].sum()
            if net_qty > 0:
                avg_cost = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
                try:
                    live = yf.Ticker(ticker).fast_info['last_price']
                except: live = avg_cost
                val = net_qty * live
                pnl = val - (net_qty * avg_cost)
                summary.append({"Ticker": ticker, "Platform": plat, "Shares": net_qty, "Avg Cost": f"${avg_cost:.2f}", "Live": f"${live:.2f}", "Value": f"${val:,.2f}", "P/L": f"${pnl:,.2f}"})
    st.table(pd.DataFrame(summary))
else:
    st.info("No trades yet! Use the sidebar.")