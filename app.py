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
target_profit_pct = st.sidebar.slider("Target Profit % of Credit", min_value=10, max_value=50, value=20, step=5)
main_contracts = st.sidebar.selectbox("Main Trade Contracts", [5, 10, 25, 50, 100])
main_delta = st.sidebar.slider("Main Trade Delta", min_value=20, max_value=90, value=50, step=5)
rollover_delta = st.sidebar.slider("Rollover Delta", min_value=20, max_value=90, value=50, step=5)
max_rollovers = st.sidebar.slider("Max Rollovers per Trade", min_value=0, max_value=10, value=3, step=1)

st.sidebar.header("Simulation Settings")
num_trades_per_sim = st.sidebar.number_input("Number of Trades per Simulation", value=50, step=10)
num_simulations = st.sidebar.number_input("Number of Simulations", value=1000, step=100)

# -------------------------------
# Helper Functions
# -------------------------------
def credit_from_delta(delta, spread_width, contracts):
    # Credit = delta/10 * spread * 100 * contracts (as per your logic)
    return delta / 10 * spread_width * 100 * contracts

def simulate_single_trade(delta, contracts, spread_width, target_profit_pct, collateral):
    prob_success = 100 - delta
    credit = credit_from_delta(delta, spread_width, contracts)
    realized_profit = min(credit * target_profit_pct / 100, collateral * target_profit_pct / 100)
    loss_amount = spread_width * 100 * contracts - credit

    success = np.random.rand() * 100 < prob_success
    if success:
        return realized_profit, 1, True  # pnl, trades_used, win
    else:
        return -loss_amount, 1, False

def simulate_rollovers(loss_amount, contracts, spread_width, target_profit_pct, collateral, rollover_delta, max_rollovers):
    total_pnl = 0
    trades_used = 0
    rollovers_done = 0
    win_after_roll = False

    while rollovers_done < max_rollovers and not win_after_roll:
        pnl, trade_count, win = simulate_single_trade(rollover_delta, contracts, spread_width, target_profit_pct, collateral)
        trades_used += trade_count
        total_pnl += pnl
        rollovers_done += 1
        if win:
            win_after_roll = True  # only count if this rollover wins

    return total_pnl, trades_used, rollovers_done, win_after_roll

# -------------------------------
# Monte Carlo Simulation
# -------------------------------
all_final_accounts = []
all_total_rollovers = []
all_total_trades = []
all_wins_before = []
all_wins_after = []
all_max_drawdowns = []

for sim in range(num_simulations):
    collateral = initial_collateral
    account_history = [collateral]
    peak = collateral
    drawdowns = []

    total_rollovers = 0
    total_trades = 0
    wins_before = 0
    wins_after = 0

    for _ in range(num_trades_per_sim):
        pnl, trades_used, win = simulate_single_trade(main_delta, main_contracts, spread_width, target_profit_pct, collateral)
        total_trades += trades_used

        if win:
            wins_before += 1
            wins_after += 1
        elif max_rollovers > 0:
            pnl_roll, trades_roll, rollovers_done, rollover_win = simulate_rollovers(-pnl, main_contracts, spread_width, target_profit_pct, collateral, rollover_delta, max_rollovers)
            pnl += pnl_roll
            total_trades += trades_roll
            total_rollovers += rollovers_done
            if rollover_win:
                wins_after += 1

        collateral += pnl
        account_history.append(collateral)
        peak = max(peak, collateral)
        drawdowns.append(peak - collateral)

    all_final_accounts.append(collateral)
    all_total_rollovers.append(total_rollovers)
    all_total_trades.append(total_trades)
    all_wins_before.append(wins_before)
    all_wins_after.append(wins_after)
    all_max_drawdowns.append(max(drawdowns))

# -------------------------------
# Dashboard Metrics
# -------------------------------
st.subheader("Simulation Dashboard Metrics")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Median Final Account ($)", f"{np.median(all_final_accounts):,.0f}")
col2.metric("Best Case Final Account ($)", f"{np.max(all_final_accounts):,.0f}")
col3.metric("Worst Case Final Account ($)", f"{np.min(all_final_accounts):,.0f}")
col4.metric("Avg Total Rollovers", f"{np.mean(all_total_rollovers):.2f}")

col5, col6, col7, col8 = st.columns(4)
col5.metric("Avg Rollovers per Trade", f"{np.mean(np.array(all_total_rollovers)/num_trades_per_sim):.2f}")
col6.metric("Max Drawdown ($)", f"{np.max(all_max_drawdowns):,.0f}")
col7.metric("Win Rate (Before Rollovers)", f"{np.mean(all_wins_before)/num_trades_per_sim*100:.1f}%")
col8.metric("Win Rate (After Rollovers)", f"{np.mean(all_wins_after)/num_trades_per_sim*100:.1f}%")

# -------------------------------
# Summary Table
# -------------------------------
summary_df = pd.DataFrame({
    'Simulation': range(1, num_simulations+1),
    'Final Account ($)': all_final_accounts,
    'Total Rollovers': all_total_rollovers,
    'Total Trades Executed': all_total_trades,
    'Winning Trades (Before Rollovers)': all_wins_before,
    'Winning Trades (After Rollovers)': all_wins_after,
    'Max Drawdown ($)': all_max_drawdowns,
    'Avg Rollovers per Trade': [x/num_trades_per_sim for x in all_total_rollovers],
})

st.subheader("Simulation Summary Table")
st.dataframe(summary_df.reset_index(drop=True))

# -------------------------------
# Plots
# -------------------------------
st.subheader("Histogram of Final Accounts")
fig_hist = px.histogram(all_final_accounts, nbins=50, labels={'value':'Final Account ($)'})
st.plotly_chart(fig_hist)

st.subheader("Sample Cumulative Account Value Trajectories")
sample_sims = min(50, num_simulations)
fig_traj = px.line(pd.DataFrame([np.cumsum([initial_collateral]+[pnl for pnl in all_final_accounts[:num_trades_per_sim]]) for pnl in all_final_accounts[:sample_sims]]).T,
                   labels={'index':'Trade Number', 'value':'Account Value ($)'})
st.plotly_chart(fig_traj)

st.subheader("Histogram of Rollovers per Simulation")
fig_roll = px.histogram(all_total_rollovers, nbins=20, labels={'value':'Total Rollovers'})
st.plotly_chart(fig_roll)
