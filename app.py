# app.py
import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Monte Carlo Credit Spread Simulator", layout="wide")
st.title("Monte Carlo Credit Spread Simulator (Advanced Rollover Logic)")

# ==============================
# Sidebar Inputs
# ==============================
st.sidebar.header("Portfolio Settings")
initial_collateral = st.sidebar.number_input("Initial Collateral ($)", min_value=1000, value=100000, step=1000)
risk_percent = st.sidebar.slider("Target Profit % of Credit", min_value=10, max_value=50, value=30, step=5)
spread_width = st.sidebar.selectbox("Spread Width ($)", [5, 10, 25, 50, 100])
main_contracts = st.sidebar.selectbox("Main Trade Contracts", [5, 10, 25, 50, 100])

st.sidebar.header("Main Trade Setup")
entry_delta = st.sidebar.selectbox("Main Trade Delta", list(range(20, 91)))

st.sidebar.header("Rollover Settings")
max_rollovers = st.sidebar.slider("Max Rollovers", 0, 10, 3)
rollover_delta = st.sidebar.selectbox("Rollover Delta", list(range(20, 91)))

st.sidebar.header("Simulation Settings")
trades_per_sim = st.sidebar.number_input("Number of Trades per Simulation", min_value=10, value=100, step=10)
num_simulations = st.sidebar.number_input("Number of Simulations", min_value=10, value=500, step=50)

# ==============================
# Helper Functions
# ==============================
def calc_credit(delta, spread_width, contracts):
    return (delta / 10) * spread_width * 100 * contracts

def calc_loss(spread_width, contracts, credit):
    return spread_width * 100 * contracts - credit

def simulate_single_trade(collateral, delta, spread_width, contracts, target_profit_percent,
                          max_rollovers, rollover_delta):
    """Simulate one trade with potential rollovers using dynamic sizing"""
    credit = calc_credit(delta, spread_width, contracts)
    target_profit = target_profit_percent / 100 * credit
    loss_amount = calc_loss(spread_width, contracts, credit)

    # Determine win/loss
    prob_win = 100 - delta
    if np.random.rand() * 100 < prob_win:
        pnl = target_profit
        total_trades_used = 1
    else:
        # Initial loss
        pnl = -loss_amount
        total_trades_used = 1

        for r in range(max_rollovers):
            # Determine required contracts to recoup previous loss and make profit
            credit_roll = calc_credit(rollover_delta, spread_width, 1)
            contracts_needed = int(np.ceil(abs(pnl) / credit_roll))
            if contracts_needed == 0:
                contracts_needed = 1
            credit_roll_total = calc_credit(rollover_delta, spread_width, contracts_needed)
            target_profit_roll = target_profit_percent / 100 * credit_roll_total
            loss_roll = calc_loss(spread_width, contracts_needed, credit_roll_total)

            total_trades_used += 1

            if np.random.rand() * 100 < (100 - rollover_delta):
                # Win on rollover
                pnl = -pnl + target_profit_roll  # recoup previous loss + new profit
                break
            else:
                # Loss on rollover, accumulate
                pnl = pnl - loss_roll

    final_collateral = collateral + pnl
    return final_collateral, total_trades_used

# ==============================
# Run Monte Carlo Simulation
# ==============================
all_final_accounts = []
all_trade_counts = []

for sim in range(num_simulations):
    collateral = initial_collateral
    trades_count = []
    for t in range(trades_per_sim):
        collateral, trades_used = simulate_single_trade(collateral, entry_delta, spread_width, main_contracts,
                                                        risk_percent, max_rollovers, rollover_delta)
        trades_count.append(trades_used)
    all_final_accounts.append(collateral)
    all_trade_counts.append(trades_count)

# ==============================
# Dashboard Metrics
# ==============================
st.subheader("Simulation Dashboard")
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Simulations", num_simulations)
col2.metric("Trades per Simulation", trades_per_sim)
col3.metric("Initial Collateral ($)", f"{initial_collateral:,.0f}")
col4.metric("Median Final Account ($)", f"{np.median(all_final_accounts):,.0f}")
col5.metric("Best Case ($)", f"{np.max(all_final_accounts):,.0f}")
col6.metric("Worst Case ($)", f"{np.min(all_final_accounts):,.0f}")

# ==============================
# Histogram of Final Accounts
# ==============================
st.subheader("Histogram of Final Account Values")
hist_fig = px.histogram(all_final_accounts, nbins=50,
                        labels={'value': 'Final Account Value ($)'},
                        title='Distribution of Ending Account Values')
st.plotly_chart(hist_fig, use_container_width=True)

# ==============================
# Sample Trade Trajectories
# ==============================
st.subheader("Sample Trade Trajectories (First 50 Simulations)")
sample_trades = np.array(all_trade_counts[:50])
cum_trades = np.cumsum(sample_trades, axis=1)
trade_fig = px.line(cum_trades.T, labels={'index': 'Trade Number', 'value': 'Cumulative Trades'},
                    title='Cumulative Trade Counts per Simulation')
st.plotly_chart(trade_fig, use_container_width=True)

# ==============================
# Simulation Summary Table
# ==============================
st.subheader("Simulation Summary Table")
summary_df = pd.DataFrame({
    'Simulation': range(1, num_simulations + 1),
    'Final Account ($)': all_final_accounts,
    'Max Trades Used': [max(tc) for tc in all_trade_counts]
})
st.dataframe(summary_df.sort_values(by='Final Account ($)', ascending=False))
