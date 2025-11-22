import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
import math

st.set_page_config(page_title="Monte Carlo Credit Spread Simulator", layout="wide")
st.title("Monte Carlo Credit Spread Simulator")

# ---------------- Sidebar Inputs ----------------
st.sidebar.header("Simulation Inputs")

initial_account = st.sidebar.number_input("Initial Account ($)", value=100_000, step=1000, format="%d")
spread_width = st.sidebar.number_input("Spread Width ($)", value=10, step=1)
main_delta = st.sidebar.slider("Main Trade Delta (%)", min_value=20, max_value=90, value=50)
main_qty = st.sidebar.slider("Main Trade Quantity", min_value=1, max_value=100, value=5)
profit_min = st.sidebar.number_input("Min Profit per Contract ($)", min_value=100, max_value=700, value=200)
profit_max = st.sidebar.number_input("Max Profit per Contract ($)", min_value=100, max_value=700, value=400)
max_rollovers = st.sidebar.slider("Max Rollovers per Trade", min_value=0, max_value=10, value=2)
rollover_delta = st.sidebar.slider("Rollover Delta (%)", min_value=20, max_value=90, value=40)
num_trades = st.sidebar.number_input("Number of Trades per Simulation", min_value=10, max_value=200, value=50, step=10)
num_simulations = st.sidebar.number_input("Number of Simulations", min_value=1, max_value=1000, value=50, step=1)
max_contracts_pct = st.sidebar.slider("Max Contracts as % of Account", min_value=10, max_value=100, value=50)
fixed_seed = st.sidebar.checkbox("Use Random Seed", value=True)
seed_val = st.sidebar.number_input("Random Seed", value=42)

# ---------------- Helper Functions ----------------
def simulate_trade(account, delta, qty, spread, profit_min, profit_max):
    """Simulate one credit spread trade"""
    collateral_per_contract = spread * 100
    total_collateral = collateral_per_contract * qty

    # Determine if the trade wins
    prob_success = delta / 100.0
    win = np.random.rand() < prob_success

    if win:
        # Profit per trade now respects qty
        realized_profit = np.random.uniform(profit_min * qty, profit_max * qty)
        loss = 0
        rollover_needed = 0
    else:
        realized_profit = 0
        loss = total_collateral
        rollover_needed = loss

    account += realized_profit - loss
    return account, realized_profit, loss, rollover_needed, win, total_collateral

def simulate_rollover(account, debit_to_cover, spread, delta, max_contracts_allowed, profit_min, profit_max):
    """Simulate a rollover trade that tries to cover previous loss"""
    collateral_per_contract = spread * 100
    credit_per_contract_min = profit_min
    credit_per_contract_max = profit_max

    # determine number of contracts needed to cover debit
    if credit_per_contract_min <= 0:
        qty = max_contracts_allowed
    else:
        qty = int(np.ceil(debit_to_cover / credit_per_contract_min))
    qty = min(qty, max_contracts_allowed)
    qty = max(1, qty)

    total_collateral = collateral_per_contract * qty

    # Determine if rollover wins
    prob_success = delta / 100.0
    win = np.random.rand() < prob_success

    if win:
        realized_profit = np.random.uniform(credit_per_contract_min * qty, credit_per_contract_max * qty)
        loss = 0
    else:
        realized_profit = 0
        loss = total_collateral

    account += realized_profit - loss
    return account, realized_profit, loss, win, qty, total_collateral

# ---------------- Main Simulation ----------------
all_sim_results = []
all_histories = []
all_trade_details = []

if fixed_seed:
    np.random.seed(seed_val)

