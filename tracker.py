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
# Keeps market prices live by refreshing every 60 seconds
st_autorefresh(interval=60000, key="pricerefresh")

st.set_page_config(page_title="Mum's Stock Dashboard", layout="wide")
st.title("📈 Stock Portfolio & History")

# --- 2. CLOUD DATABASE CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        # ttl=0 ensures we pull the absolute latest data from the sheet
        return conn.read(ttl=0)
    except Exception:
        return pd.DataFrame(columns=["Date", "Ticker", "Type", "Qty", "Price", "Platform"])

@st.cache_data(ttl="1d") # Cache company names to keep the app snappy
def get_company_name(ticker):
    try:
        return yf.Ticker(ticker).info.get('longName', ticker)
    except:
        return ticker

# --- 3. SEARCH & AUTO-PRICE LOGIC ---
def search_stocks(search_term: str) -> List[str]:
    if not search_term or len(search_term) < 2:
        return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={search_term}&quotes_count=5"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        return [f"{q['symbol']} ({q.get('longname', 'Unknown')})" for q in res.get('quotes', [])]
    except Exception:
        return []

# --- 4. SIDEBAR: INTUITIVE ENTRY ---
with st.sidebar:
    st.header("➕ Add New Trade")
    
    # STEP 1: Search (Live/Outside form)
    selected_result = st_searchbox(search_stocks, key="ticker_search", label="1. Search Stock")
    
    suggested_price = 0.0
    if selected_result:
        ticker_symbol = selected_result.split(" ")[0]
        try:
            suggested_price = yf.Ticker(ticker_symbol).fast_info['last_price']
        except:
            suggested_price = 0.0

    # STEP 2: Entry Details (In a form to prevent accidental submission)
    with st.form("trade_form", clear_on_submit=True):
        st.write("2. Transaction Details")
        t_date = st.date_input("Trade Date", date.today())
        
        c1, c2 = st.columns(2)
        t_type = c1.selectbox("Type", ["Buy", "Sell"])
        t_platform = c2.text_input("Platform", placeholder="e.g. MooMoo")
        
        t_qty = st.number_input("Quantity", min_value=0.0, step=0.1)
        # Price field defaults to the live market value
        t_price = st.number_input("Price ($)", min_value=0.0, value=float(suggested_price), step=0.01)
        
        submitted = st.form_submit_button("Save to Cloud")

if submitted and selected_result:
    ticker = selected_result.split(" ")[0]
    df = load_data()
    new_entry = pd.DataFrame([{"Date": str(t_date), "Ticker": ticker, "Type": t_type, 
                               "Qty": t_qty, "Price": t_price, "Platform": t_platform}])
    updated_df = pd.concat([df, new_entry], ignore_index=True)
    conn.update(data=updated_df)
    st.sidebar.success(f"Added {ticker}!")
    st.rerun()

# --- 5. TABS FOR ORGANIZATION ---
# Creating tabs to separate the Live Dashboard from the Full History
tab1, tab2 = st.tabs(["📊 Live Dashboard", "📜 Transaction History"])

all_data = load_data()

with tab1:
    if not all_data.empty:
        # Convert numeric types
        all_data["Qty"] = pd.to_numeric(all_data["Qty"], errors='coerce')
        all_data["Price"] = pd.to_numeric(all_data["Price"], errors='coerce')
        all_data["Date"] = pd.to_datetime(all_data["Date"])

        active_positions = []
        realized_trades = []
        total_market_val, total_unrealized_pnl, total_realized_profit = 0.0, 0.0, 0.0

        for ticker in all_data['Ticker'].unique():
            t_df = all_data[all_data['Ticker'] == ticker]
            buys = t_df[t_df['Type'] == 'Buy']
            sells = t_df[t_df['Type'] == 'Sell']
            net_qty = buys['Qty'].sum() - sells['Qty'].sum()
            
            # Realized Calculations
            if not sells.empty:
                avg_buy_price = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
                for _, sell_row in sells.iterrows():
                    profit = (sell_row['Price'] - avg_buy_price) * sell_row['Qty']
                    total_realized_profit += profit
                    realized_trades.append({"Date": sell_row['Date'], "Ticker": ticker, "Profit": profit})

            # Unrealized (Active) Positions
            if net_qty > 0:
                avg_cost = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
                try:
                    live_price = yf.Ticker(ticker).fast_info['last_price']
                except:
                    live_price = avg_cost
                
                cur_val = net_qty * live_price
                un_pnl = cur_val - (net_qty * avg_cost)
                total_market_val += cur_val
                total_unrealized_pnl += un_pnl

                active_positions.append({
                    "Ticker": ticker, "Company": get_company_name(ticker), "Shares": net_qty,
                    "Avg Cost": avg_cost, "Live": live_price, "Value": cur_val, "P/L": un_pnl
                })

        # Metrics display
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Value", f"${total_market_val:,.2f}")
        m2.metric("Unrealized P/L", f"${total_unrealized_pnl:,.2f}", delta=f"${total_unrealized_pnl:,.2f}")
        m3.metric("Total Realized", f"${total_realized_profit:,.2f}", delta=f"${total_realized_profit:,.2f}")

        # Active Positions Table
        st.subheader("📋 Active Positions")
        if active_positions:
            active_df = pd.DataFrame(active_positions)
            st.table(active_df.style.applymap(lambda x: 'color: green' if x > 0 else 'color: red', subset=['P/L'])
                     .format({"Avg Cost": "${:.2f}", "Live": "${:.2f}", "Value": "${:,.2f}", "P/L": "${:,.2f}"}))
        
        # Cumulative Chart
        if realized_trades:
            st.subheader("💰 Realized Profit Over Time")
            chart_df = pd.DataFrame(realized_trades).sort_values("Date")
            chart_df["Cumulative Profit"] = chart_df["Profit"].cumsum()
            st.area_chart(data=chart_df, x="Date", y="Cumulative Profit")
    else:
        st.info("The sidebar is ready! Add your first trade to get started.")

with tab2:
    st.subheader("📜 Full History")
    if not all_data.empty:
        # Displaying the raw CSV/Sheet data so she can audit her entries
        st.dataframe(all_data.sort_values("Date", ascending=False), use_container_width=True)
    else:
        st.write("No transactions recorded yet.")