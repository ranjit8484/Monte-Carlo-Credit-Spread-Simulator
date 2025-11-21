# app.py
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="Monte Carlo Credit Spread Simulator", layout="wide")

# ---------------- Sidebar Inputs ----------------
st.sidebar.header("Simulation Inputs")

initial_account = st.sidebar.number_input("Initial Account ($)", value=100_000, step=1000)
spread_width = st.sidebar.number_input("Spread Width ($)", value=10, step=1)
main_delta = st.sidebar.slider("Main Trade Delta (%)", min_value=20, max_value=90, value=50)
main_qty = st.sidebar.slider("Main Trade Quantity", min_value=1, max_value=100, value=5)
target_profit_pct = st.sidebar.slider("Target Profit (% of collateral)", min_value=10, max_value=100, value=50)
max_rollovers = st.sidebar.slider("Max Rollovers per Trade", min_value=0, max_value=10, value=3)
rollover_mode = st.sidebar.selectbox("Rollover Sizing Mode", ["Cover Debit on Open", "Scale by Multiplier"])
rollover_multiplier = st.sidebar.selectbox("Rollover Multiplier", [1.0, 1.25, 1.5], index=1)
rollover_delta = st.sidebar.slider("Rollover Delta (%)", min_value=20, max_value=90, value=40)
num_trades = st.sidebar.number_input("Number of Trades per Simulation", min_value=10, max_value=200, value=50, step=10)
num_simulations = st.sidebar.number_input("Number of Simulations", min_value=1, max_value=50, value=5)
max_contracts_pct = st.sidebar.slider("Max Contracts as % of Account", min_value=10, max_value=100, value=90)
fixed_seed = st.sidebar.checkbox("Use Random Seed", value=True)
seed_val = st.sidebar.number_input("Random Seed", value=42)

# ---------------- Helper Functions ----------------
def simulate_trade(account, delta, qty, spread, target_profit):
    """Simulate one credit spread trade"""
    collateral_per_contract = spread * 100
    total_collateral = collateral_per_contract * qty
    credit_per_contract = spread * (delta / 100) * 100
    total_credit = credit_per_contract * qty

    prob_success = delta / 100
    win = np.random.rand() < prob_success

    if win:
        # Realized profit is capped by target profit % of collateral
        realized_profit = min(total_credit, total_collateral * target_profit / 100)
        account += realized_profit
        loss = 0
        rollover_needed = 0
    else:
        loss = total_collateral - total_credit
        account -= loss
        rollover_needed = loss  # Amount to cover in rollover
        realized_profit = 0

    return account, realized_profit, loss, rollover_needed, win, total_collateral, total_credit

def simulate_rollover(account, debit_to_cover, spread, delta, qty_multiplier, max_contracts_allowed, target_profit):
    """Simulate a rollover trade (non-martingale)"""
    collateral_per_contract = spread * 100
    credit_per_contract = spread * (delta / 100) * 100

    # Determine rollover quantity
    needed_qty = int(np.ceil(debit_to_cover / credit_per_contract))
    qty = min(int(needed_qty * qty_multiplier), max_contracts_allowed)
    total_collateral = qty * collateral_per_contract
    total_credit = qty * credit_per_contract

    prob_success = delta / 100
    win = np.random.rand() < prob_success

    if win:
        # Realized profit capped by target profit
        realized_profit = min(total_credit, total_collateral * target_profit / 100)
        account += realized_profit
        loss = 0
    else:
        loss = total_collateral - total_credit
        account -= loss
        realized_profit = 0

    return account, realized_profit, loss, win, qty, total_collateral, total_credit

# ---------------- Main Simulation ----------------
all_sim_results = []

if fixed_seed:
    np.random.seed(seed_val)

for sim in range(num_simulations):
    account = initial_account
    account_history = [account]
    total_rollovers = 0
    total_trades = 0
    max_contracts_used = 0
    wins_before = 0
    wins_after = 0
    drawdown = 0

    for trade_idx in range(num_trades):
        total_trades += 1
        max_contracts_allowed = int((account * max_contracts_pct / 100) // (spread_width * 100))
        account, realized_profit, loss, rollover_needed, win, trade_collateral, trade_credit = simulate_trade(
            account, main_delta, main_qty, spread_width, target_profit_pct
        )
        account_history.append(account)
        if win:
            wins_before += 1
        else:
            # handle rollovers
            rollovers_done = 0
            while rollovers_done < max_rollovers and rollover_needed > 0:
                rollovers_done += 1
                total_rollovers += 1
                account, r_profit, r_loss, r_win, qty_used, r_collateral, r_credit = simulate_rollover(
                    account, rollover_needed, spread_width, rollover_delta, rollover_multiplier, max_contracts_allowed, target_profit_pct
                )
                account_history.append(account)
                rollover_needed = r_loss
                if r_win:
                    wins_after += 1
                    break

        max_contracts_used = max(max_contracts_used, main_qty + total_rollovers)

        # Track drawdown
        peak = max(account_history)
        drawdown = max(drawdown, peak - account)

    all_sim_results.append({
        "Simulation": sim + 1,
        "Final Account": account,
        "Total Rollovers": total_rollovers,
        "Avg Rollovers per Trade": total_rollovers / num_trades,
        "Max Contracts Used": max_contracts_used,
        "Total Trades": total_trades,
        "Wins Before Roll": wins_before,
        "Wins After Roll": wins_after,
        "Max Drawdown": drawdown
    })

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

# ---------------- Plots ----------------
st.header("Simulation Plots")

# Histogram of final accounts
st.subheader("Histogram of Final Accounts")
fig, ax = plt.subplots()
ax.hist(summary_df['Final Account'], bins=20, color='skyblue', edgecolor='black')
ax.set_xlabel("Final Account ($)")
ax.set_ylabel("Frequency")
st.pyplot(fig)

# Sample cumulative account trajectories
st.subheader("Sample Cumulative Account Value Trajectories")
fig2, ax2 = plt.subplots()
for i in range(min(num_simulations, 10)):
    ax2.plot(range(len(summary_df)), summary_df['Final Account'], alpha=0.6)
ax2.set_xlabel("Trade Index")
ax2.set_ylabel("Account Value ($)")
st.pyplot(fig2)

# Histogram of rollovers per simulation
st.subheader("Histogram of Rollovers per Simulation")
fig3, ax3 = plt.subplots()
ax3.hist(summary_df['Total Rollovers'], bins=20, color='lightgreen', edgecolor='black')
ax3.set_xlabel("Total Rollovers")
ax3.set_ylabel("Frequency")
st.pyplot(fig3)

# ---------------- Summary Table ----------------
st.header("Simulation Summary Table")
st.dataframe(summary_df.reset_index(drop=True))