for sim in range(num_simulations):
    account = float(initial_account)
    account_history = [account]
    total_rollovers = 0
    total_trades = 0
    wins_before = 0
    wins_after = 0
    max_contracts_used = 0
    drawdown = 0
    max_drawdown = 0
    sim_trade_records = []

    for trade_idx in range(num_trades):
        total_trades += 1
        max_contracts_allowed = int((account * (max_contracts_pct / 100.0)) // (spread_width * 100))
        if max_contracts_allowed < 1:
            break

        # simulate main trade
        account, profit, loss, rollover_needed, win, trade_collateral = simulate_trade(
            account, main_delta, main_qty, spread_width, profit_min, profit_max
        )
        account_history.append(account)
        if win:
            wins_before += 1
            wins_after += 1

        rollovers_done = 0
        # handle rollovers
        while rollovers_done < max_rollovers and rollover_needed > 0 and account > 0:
            rollovers_done += 1
            total_rollovers += 1
            account, r_profit, r_loss, r_win, qty_used, r_collateral = simulate_rollover(
                account, rollover_needed, spread_width, rollover_delta, max_contracts_allowed, profit_min, profit_max
            )
            account_history.append(account)
            rollover_needed = r_loss
            if r_win:
                wins_after += 1
                break

        max_contracts_used = max(max_contracts_used, main_qty + rollovers_done)

        peak = max(account_history)
        current_dd = peak - account
        max_drawdown = max(max_drawdown, current_dd)

        # record trade details
        sim_trade_records.append({
            "Simulation": sim + 1,
            "Trade Index": trade_idx + 1,
            "Win": win,
            "Profit": profit,
            "Loss": loss,
            "Rollovers Done": rollovers_done,
            "Main Qty": main_qty,
            "Collateral": trade_collateral,
            "Account After Trade": account,
        })

        if account <= 0:
            break

    all_sim_results.append({
        "Simulation": sim + 1,
        "Final Account": account,
        "Total Rollovers": total_rollovers,
        "Avg Rollovers per Trade": (total_rollovers / float(num_trades)) if num_trades > 0 else 0.0,
        "Max Contracts Used": max_contracts_used,
        "Total Trades": total_trades,
        "Wins Before Roll": wins_before,
        "Wins After Roll": wins_after,
        "Max Drawdown": max_drawdown
    })
    all_histories.append(account_history)
    all_trade_details.extend(sim_trade_records)

# ---------------- Summary DF ----------------
summary_df = pd.DataFrame(all_sim_results)
trade_df = pd.DataFrame(all_trade_details)

# ---------------- Dashboard Metrics ----------------
st.header("Simulation Dashboard Metrics")
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Median Final Account ($)", f"{summary_df['Final Account'].median():,.0f}")
col2.metric("Mean Final Account ($)", f"{summary_df['Final Account'].mean():,.0f}")
col3.metric("Best Final Account ($)", f"{summary_df['Final Account'].max():,.0f}")
col4.metric("Worst Final Account ($)", f"{summary_df['Final Account'].min():,.0f}")
col5.metric("Avg Total Rollovers per Simulation", f"{summary_df['Total Rollovers'].mean():.2f}")
col6.metric("Avg Max Drawdown ($)", f"{summary_df['Max Drawdown'].mean():,.0f}")

st.markdown("---")
st.write("Win rates are counts of main trades (before) and trades that ended up profitable (after rollovers).")
col7, col8 = st.columns(2)
col7.metric("Win Rate (Before Rollovers)", f"{(summary_df['Wins Before Roll'].sum() / (num_simulations * num_trades) * 100) if (num_simulations * num_trades)>0 else 0:.2f}%")
col8.metric("Win Rate (After Rollovers)", f"{(summary_df['Wins After Roll'].sum() / (num_simulations * num_trades) * 100) if (num_simulations * num_trades)>0 else 0:.2f}%")

# ---------------- Plots ----------------
st.header("Simulation Plots")

# Histogram of final accounts
st.subheader("Histogram of Final Accounts")
fig_hist = px.histogram(summary_df, x="Final Account", nbins=40, template="plotly_white",
                        title="Distribution of Final Account Values")
fig_hist.update_layout(margin=dict(t=40, b=20, l=20, r=20))
fig_hist.add_vline(x=initial_account, line_dash="dash", line_color="black", annotation_text="Start account", annotation_position="top left")
st.plotly_chart(fig_hist, use_container_width=True)

# Mean trajectory with percentile bands
st.subheader("Mean account trajectory with 10th-90th percentile band")
max_len = max(len(h) for h in all_histories) if all_histories else 0
hist_array = np.array([h + [h[-1]] * (max_len - len(h)) for h in all_histories])
mean_traj = np.mean(hist_array, axis=0)
p10 = np.percentile(hist_array, 10, axis=0)
p90 = np.percentile(hist_array, 90, axis=0)
x_axis = list(range(0, max_len))
fig_traj = go.Figure()
fig_traj.add_trace(go.Scatter(
    x=x_axis + x_axis[::-1],
    y=list(p90) + list(p10[::-1]),
    fill='toself',
    fillcolor='rgba(173,216,230,0.3)',
    line=dict(color='rgba(255,255,255,0)'),
    hoverinfo="skip",
    showlegend=True,
    name='10-90 percentile'
))
fig_traj.add_trace(go.Scatter(x=x_axis, y=mean_traj, mode='lines', name='Mean trajectory',
                              line=dict(color='royalblue', width=3)))
fig_traj.update_layout(template="plotly_white", xaxis_title="Event index (trade + rollovers points)", yaxis_title="Account Value ($)",
                       margin=dict(t=40, b=20, l=20, r=20), legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
st.plotly_chart(fig_traj, use_container_width=True)

# ---------------- Trade Table per Simulation ----------------
st.header("Trades per Simulation")
sim_choice = st.number_input("Select Simulation Number", min_value=1, max_value=num_simulations, value=1)
filtered_trades = trade_df[trade_df['Simulation'] == sim_choice].reset_index(drop=True)
st.dataframe(filtered_trades)
