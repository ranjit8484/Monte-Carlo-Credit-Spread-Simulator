# app.py
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
main_qty = st.sidebar.slider("Main Trade Quantity", min_value=1, max_value=100, value=5)
target_profit_pct = st.sidebar.slider("Target Profit (% of collateral)", min_value=10, max_value=100, value=50)
max_rollovers = st.sidebar.slider("Max Rollovers per Trade", min_value=0, max_value=10, value=3)
rollover_mode = st.sidebar.selectbox("Rollover Sizing Mode", ["Cover Debit on Open", "Scale by Multiplier"])
rollover_multiplier = float(st.sidebar.selectbox("Rollover Multiplier", [1.0, 1.25, 1.5], index=1))
rollover_delta = st.sidebar.slider("Rollover Delta (%)", min_value=20, max_value=90, value=40)
num_trades = st.sidebar.number_input("Number of Trades per Simulation", min_value=10, max_value=200, value=50, step=10)
num_simulations = st.sidebar.number_input("Number of Simulations", min_value=1, max_value=200, value=50, step=1)
max_contracts_pct = st.sidebar.slider("Max Contracts as % of Account", min_value=10, max_value=100, value=90)
use_seed = st.sidebar.checkbox("Use Random Seed", value=True)
seed_val = int(st.sidebar.number_input("Random Seed", value=42))

# ---------------- Helper Functions ----------------
def simulate_trade(account, delta, qty, spread, target_profit):
    """Simulate one credit spread trade (user's logic)"""
    collateral_per_contract = spread * 100
    total_collateral = collateral_per_contract * qty
    credit_per_contract = spread * (delta / 100) * 100
    total_credit = credit_per_contract * qty

    # Note: your code used prob_success = delta / 100
    prob_success = delta / 100.0
    win = np.random.rand() < prob_success

    if win:
        # Realized profit is capped by target profit % of collateral
        realized_profit = min(total_credit, total_collateral * target_profit / 100.0)
        account += realized_profit
        loss = 0.0
        rollover_needed = 0.0
    else:
        loss = total_collateral - total_credit
        account -= loss
        rollover_needed = loss  # Amount to cover in rollover
        realized_profit = 0.0

    return account, realized_profit, loss, rollover_needed, win, total_collateral, total_credit

def simulate_rollover(account, debit_to_cover, spread, delta, qty_multiplier, max_contracts_allowed, target_profit):
    """Simulate a single rollover trade using user's logic"""
    collateral_per_contract = spread * 100
    credit_per_contract = spread * (delta / 100.0) * 100.0

    # If credit_per_contract is zero (shouldn't happen), ensure we don't divide by zero
    if credit_per_contract <= 0:
        needed_qty = max_contracts_allowed
    else:
        needed_qty = int(math.ceil(debit_to_cover / credit_per_contract))

    qty = int(min(int(round(needed_qty * qty_multiplier)), max_contracts_allowed))
    qty = max(1, qty)  # ensure at least 1

    total_collateral = qty * collateral_per_contract
    total_credit = qty * credit_per_contract

    prob_success = delta / 100.0
    win = np.random.rand() < prob_success

    if win:
        # realized profit capped by target profit
        realized_profit = min(total_credit, total_collateral * target_profit / 100.0)
        account += realized_profit
        loss = 0.0
    else:
        loss = total_collateral - total_credit
        account -= loss
        realized_profit = 0.0

    return account, realized_profit, loss, win, qty, total_collateral, total_credit

# ---------------- Main Simulation ----------------
# prepare storage
all_sim_results = []
all_histories = []  # store account_history for each simulation (to plot mean + percentiles)

if use_seed:
    np.random.seed(seed_val)

