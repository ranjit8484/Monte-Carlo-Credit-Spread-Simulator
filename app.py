import streamlit as st
import pandas as pd
import numpy as np
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
main_qty = st.sidebar.slider("Main Trade Quantity", min_value=1, max_value=25, value=5)
target_profit_pct = st.sidebar.slider("Target Profit (% of collateral)", min_value=10, max_value=100, value=50, step=25)
max_loss_per_trade = st.sidebar.slider("Max Loss per Trade ($)", min_value=100, max_value=1000, value=500, step=25)
max_rollovers = st.sidebar.slider("Max Rollovers per Trade", min_value=0, max_value=10, value=3)
rollover_delta = st.sidebar.slider("Rollover Delta (%)", min_value=20, max_value=90, value=40)
num_trades = st.sidebar.number_input("Number of Trades per Simulation", min_value=10, max_value=200, value=50, step=10)
num_simulations = st.sidebar.number_input("Number of Simulations", min_value=1, max_value=1000, value=50, step=1)
max_contracts_pct = st.sidebar.slider("Max Contracts as % of Account", min_value=10, max_value=100, value=50)
fixed_seed = st.sidebar.checkbox("Use Random Seed", value=True)
seed_val = st.sidebar.number_input("Random Seed", value=42)

# ---------------- Helper Functions ----------------
def calc_trade_qty(account, max_loss_per_trade, spread, delta, requested_qty, max_contracts_allowed):
    collateral_per_contract = spread * 100
    credit_per_contract = spread * (delta / 100) * 100
    per_contract_loss = collateral_per_contract - credit_per_contract
    if per_contract_loss <= 0:
        qty_allowed = max_contracts_allowed
    else:
        qty_allowed = int(math.floor(max_loss_per_trade / per_contract_loss))
    qty = min(requested_qty, qty_allowed, max_contracts_allowed)
    qty = max(1, qty)
    return qty, collateral_per_contract, credit_per_contract

def simulate_trade(account, delta, qty, spread, target_profit, max_loss_per_trade, max_contracts_allowed):
    qty, collateral_per_contract, credit_per_contract = calc_trade_qty(account, max_loss_per_trade, spread, delta, qty, max_contracts_allowed)
    total_collateral = qty * collateral_per_contract
    total_credit = qty * credit_per_contract

    prob_success = delta / 100.0
    win = np.random.rand() < prob_success

    if win:
        realized_profit = min(total_credit, total_collateral * target_profit / 100.0)
        loss = 0.0
        rollover_needed = 0.0
    else:
        loss = total_collateral - total_credit
        account -= loss
        rollover_needed = loss
        realized_profit = 0.0

    account += realized_profit
    return account, realized_profit, loss, rollover_needed, win, total_collateral, total_credit, qty

def simulate_rollover(account, debit_to_cover, spread, delta, max_loss_per_trade, max_contracts_allowed):
    qty, collateral_per_contract, credit_per_contract = calc_trade_qty(account, max_loss_per_trade, spread, delta, requested_qty=1, max_contracts_allowed=max_contracts_allowed)
    if debit_to_cover > 0:
        qty = int(math.ceil(debit_to_cover / credit_per_contract))
        qty, collateral_per_contract, credit_per_contract = calc_trade_qty(account, max_loss_per_trade, spread, delta, qty, max_contracts_allowed)
    total_collateral = qty * collateral_per_contract
    total_credit = qty * credit_per_contract

    prob_success = delta / 100.0
    win = np.random.rand() < prob_success

    if win:
        realized_profit = min(total_credit, total_collateral * target_profit_pct / 100.0)
        loss = 0.0
        account += realized_profit
    else:
        loss = total_collateral - total_credit
        account -= loss
        realized_profit = 0.0

    return account, realized_profit, loss, win, qty, total_collateral, total_credit

# ---------------- Main Simulation ----------------
all_sim_results = []
all_histories = []
all_trade_details = []

if fixed_seed:
    np.random.seed(int(seed_val))

