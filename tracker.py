import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

# --- 1. AUTO-REFRESH CONFIG ---
# This "wakes up" the app every 60 seconds (60,000 milliseconds)
# It fetches fresh stock prices automatically without Mum clicking anything.
st_autorefresh(interval=60000, key="pricerefresh")

st.set_page_config(page_title="Mum's Live Portfolio", layout="wide")
st.title("📈 Live Portfolio Tracker")

# --- 2. DATABASE CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # Set ttl to 0 so every auto-refresh pulls the latest sheet data
    return conn.read(ttl=0)

# --- 3. LIVE CALCULATIONS ---
df = load_data()

if not df.empty:
    # Convert data types for math
    df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce')
    df["Price"] = pd.to_numeric(df["Price"], errors='coerce')

    summary_list = []
    total_market_val = 0.0
    total_pnl = 0.0

    # Group by Ticker to handle multiple buys of the same stock
    for ticker in df['Ticker'].unique():
        t_df = df[df['Ticker'] == ticker]
        
        buys = t_df[t_df['Type'] == 'Buy']
        sells = t_df[t_df['Type'] == 'Sell']
        net_qty = buys['Qty'].sum() - sells['Qty'].sum()

        if net_qty > 0:
            # Weighted Average Cost Basis
            avg_cost = (buys['Qty'] * buys['Price']).sum() / buys['Qty'].sum()
            
            # Fetch the Current Market Price
            try:
                # 'fast_info' is used for high-speed live price access
                live_price = yf.Ticker(ticker).fast_info['last_price']
            except:
                live_price = avg_cost # Fallback if connection fails

            # PNL math
            current_val = net_qty * live_price
            unrealized_pnl = current_val - (net_qty * avg_cost)
            
            total_market_val += current_val
            total_pnl += unrealized_pnl

            summary_list.append({
                "Ticker": ticker,
                "Shares": net_qty,
                "Avg Cost": f"${avg_cost:.2f}",
                "LIVE PRICE": f"${live_price:.2f}", # The live column
                "Total Value": f"${current_val:,.2f}",
                "Profit/Loss": f"${unrealized_pnl:,.2f}"
            })

    # --- 4. TOP-LEVEL DASHBOARD ---
    # These metrics update automatically every minute
    col1, col2 = st.columns(2)
    col1.metric("Total Portfolio Value", f"${total_market_val:,.2f}")
    
    # Delta shows the PNL as green (up) or red (down)
    col2.metric("Total Unrealized P/L", f"${total_pnl:,.2f}", delta=f"${total_pnl:,.2f}")

    # Display breakdown
    st.dataframe(pd.DataFrame(summary_list), use_container_width=True)
else:
    st.info("Add some trades in the sidebar to see live prices!")