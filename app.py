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
target_profit = st.sidebar.slider("Target Profit per Trade ($)", min_value=100, max_value=700, step=25, value=200)
max_loss_per_trade = st.sidebar.slider("Max Loss per Trade ($)", min_value=100, max_value=700, step=25, value=500)
max_rollovers = st.sidebar.slider("Max Rollovers per Trade", min_value=0, max_value=10, value=2)
rollover_delta = st.sidebar.slider("Rollover Delta (%)", min_value=20, max_value=90, value=40)
num_trades = st.sidebar.number_input("Number of Trades per Simulation", min_value=10, max_value=200, value=50, step=10)
num_simulations = st.sidebar.number_input("Number of Simulations", min_value=1, max_value=1000, value=50, step=1)
max_contracts_pct = st.sidebar.slider("Max Contracts as % of Account", min_value=10, max_value=50, value=50)
fixed_seed = st.sidebar.checkbox("Use Random Seed", value=True)
seed_val = st.sidebar.number_input("Random Seed", value=42, step=1)

# ---------------- Helper Functions ----------------
def calc_max_loss(delta, spread):
    """Maximum loss per contract based on delta and spread"""
    return spread * 100 * (1 - delta / 100.0)

def simulate_trade(account, delta, qty, spread, max_loss_allowed):
    """Simulate a single credit spread trade"""
    collateral_per_contract = spread * 100
    credit_per_contract = spread * (delta / 100.0) * 100.0
    max_loss_contract = calc_max_loss(delta, spread)

    # Adjust quantity to not exceed max loss per trade
    max_qty_allowed = int(max_loss_allowed / max_loss_contract)
    qty = min(qty, max_qty_allowed) if max_qty_allowed > 0 else 1

    total_collateral = collateral_per_contract * qty
    total_credit = credit_per_contract * qty

    prob_success = delta / 100.0
    win = np.random.rand() < prob_success

    if win:
        trade_pl = total_credit
        loss = 0.0
        rollover_needed = 0.0
    else:
        trade_pl = - (total_collateral - total_credit)
        loss = total_collateral - total_credit
        rollover_needed = loss

    return account + trade_pl, trade_pl, loss, rollover_needed, win, total_collateral, total_credit, qty

def simulate_rollover(account, debit_to_cover, spread, delta, max_loss_allowed, max_contracts_allowed):
    """Simulate a rollover trade to recover previous loss"""
    collateral_per_contract = spread * 100
    credit_per_contract = spread * (delta / 100.0) * 100.0
    max_loss_contract = calc_max_loss(delta, spread)

    # Determine qty needed to cover remaining loss
    needed_qty = int(np.ceil(debit_to_cover / credit_per_contract))
    qty = min(needed_qty, max_contracts_allowed)

    # Respect max loss per trade
    max_qty_allowed = int(max_loss_allowed / max_loss_contract)
    qty = min(qty, max_qty_allowed) if max_qty_allowed > 0 else 1

    total_collateral = collateral_per_contract * qty
    total_credit = credit_per_contract * qty
    prob_success = delta / 100.0
    win = np.random.rand() < prob_success

    if win:
        trade_pl = total_credit
        loss = 0.0
    else:
        trade_pl = - (total_collateral - total_credit)
        loss = total_collateral - total_credit

    return account + trade_pl, trade_pl, loss, win, qty, total_collateral, total_credit

# ---------------- Main Simulation ----------------
all_sim_results = []
all_histories = []
all_trade_records = []

if fixed_seed:
    np.random.seed(seed_val)

