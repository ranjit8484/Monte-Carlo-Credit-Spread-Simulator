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
target_profit_min = st.sidebar.number_input("Min Profit per Trade ($)", min_value=50, max_value=700, value=100, step=50)
target_profit_max = st.sidebar.number_input("Max Profit per Trade ($)", min_value=50, max_value=700, value=300, step=50)
max_rollovers = st.sidebar.slider("Max Rollovers per Trade", min_value=0, max_value=10, value=2)
rollover_delta = st.sidebar.slider("Rollover Delta (%)", min_value=20, max_value=90, value=40)
num_trades = st.sidebar.number_input("Number of Trades per Simulation", min_value=10, max_value=200, value=50, step=10)
num_simulations = st.sidebar.number_input("Number of Simulations", min_value=1, max_value=1000, value=50, step=1)
max_contracts_pct = st.sidebar.slider("Max Account Exposure (%)", min_value=10, max_value=100, value=50)
fixed_seed = st.sidebar.checkbox("Use Random Seed", value=True)
seed_val = st.sidebar.number_input("Random Seed", value=42)

# ---------------- Helper Functions ----------------
def simulate_trade(account, delta, qty, spread, target_profit_min, target_profit_max):
    collateral_per_contract = spread * 100
    total_collateral = collateral_per_contract * qty
    theoretical_credit_per_contract = spread * (delta / 100) * 100
    total_credit = theoretical_credit_per_contract * qty
    total_credit = np.clip(total_credit, target_profit_min, target_profit_max)
    credit_per_contract = total_credit / qty
    prob_success = delta / 100.0
    win = np.random.rand() < prob_success
    if win:
        realized_profit = total_credit
        loss = 0.0
        rollover_needed = 0.0
    else:
        loss = total_collateral - total_credit
        realized_profit = 0.0
        rollover_needed = loss
    account += realized_profit - loss
    return account, realized_profit, loss, rollover_needed, win, total_collateral, total_credit, qty

def simulate_rollover(account, debit_to_cover, spread, delta, max_contracts_allowed, target_profit_min, target_profit_max):
    collateral_per_contract = spread * 100
    theoretical_credit_per_contract = spread * (delta / 100) * 100
    needed_qty = int(np.ceil(debit_to_cover / theoretical_credit_per_contract))
    qty = min(needed_qty, max_contracts_allowed)
    qty = max(1, qty)
    total_collateral = qty * collateral_per_contract
    total_credit = theoretical_credit_per_contract * qty
    total_credit = np.clip(total_credit, target_profit_min, target_profit_max)
    prob_success = delta / 100.0
    win = np.random.rand() < prob_success
    if win:
        realized_profit = total_credit
        loss = 0.0
    else:
        realized_profit = 0.0
        loss = total_collateral - total_credit
    account += realized_profit - loss
    return account, realized_profit, loss, win, qty, total_collateral, total_credit

# ---------------- Main Simulation ----------------
if fixed_seed:
    np.random.seed(seed_val)

all_sim_results = []
all_histories = []
all_trade_details = []

