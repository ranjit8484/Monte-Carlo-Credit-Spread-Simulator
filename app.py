# app.py
import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Monte Carlo Credit Spread Simulator", layout="wide")
st.title("Monte Carlo Credit Spread Simulator")

# -------------------------------
# Sidebar Inputs
# -------------------------------
st.sidebar.header("Portfolio & Trade Settings")
initial_collateral = st.sidebar.number_input("Initial Collateral ($)", value=100000, step=1000)
spread_width = st.sidebar.selectbox("Spread Width ($)", [5, 10, 25, 50, 100])
target_profit_pct = st.sidebar.slider("Target Profit % of Credit", min_value=10, max_value=50, value=30, step=5)
main_contracts = st.sidebar.selectbox("Main Trade Contracts", [5, 10, 25, 50, 100])
entry_delta = st.sidebar.slider("Main Trade Delta", min_value=20, max_value=90, value=50, step=5)
rollover_delta = st.sidebar.slider("Rollover Delta", min_value=20, max_value=90, value=50, step=5)
max_rollovers = st.sidebar.slider("Max Rollovers", min_value=0, max_value=10, value=2, step=1)

st.sidebar.header("Simulation Settings")
num_trades_per_sim = st.sidebar.number_input("Number of Trades per Simulation", value=50, step=10)
num_simulations = st.sidebar.number_input("Number of Simulations", value=1000, step=100)

# -------------------------------
# Helper Functions
# -------------------------------
def simulate_trade(delta, contracts, spread_width, target_profit_pct):
    prob_win = 100 - delta
    credit = delta / 10 * spread_width * 100 * contracts
    target_profit = credit * target_profit_pct / 100
    loss_amount = spread_width * 100 * contracts - credit

    win = np.random.rand() * 100 < prob_win
    if win:
        return target_profit, 1, True
    else:
        return -loss_amount, 1, False

def simulate_rollover(loss_amount, contracts, spread_width, target_profit_pct, rollover_delta, max_rollovers):
    total_pnl = 0
    trades_used = 0
    rollovers_done = 0
    win = False

    while not win and rollovers_done < max_rollovers:
        pnl, trade_count, win = simulate_trade(rollover_delta, contracts, spread_width, target_profit_pct)
        trades_used += trade_count
        total_pnl += pnl
        rollovers_done += 1

    return total_pnl, trades_used, rollovers_done

# -------------------------------
# Monte Carlo Simulation
# -------------------------------
all_final_accounts = []
all_trade_counts = []
all_rollovers = []
all_drawdowns = []
all_wins_before_roll = []
all_wins_after_roll = []

for sim in range(num_simulations):
    collateral = initial_collateral
    trade_counts = []
    rollovers_counts = []
    wins_before = 0
    wins_after = 0
    account_history = [collateral]
    peak = collateral
    drawdown_list = []

    for t in range(num_trades_per_sim):
        pnl, trades_used, win = simulate_trade(entry_delta, main_contracts, spread_width, target_profit_pct)
        trades_used_total = trades_used
        rollovers_done = 0

        if win:
            wins_before += 1
            wins_after += 1
        elif max_rollovers > 0:
            pnl_roll, trades_roll, rollovers_done = simulate_rollover(-pnl, main_contracts, spread_width, target_profit_pct, rollover_delta, max_rollovers)
            pnl += pnl_roll
            trades_used_total += trades_roll
            if pnl > 0:
                wins_after += 1

        collateral += pnl
        trade_counts.append(trades_used_total)
        rollovers_counts.append(rollovers_done)

        peak = max(peak, collateral)
        drawdown_list.append(peak - collateral)
        account_history.append(collateral)

    all_final_accounts.append(collateral)
    all_trade_counts.append(trade_counts)
    all_rollovers.append(rollovers_counts)
    all_drawdowns.append(drawdown_list)
    all_wins_before_roll.append(wins_before)
    all_wins_after_roll.append(wins_after)

# -------------------------------
# Dashboard Metrics
# -------------------------------
st.subheader("Simulation Dashboard Metrics")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Median Final Account ($)", f"{np.median(all_final_accounts):,.0f}")
col2.metric("Best Case Final Account ($)", f"{np.max(all_final_accounts):,.0f}")
col3.metric("Worst Case Final Account ($)", f"{np.min(all_final_accounts):,.0f}")
col4.metric("Avg Total Rollovers", f"{np.mean([sum(rc) for rc in all_rollovers]):.1f}")

col5, col6, col7, col8 = st.columns(4)
col5.metric("Avg Rollovers per Trade", f"{np.mean([np.mean(rc) for rc in all_rollovers]):.2f}")
col6.metric("Max Drawdown ($)", f"{np.max([max(dd) for dd in all_drawdowns]):,.0f}")
col7.metric("Win Rate (Before Rollovers)", f"{np.mean(all_wins_before_roll)/num_trades_per_sim*100:.1f}%")
col8.metric("Win Rate (After Rollovers)", f"{np.mean(all_wins_after_roll)/num_trades_per_sim*100:.1f}%")

# -------------------------------
# Summary Table
# -------------------------------
summary_df = pd.DataFrame({
    'Simulation': range(1, num_simulations + 1),
    'Final Account ($)': all_final_accounts,
    'Total Rollovers': [sum(rc) for rc in all_rollovers],
    'Avg Rollovers per Trade': [np.mean(rc) for rc in all_rollovers],
    'Max Rollovers in Single Trade': [max(rc) for rc in all_rollovers],
    'Total Trades Executed': [sum(tc) for tc in all_trade_counts],
    'Winning Trades (Before Rollovers)': all_wins_before_roll,
    'Winning Trades (After Rollovers)': all_wins_after_roll,
    'Max Drawdown ($)': [max(dd) for dd in all_drawdowns],
})

st.subheader("Simulation Summary Table")
st.dataframe(summary_df.reset_index(drop=True))

# -------------------------------
# Plots
# -------------------------------
st.subheader("Histogram of Final Accounts")
fig_hist = px.histogram(all_final_accounts, nbins=50, labels={'value': 'Final Account ($)'})
st.plotly_chart(fig_hist)

st.subheader("Sample Cumulative Account Value Trajectories")
sample_sim = min(50, num_simulations)
fig_traj = px.line(
    pd.DataFrame([np.cumsum([initial_collateral]+[pnl for pnl in all_final_accounts[:num_trades_per_sim]]) for pnl in all_final_accounts[:sample_sim]]).T,
    labels={'index':'Trade Number', 'value':'Account Value ($)'}
)
st.plotly_chart(fig_traj)

st.subheader("Histogram of Rollovers per Simulation")
fig_roll = px.histogram([sum(rc) for rc in all_rollovers], nbins=20, labels={'value':'Total Rollovers'})
st.plotly_chart(fig_roll)