for sim in range(int(num_simulations)):
    account = float(initial_account)
    account_history = [account]  # include starting account
    total_rollovers = 0
    total_trades = 0
    max_contracts_used = 0
    wins_before = 0
    wins_after = 0
    max_drawdown = 0.0

    for trade_idx in range(int(num_trades)):
        total_trades += 1

        # compute how many contracts we can support given exposure limit
        max_contracts_allowed = int((account * (max_contracts_pct / 100.0)) // (spread_width * 100))
        if max_contracts_allowed < 1:
            # can't open any contract under exposure rules; treat as forced stop for this sim
            # append current account history and break
            break

        # simulate main trade
        account, realized_profit, loss, rollover_needed, win, trade_collateral, trade_credit = simulate_trade(
            account, main_delta, main_qty, spread_width, target_profit_pct
        )
        account_history.append(account)
        if win:
            wins_before += 1
            wins_after += 1
        else:
            # handle rollovers up to max_rollovers
            rollovers_done = 0
            outstanding_debit = rollover_needed
            while rollovers_done < max_rollovers and outstanding_debit > 0 and account > 0:
                rollovers_done += 1
                total_rollovers += 1

                # determine qty multiplier based on rollover_mode
                if rollover_mode == "Cover Debit on Open":
                    qty_multiplier = 1.0  # we'll compute needed_qty directly in simulate_rollover
                else:
                    qty_multiplier = rollover_multiplier

                account, r_profit, r_loss, r_win, qty_used, r_collateral, r_credit = simulate_rollover(
                    account, outstanding_debit, spread_width, rollover_delta, qty_multiplier, max_contracts_allowed, target_profit_pct
                )

                account_history.append(account)
                outstanding_debit = r_loss  # if rollover lost, r_loss becomes new debit-to-cover
                if r_win:
                    wins_after += 1
                    break

            # end while rollovers

        max_contracts_used = max(max_contracts_used, main_qty + total_rollovers)

        # update drawdown
        peak = max(account_history)
        current_dd = peak - account
        max_drawdown = max(max_drawdown, current_dd)

        # Safety stop: if account depleted, break
        if account <= 0:
            break

    # finish sim
    final_account = account
    all_sim_results.append({
        "Simulation": sim + 1,
        "Final Account": final_account,
        "Total Rollovers": total_rollovers,
        "Avg Rollovers per Trade": (total_rollovers / float(num_trades)) if num_trades > 0 else 0.0,
        "Max Contracts Used": max_contracts_used,
        "Total Trades": total_trades,
        "Wins Before Roll": wins_before,
        "Wins After Roll": wins_after,
        "Max Drawdown": max_drawdown
    })
    all_histories.append(account_history)

# create summary_df (index hidden on display)
summary_df = pd.DataFrame(all_sim_results)

# ---------------- Dashboard Metrics ----------------
st.header("Simulation Dashboard Metrics")
col1, col2, col3 = st.columns(3)
col1.metric("Median Final Account ($)", f"{summary_df['Final Account'].median():,.0f}")
col2.metric("Mean Final Account ($)", f"{summary_df['Final Account'].mean():,.0f}")
col3.metric("Best Final Account ($)", f"{summary_df['Final Account'].max():,.0f}")

col4, col5, col6 = st.columns(3)
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

# 1) Histogram of final accounts (Plotly)
st.subheader("Histogram of Final Accounts")
fig_hist = px.histogram(summary_df, x="Final Account", nbins=40, template="plotly_white",
                        title="Distribution of Final Account Values")
fig_hist.update_layout(margin=dict(t=40, b=20, l=20, r=20))
fig_hist.add_vline(x=initial_account, line_dash="dash", line_color="black", annotation_text="Start account", annotation_position="top left")
st.plotly_chart(fig_hist, use_container_width=True)

# 2) Mean trajectory with 10th-90th percentile band
st.subheader("Mean account trajectory with 10th-90th percentile band")

# normalize histories to equal length by padding the shorter ones with their final value
max_len = max(len(h) for h in all_histories) if all_histories else 0
hist_array = np.array([h + [h[-1]] * (max_len - len(h)) for h in all_histories])  # shape: (nsim, max_len)

# compute mean and percentile bands along axis 0
mean_traj = np.mean(hist_array, axis=0)
p10 = np.percentile(hist_array, 10, axis=0)
p90 = np.percentile(hist_array, 90, axis=0)
x_axis = list(range(0, max_len))  # trade indices (0 = start account)

fig_traj = go.Figure()
# percentile band
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
# mean line
fig_traj.add_trace(go.Scatter(x=x_axis, y=mean_traj, mode='lines', name='Mean trajectory',
                              line=dict(color='royalblue', width=3)))
fig_traj.update_layout(template="plotly_white", xaxis_title="Event index (trade + rollovers points)", yaxis_title="Account Value ($)",
                       margin=dict(t=40, b=20, l=20, r=20), legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
st.plotly_chart(fig_traj, use_container_width=True)

# 3) Histogram of total rollovers per simulation
st.subheader("Histogram of Total Rollovers per Simulation")
fig_roll = px.histogram(summary_df, x="Total Rollovers", nbins=30, template="plotly_white",
                        title="Total rollovers per simulation")
fig_roll.update_layout(margin=dict(t=40, b=20, l=20, r=20))
st.plotly_chart(fig_roll, use_container_width=True)

# ---------------- Summary Table ----------------
st.header("Simulation Summary Table")
st.dataframe(summary_df.reset_index(drop=True))