for sim in range(int(num_simulations)):
    account = float(initial_account)
    account_history = [account]
    total_rollovers = 0
    total_trades = 0
    max_contracts_used = 0
    wins_before = 0
    wins_after = 0
    sim_trades = []

    for trade_idx in range(int(num_trades)):
        max_contracts_allowed = int((account * (max_contracts_pct / 100.0)) // (spread_width * 100))
        if max_contracts_allowed < 1:
            break
        account, realized_profit, loss, rollover_needed, win, trade_collateral, trade_credit, trade_qty = simulate_trade(
            account, main_delta, main_qty, spread_width, target_profit_min, target_profit_max
        )
        account_history.append(account)
        total_trades += 1
        max_contracts_used = max(max_contracts_used, trade_qty)
        if win:
            wins_before += 1
            wins_after += 1
        else:
            rollovers_done = 0
            outstanding_debit = rollover_needed
            while rollovers_done < max_rollovers and outstanding_debit > 0 and account > 0:
                rollovers_done += 1
                total_rollovers += 1
                max_contracts_allowed_roll = int((account * (max_contracts_pct / 100.0)) // (spread_width * 100))
                max_contracts_allowed_roll = max(1, max_contracts_allowed_roll)
                account, r_profit, r_loss, r_win, qty_used, r_collateral, r_credit = simulate_rollover(
                    account, outstanding_debit, spread_width, rollover_delta, max_contracts_allowed_roll, target_profit_min, target_profit_max
                )
                account_history.append(account)
                outstanding_debit = r_loss
                if r_win:
                    wins_after += 1
                    break

        sim_trades.append({
            "Simulation": sim + 1,
            "Trade Index": trade_idx + 1,
            "Win Before Rollover": win,
            "Profit": realized_profit,
            "Loss": loss,
            "Rollovers Done": rollovers_done,
            "Collateral": trade_collateral,
            "Credit": trade_credit,
            "Account Value": account,
            "Win After Rollover": r_win if not win else win
        })

    all_sim_results.append({
        "Simulation": sim + 1,
        "Final Account": account,
        "Total Rollovers": total_rollovers,
        "Avg Rollovers per Trade": total_rollovers / num_trades if num_trades > 0 else 0,
        "Max Contracts Used": max_contracts_used,
        "Total Trades": total_trades,
        "Wins Before Roll": wins_before,
        "Wins After Roll": wins_after,
    })
    all_histories.append(account_history)
    all_trade_details.extend(sim_trades)

# ---------------- Summary & Dashboard ----------------
summary_df = pd.DataFrame(all_sim_results)
trade_details_df = pd.DataFrame(all_trade_details)

st.header("Simulation Dashboard Metrics")
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Median Final Account ($)", f"{summary_df['Final Account'].median():,.0f}")
col2.metric("Mean Final Account ($)", f"{summary_df['Final Account'].mean():,.0f}")
col3.metric("Best Final Account ($)", f"{summary_df['Final Account'].max():,.0f}")
col4.metric("Worst Final Account ($)", f"{summary_df['Final Account'].min():,.0f}")
col5.metric("Avg Total Rollovers per Simulation", f"{summary_df['Total Rollovers'].mean():.2f}")
col6.metric("Avg Max Drawdown ($)", f"{(summary_df['Final Account'].max() - summary_df['Final Account'].min()):,.0f}")

st.markdown("---")
col7, col8 = st.columns(2)
col7.metric("Win Rate (Before Rollovers)", f"{(summary_df['Wins Before Roll'].sum() / (num_simulations * num_trades) * 100) if (num_simulations * num_trades) > 0 else 0:.2f}%")
col8.metric("Win Rate (After Rollovers)", f"{(summary_df['WinsAfterRoll'].sum() / (num_simulations * num_trades) * 100) if (num_simulations * num_trades) > 0 else 0:.2f}%")

# ---------------- Plots ----------------
st.header("Simulation Plots")

# Histogram of final accounts
fig_hist = px.histogram(summary_df, x="Final Account", nbins=40, template="plotly_white",
                        title="Distribution of Final Account Values")
fig_hist.add_vline(x=initial_account, line_dash="dash", line_color="black",
                   annotation_text="Start account", annotation_position="top left")
st.plotly_chart(fig_hist, use_container_width=True)

# Mean trajectory with 10th-90th percentile band
max_len = max(len(h) for h in all_histories) if all_histories else 0
hist_array = np.array([h + [h[-1]] * (max_len - len(h)) for h in all_histories])
mean_traj = np.mean(hist_array, axis=0)
p10 = np.percentile(hist_array, 10, axis=0)
p90 = np.percentile(hist_array, 90, axis=0)
x_axis = list(range(max_len))

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
fig_traj.update_layout(template="plotly_white", xaxis_title="Event index", yaxis_title="Account Value ($)",
                       margin=dict(t=40, b=20, l=20, r=20), legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
st.plotly_chart(fig_traj, use_container_width=True)

# ---------------- Trade Table per Simulation ----------------
st.header("Detailed Trade Table")
selected_sim = st.selectbox("Select Simulation Number", options=sorted(trade_details_df["Simulation"].unique()))
st.dataframe(trade_details_df[trade_details_df["Simulation"] == selected_sim].reset_index(drop=True))
