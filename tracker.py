import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

# --- 1. HEARTBEAT ---
st_autorefresh(interval=60000, key="pricerefresh")

st.set_page_config(page_title="Mum's Portfolio", layout="wide")
st.title("📈 Portfolio Dashboard & Performance")

# --- 2. CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    return conn.read(ttl=0)

# --- 3. DATA PROCESSING ---
df = load_data()

if not df.empty:
    df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce')
    df["Price"] = pd.to_numeric(df["Price"], errors='coerce')
    df["Date"] = pd.to_datetime(df["Date"]) # Ensure dates are usable for charts

    active_positions = []
    realized_trades = []
    total_market_val, total_unrealized_pnl, total_realized_profit = 0.0, 0.0, 0.0

    for ticker in df['Ticker'].unique():
        t_df = df[df['Ticker'] == ticker]
        buys = t_df[t_df['Type'] == 'Buy']
        sells = t_df[t_df['Type'] == 'Sell']
        
        net_qty = buys['Qty'].sum() - sells['Qty'].sum()
        
        # --- REALIZED LOGIC ---
        if not sells.empty:
            avg_buy_price = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
            for _, sell_row in sells.iterrows():
                profit = (sell_row['Price'] - avg_buy_price) * sell_row['Qty']
                total_realized_profit += profit
                realized_trades.append({
                    "Date": sell_row['Date'],
                    "Ticker": ticker,
                    "Profit": profit
                })

        # --- UNREALIZED LOGIC ---
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
                "Ticker": ticker, "Shares": net_qty, "Avg Cost": avg_cost,
                "Live": live_price, "Value": cur_val, "P/L": un_pnl
            })

    # --- 4. TOP METRICS (WITH AUTO-COLOR) ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Current Value", f"${total_market_val:,.2f}")
    c2.metric("Unrealized P/L", f"${total_unrealized_pnl:,.2f}", delta=f"${total_unrealized_pnl:,.2f}")
    c3.metric("Total Realized", f"${total_realized_profit:,.2f}", delta=f"${total_realized_profit:,.2f}")

    # --- 5. PROFIT OVER TIME CHART ---
    if realized_trades:
        st.subheader("💰 Realized Profit Growth")
        chart_df = pd.DataFrame(realized_trades).sort_values("Date")
        chart_df["Cumulative Profit"] = chart_df["Profit"].cumsum()
        st.area_chart(data=chart_df, x="Date", y="Cumulative Profit")

    # --- 6. TABLES ---
    st.subheader("📋 Active Positions")
    if active_positions:
        active_df = pd.DataFrame(active_positions)
        # Apply color based on P/L column
        st.table(active_df.style.applymap(lambda x: 'color: green' if x > 0 else 'color: red', subset=['P/L'])
                 .format({"Avg Cost": "${:.2f}", "Live": "${:.2f}", "Value": "${:,.2f}", "P/L": "${:,.2f}"}))
else:
    st.info("No trades found. Add some in the sidebar!")