for sim in range(int(num_simulations)):
    account = float(initial_account)
    account_history = [account]
    total_rollovers = 0
    total_trades = 0
    max_contracts_used = 0
    wins_before = 0
    wins_after = 0
    max_drawdown = 0.0

    for trade_idx in range(int(num_trades)):
        total_trades += 1
        max_contracts_allowed = int((account * max_contracts_pct / 100.0) // (spread_width * 100))
        if max_contracts_allowed < 1:
            break

        account, trade_pl, loss, rollover_needed, win, trade_collateral, trade_credit, trade_qty = simulate_trade(
            account, main_delta, main_qty, spread_width, max_loss_per_trade
        )
        account_history.append(account)
        rollovers_done = 0
        if win:
            wins_before += 1
            wins_after += 1
        else:
            # Rollovers to recover loss
            remaining_loss = rollover_needed
            rollover_count = 0
            while rollover_count < max_rollovers and remaining_loss > 0 and account > 0:
                rollover_count += 1
                total_rollovers += 1
                account, r_pl, r_loss, r_win, r_qty, r_collateral, r_credit = simulate_rollover(
                    account, remaining_loss, spread_width, rollover_delta, max_loss_per_trade, max_contracts_allowed
                )
                account_history.append(account)
                rollovers_done += 1
                remaining_loss = max(0, remaining_loss - r_pl)
                if r_win:
                    wins_after += 1
                    break
                # record rollover as sub-trade
                all_trade_records.append({
                    "Simulation": sim + 1,
                    "Trade #": f"{trade_idx + 1}.{rollover_count}",
                    "Rollover": True,
                    "Win": r_win,
                    "Trade P/L": r_pl,
                    "# of Rollovers Done": rollovers_done,
                    "Quantity": r_qty,
                    "Collateral": r_collateral,
                    "Credit": r_credit,
                    "Account": account
                })

        max_contracts_used = max(max_contracts_used, trade_qty + rollovers_done)
        peak = max(account_history)
        current_dd = peak - account
        max_drawdown = max(max_drawdown, current_dd)

        # record main trade
        all_trade_records.append({
            "Simulation": sim + 1,
            "Trade #": trade_idx + 1,
            "Rollover": False,
            "Win": win,
            "Trade P/L": trade_pl,
            "# of Rollovers Done": rollovers_done,
            "Quantity": trade_qty,
            "Collateral": trade_collateral,
            "Credit": trade_credit,
            "Account": account
        })

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

# ---------------- Summary Table ----------------
summary_df = pd.DataFrame(all_sim_results)
trade_df = pd.DataFrame(all_trade_records)

# ---------------- Dashboard Metrics ----------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Median Final Account ($)", f"{summary_df['Final Account'].median():,.0f}")
col2.metric("Mean Final Account ($)", f"{summary_df['Final Account'].mean():,.0f}")
col3.metric("Best Final Account ($)", f"{summary_df['Final Account'].max():,.0f}")
col4.metric("Worst Final Account ($)", f"{summary_df['Final Account'].min():,.0f}")

col5, col6 = st.columns(2)
col5.metric("Avg Total Rollovers per Simulation", f"{summary_df['Total Rollovers'].mean():.2f}")
col6.metric("Avg Max Drawdown ($)", f"{summary_df['Max Drawdown'].mean():,.0f}")

st.markdown("---")
st.write("Win rates are counts of main trades (before) and trades that ended up profitable (after rollovers).")
col7, col8 = st.columns(2)
col7.metric("Win Rate (Before Rollovers)", f"{(summary_df['Wins Before Roll'].sum() / (num_simulations * num_trades) * 100) if (num_simulations * num_trades) > 0 else 0:.2f}%")
col8.metric("Win Rate (After Rollovers)", f"{(summary_df['Wins After Roll'].sum() / (num_simulations * num_trades) * 100) if (num_simulations * num_trades) > 0 else 0:.2f}%")

# ---------------- Plots ----------------
st.header("Simulation Plots")
fig_hist = px.histogram(summary_df, x="Final Account", nbins=40, template="plotly_white",
                        title="Distribution of Final Account Values")
fig_hist.update_layout(margin=dict(t=40, b=20, l=20, r=20))
fig_hist.add_vline(x=initial_account, line_dash="dash", line_color="black", annotation_text="Start account", annotation_position="top left")
st.plotly_chart(fig_hist, use_container_width=True)

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
fig_traj.update_layout(template="plotly_white", xaxis_title="Event index", yaxis_title="Account Value ($)",
                       margin=dict(t=40, b=20, l=20, r=20), legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
st.plotly_chart(fig_traj, use_container_width=True)

# ---------------- Trade Table ----------------
st.header("Trade-by-Trade Simulation Table")
selected_sim = st.number_input("Select Simulation Number", min_value=1, max_value=int(num_simulations), value=1, step=1)
sim_trade_df = trade_df[trade_df["Simulation"] == selected_sim].reset_index(drop=True)

# Highlight wins/losses
def highlight_win_loss(row):
    color = []
    for val, win in zip(row, row['Win'] if 'Win' in row else [True]):
        if row['Trade P/L'] < 0:
            color.append('background-color: #ffcccc')  # light red
        else:
            color.append('background-color: #ccffcc')  # light green
    return color

st.dataframe(sim_trade_df)