for sim in range(int(num_simulations)):
    account = float(initial_account)
    account_history = [account]
    total_rollovers = 0
    total_trades = 0
    max_contracts_used = 0
    wins_before = 0
    wins_after = 0
    drawdown = 0.0
    max_drawdown = 0.0
    trade_number = 0

    for trade_idx in range(int(num_trades)):
        total_trades += 1
        max_contracts_allowed = int((account * (max_contracts_pct / 100.0)) // (spread_width * 100))
        if max_contracts_allowed < 1:
            break

        account, profit, loss, rollover_needed, win, trade_collateral, trade_credit, trade_qty = simulate_trade(
            account, main_delta, main_qty, spread_width, target_profit_pct, max_loss_per_trade, max_contracts_allowed
        )
        trade_number += 1
        trade_id = f"{trade_idx+1}"
        account_history.append(account)
        all_trade_details.append({
            "Simulation": sim + 1,
            "Trade": trade_id,
            "Win": win,
            "Profit": profit,
            "Loss": loss,
            "Rollovers Done": 0,
            "Qty": trade_qty,
            "Collateral": trade_collateral,
            "Credit": trade_credit,
            "Account Value": account,
            "Main Trade": True
        })
        if win:
            wins_before += 1
            wins_after += 1
        else:
            rollovers_done = 0
            outstanding_debit = rollover_needed
            while rollovers_done < max_rollovers and outstanding_debit > 0 and account > 0:
                rollovers_done += 1
                total_rollovers += 1
                trade_number += 1
                account, r_profit, r_loss, r_win, qty_used, r_collateral, r_credit = simulate_rollover(
                    account, outstanding_debit, spread_width, rollover_delta, max_loss_per_trade, max_contracts_allowed
                )
                account_history.append(account)
                trade_id_roll = f"{trade_idx+1}.{rollovers_done}"
                all_trade_details.append({
                    "Simulation": sim + 1,
                    "Trade": trade_id_roll,
                    "Win": r_win,
                    "Profit": r_profit,
                    "Loss": r_loss,
                    "Rollovers Done": rollovers_done,
                    "Qty": qty_used,
                    "Collateral": r_collateral,
                    "Credit": r_credit,
                    "Account Value": account,
                    "Main Trade": False
                })
                outstanding_debit = r_loss
                if r_win:
                    wins_after += 1
                    break

        peak = max(account_history)
        drawdown = max(drawdown, peak - account)
        max_drawdown = max(max_drawdown, peak - account)
        max_contracts_used = max(max_contracts_used, trade_qty + rollovers_done)

        if account <= 0:
            break

    final_account = account
    all_sim_results.append({
        "Simulation": sim + 1,
        "Final Account": final_account,
        "Total Rollovers": total_rollovers,
        "Avg Rollovers per Trade": total_rollovers / float(num_trades),
        "Max Contracts Used": max_contracts_used,
        "Total Trades": total_trades,
        "Wins Before Roll": wins_before,
        "Wins After Roll": wins_after,
        "Max Drawdown": max_drawdown
    })
    all_histories.append(account_history)

# ---------------- Summary DataFrames ----------------
summary_df = pd.DataFrame(all_sim_results)
trades_df = pd.DataFrame(all_trade_details)

# ---------------- Dashboard Metrics ----------------
st.header("Simulation Dashboard Metrics")
col1, col2, col3 = st.columns(3)
col1.metric("Median Final Account ($)", f"{summary_df['Final Account'].median():,.0f}")
col2.metric("Mean Final Account ($)", f"{summary_df['Final Account'].mean():,.0f}")
col3.metric("Best Final Account ($)", f"{summary_df['Final Account'].max():,.0f}")
col1, col2, col3 = st.columns(3)
col1.metric("Worst Final Account ($)", f"{summary_df['Final Account'].min():,.0f}")
col2.metric("Avg Total Rollovers per Simulation", f"{summary_df['Total Rollovers'].mean():.2f}")
col3.metric("Avg Max Drawdown ($)", f"{summary_df['Max Drawdown'].mean():,.0f}")

st.markdown("---")
st.write("Win rates are counts of main trades (before) and trades that ended up profitable (after rollovers).")
col4, col5 = st.columns(2)
col4.metric("Win Rate (Before Rollovers)", f"{(summary_df['Wins Before Roll'].sum() / (num_simulations * num_trades) * 100) if (num_simulations * num_trades)>0 else 0:.2f}%")
col5.metric("Win Rate (After Rollovers)", f"{(summary_df['Wins After Roll'].sum() / (num_simulations * num_trades) * 100) if (num_simulations * num_trades)>0 else 0:.2f}%")

# ---------------- Plots ----------------
st.header("Simulation Plots")
fig_hist = px.histogram(summary_df, x="Final Account", nbins=40, template="plotly_white",
                        title="Distribution of Final Account Values")
fig_hist.update_layout(margin=dict(t=40, b=20, l=20, r=20))
fig_hist.add_vline(x=initial_account, line_dash="dash", line_color="black", annotation_text="Start account", annotation_position="top left")
st.plotly_chart(fig_hist, use_container_width=True)

# Mean trajectory with 10th-90th percentile
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

# Histogram of total rollovers per simulation
st.subheader("Histogram of Total Rollovers per Simulation")
fig_roll = px.histogram(summary_df, x="Total Rollovers", nbins=30, template="plotly_white",
                        title="Total rollovers per simulation")
fig_roll.update_layout(margin=dict(t=40, b=20, l=20, r=20))
st.plotly_chart(fig_roll, use_container_width=True)

# ---------------- Simulation Trade Table ----------------
st.header("Simulation Trade Table")
sim_selected = st.number_input("Select Simulation Number", min_value=1, max_value=int(num_simulations), value=1, step=1)
trades_to_show = trades_df[trades_df['Simulation'] == sim_selected].reset_index(drop=True)
st.dataframe(trades_to_show)
