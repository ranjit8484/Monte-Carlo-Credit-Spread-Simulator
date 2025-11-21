# app.py
import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px
import math

st.set_page_config(page_title="Monte Carlo Credit Spread Simulator", layout="wide")
st.title("Monte Carlo Credit Spread Simulator (No-Debit Rollover Logic)")

# ---------------------------
# Sidebar - Inputs
# ---------------------------
st.sidebar.header("Portfolio & Trade Settings")
initial_account = st.sidebar.number_input("Initial account ($)", value=100000, step=1000)
spread_width = st.sidebar.selectbox("Spread width ($)", [5, 10, 25, 50, 100], index=1)
main_contracts = st.sidebar.selectbox("Main trade contracts (qty)", [5, 10, 20, 25, 50, 100], index=1)
main_delta = st.sidebar.slider("Main trade delta (20-90)", min_value=20, max_value=90, value=50, step=5)

st.sidebar.markdown("----")
st.sidebar.header("Profit / Loss rules")
target_profit_pct = st.sidebar.slider("Target profit (% of trade collateral)", min_value=5, max_value=50, value=20, step=5)
st.sidebar.markdown("Profit on a win = min(total credit, target% * trade collateral)")

st.sidebar.markdown("----")
st.sidebar.header("Rollover settings")
rollover_delta = st.sidebar.slider("Rollover delta (20-90)", min_value=20, max_value=90, value=40, step=5)
max_rollovers = st.sidebar.slider("Max rollovers per trade", min_value=0, max_value=10, value=3, step=1)
max_exposure_pct = st.sidebar.slider("Max collateral exposure (% of account)", 10, 100, 90, step=5) / 100.0
st.sidebar.markdown("Rollover sized so new credit >= debit-to-close if possible under exposure limit")

st.sidebar.markdown("----")
st.sidebar.header("Simulation settings")
trades_per_sim = st.sidebar.number_input("Trades per simulation", value=50, min_value=1, step=1)
num_simulations = st.sidebar.number_input("Number of simulations", value=1000, min_value=1, step=50)
seed = st.sidebar.number_input("Random seed (0 = random)", value=0, min_value=0)
if seed != 0:
    np.random.seed(seed)

# ---------------------------
# Helper math functions
# ---------------------------
CONTRACT_SIZE = 100

def credit_per_contract(delta: int, spread: float) -> float:
    """Credit per option contract in dollars using your convention:
       credit per share = (delta / 100) * spread
       so credit per contract = credit per share * 100
    """
    credit_per_share = (delta / 100.0) * spread
    return credit_per_share * CONTRACT_SIZE

def collateral_per_contract(spread: float) -> float:
    """Collateral (max risk) per contract = spread * 100"""
    return spread * CONTRACT_SIZE

def loss_per_contract(spread: float, delta: int) -> float:
    """Loss per contract if trade ends ITM = collateral - credit"""
    return collateral_per_contract(spread) - credit_per_contract(delta, spread)

def realized_profit_on_win(spread: float, contracts: int, delta: int, target_pct: float) -> float:
    """Profit realized on a winning trade (min of credit and target% of trade collateral)"""
    total_credit = credit_per_contract(delta, spread) * contracts
    trade_collateral = collateral_per_contract(spread) * contracts
    target_profit = trade_collateral * (target_pct / 100.0)
    return min(total_credit, target_profit)

# ---------------------------
# Core simulation functions
# ---------------------------
def simulate_one_main_trade(account: float, spread: float, contracts: int, delta: int, target_pct: float,
                            rollover_delta: int, max_rolls: int, max_exposure: float):
    """
    Simulate one main trade and its rollovers using the 'no-debit' rollover rule.
    Returns:
      account_after: updated account balance after the trade and any rollovers
      trades_used: number of executed trades including rollovers
      rollovers_used: number of rollovers executed
      win_before: bool (won at main leg)
      win_after: bool (won at main or any rollover)
      max_contracts_used: peak contracts used in the sequence (for exposure tracking)
      drawdown_points: list of intermediate account values (for drawdown tracking)
    """
    drawdown_points = []
    max_contracts_used = contracts

    # MAIN TRADE
    # compute credit, collateral, loss per contract
    c_credit = credit_per_contract(delta, spread)
    c_collateral = collateral_per_contract(spread)
    c_loss = c_collateral - c_credit

    # simulate main trade
    prob_win_main = 100 - delta
    win_main = np.random.rand() * 100 < prob_win_main
    trades_used = 1
    rollovers_used = 0
    win_after = False

    if win_main:
        pnl = realized_profit_on_win(spread, contracts, delta, target_pct)
        account_after = account + pnl
        win_before = True
        win_after = True
        drawdown_points.append(account_after)
        return account_after, trades_used, rollovers_used, win_before, win_after, max_contracts_used, drawdown_points

    # MAIN TRADE LOST: realize loss now
    loss_amount = c_loss * contracts
    account_after = account - loss_amount
    win_before = False
    drawdown_points.append(account_after)

    # Now attempt rollovers up to max_rolls
    outstanding_debit_to_close = loss_amount  # this is what you paid to close the failed main trade
    current_account = account_after
    current_contracts = contracts

    for r in range(max_rolls):
        # Determine credit per contract for rollover delta
        roll_credit_per_contract = credit_per_contract(rollover_delta, spread)
        roll_collateral_per_contract = collateral_per_contract(spread)
        # compute minimum contracts to get credit >= outstanding_debit_to_close
        if roll_credit_per_contract <= 0:
            # degenerate; cannot collect credit
            break
        needed_contracts = math.ceil(outstanding_debit_to_close / roll_credit_per_contract)
        needed_contracts = max(1, needed_contracts)

        # check exposure: ensure required collateral <= account * max_exposure
        required_collateral = needed_contracts * roll_collateral_per_contract
        max_allowed_collateral = current_account * max_exposure
        if required_collateral > max_allowed_collateral:
            # reduce contracts to max allowed (floor)
            max_allowed_contracts = int(math.floor(max_allowed_collateral / roll_collateral_per_contract))
            if max_allowed_contracts < 1:
                # cannot open rollover due to exposure limits
                break
            needed_contracts = max_allowed_contracts
            required_collateral = needed_contracts * roll_collateral_per_contract

        # track peak contracts used
        max_contracts_used = max(max_contracts_used, needed_contracts)

        # simulate opening this rollover: NOTE we do NOT add credit immediately to account
        # we will settle P&L only once rollover resolves (win or loss) to keep accounting consistent
        # trades used increments
        trades_used += 1
        rollovers_used += 1

        # simulate rollover outcome
        prob_win_roll = 100 - rollover_delta
        win_roll = np.random.rand() * 100 < prob_win_roll

        if win_roll:
            # On a rollover win, realized profit is:
            pnl_roll = realized_profit_on_win(spread, needed_contracts, rollover_delta, target_pct)
            # account increases by pnl_roll
            current_account = current_account + pnl_roll
            # after this win, we consider the trade "won after rollovers"
            win_after = True
            drawdown_points.append(current_account)
            # stop rolling
            break
        else:
            # rollover lost, realize its loss
            loss_roll = (roll_collateral_per_contract - roll_credit_per_contract) * needed_contracts
            current_account = current_account - loss_roll
            # outstanding_debit_to_close becomes this loss (for next round you will size accordingly)
            outstanding_debit_to_close = loss_roll
            drawdown_points.append(current_account)
            # continue to next rollover attempt (if any)

    return current_account, trades_used, rollovers_used, win_before, win_after, max_contracts_used, drawdown_points

# ---------------------------
# Run Monte Carlo
# ---------------------------
# Storage arrays
final_accounts = []
total_rollovers_per_sim = []
total_trades_per_sim = []
wins_before_list = []
wins_after_list = []
max_drawdowns = []
max_contracts_seen_list = []

# progress feedback
with st.spinner("Running Monte Carlo simulations... this may take a moment"):
    for sim in range(int(num_simulations)):
        account = float(initial_account)
        account_history_for_draw = [account]
        total_rolls = 0
        total_trades = 0
        wins_before = 0
        wins_after = 0
        max_contracts_seen = 0

        for t in range(int(trades_per_sim)):
            account_before = account
            (account,
             trades_used,
             rollovers_used,
             win_before,
             win_after,
             max_contracts_used,
             drawdown_points) = simulate_one_main_trade(
                account,
                spread_width,
                main_contracts,
                main_delta,
                target_profit_pct,
                rollover_delta,
                max_rollovers,
                max_exposure_pct
            )

            total_trades += trades_used
            total_rolls += rollovers_used
            wins_before += 1 if win_before else 0
            wins_after += 1 if win_after else 0
            max_contracts_seen = max(max_contracts_seen, max_contracts_used)

            # Append intermediate drawdown points to account history for accurate dd calc
            # drawdown_points includes the new account after main and after rollovers
            account_history_for_draw.extend(drawdown_points)

            # Safety: if account <= 0, stop early
            if account <= 0:
                # record remaining trades as not executed
                break

        # compute max drawdown for this sim
        peaks = []
        peak = account_history_for_draw[0]
        max_dd = 0.0
        for val in account_history_for_draw:
            peak = max(peak, val)
            dd = peak - val
            if dd > max_dd:
                max_dd = dd

        final_accounts.append(account)
        total_rollovers_per_sim.append(total_rolls)
        total_trades_per_sim.append(total_trades)
        wins_before_list.append(wins_before)
        wins_after_list.append(wins_after)
        max_drawdowns.append(max_dd)
        max_contracts_seen_list.append(max_contracts_seen)

# ---------------------------
# Dashboard metrics
# ---------------------------
st.subheader("Simulation Dashboard Metrics")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Median final account ($)", f"{np.median(final_accounts):,.0f}")
col2.metric("Mean final account ($)", f"{np.mean(final_accounts):,.0f}")
col3.metric("Best final account ($)", f"{np.max(final_accounts):,.0f}")
col4.metric("Worst final account ($)", f"{np.min(final_accounts):,.0f}")

col5, col6, col7, col8 = st.columns(4)
col5.metric("Avg total rollovers per sim", f"{np.mean(total_rollovers_per_sim):.2f}")
col6.metric("Avg rollovers per trade", f"{np.mean(np.array(total_rollovers_per_sim) / trades_per_sim):.3f}")
col7.metric("Avg max drawdown ($)", f"{np.mean(max_drawdowns):,.0f}")
col8.metric("Avg max contracts used", f"{np.mean(max_contracts_seen_list):.1f}")

st.markdown("---")
st.write("Win rates are counts of main trades (before) and trades that ended up profitable (after rollovers).")
col9, col10 = st.columns(2)
col9.metric("Win rate before rollovers", f"{np.mean(np.array(wins_before_list) / trades_per_sim) * 100:.2f}%")
col10.metric("Win rate after rollovers", f"{np.mean(np.array(wins_after_list) / trades_per_sim) * 100:.2f}%")

# ---------------------------
# Summary table
# ---------------------------
summary_df = pd.DataFrame({
    "Simulation": range(1, len(final_accounts) + 1),
    "Final Account ($)": final_accounts,
    "Total Rollovers": total_rollovers_per_sim,
    "Avg Rollovers per Trade": list(np.array(total_rollovers_per_sim) / trades_per_sim),
    "Total Trades Executed": total_trades_per_sim,
    "Wins (before roll)": wins_before_list,
    "Wins (after roll)": wins_after_list,
    "Max Drawdown ($)": max_drawdowns,
    "Max Contracts Used": max_contracts_seen_list
})
st.subheader("Simulation Summary Table")
st.dataframe(summary_df.reset_index(drop=True))

# ---------------------------
# Plots
# ---------------------------
st.subheader("Histogram of final account values")
fig_hist = px.histogram(final_accounts, nbins=60, labels={'value': 'Final account ($)'}, title="Final account distribution")
fig_hist.add_vline(x=initial_account, line_dash="dash", line_color="black", annotation_text="Start account", annotation_position="top left")
st.plotly_chart(fig_hist, use_container_width=True)

st.subheader("Histogram of total rollovers per simulation")
fig_roll = px.histogram(total_rollovers_per_sim, nbins=40, labels={'value': 'Total rollovers'}, title="Total rollovers per simulation")
st.plotly_chart(fig_roll, use_container_width=True)

st.subheader("Sample final account trajectories (random subset)")
sample_n = min(40, len(final_accounts))
sample_idx = np.random.choice(len(final_accounts), sample_n, replace=False)
df_sample = pd.DataFrame({
    "Simulation": [i+1 for i in sample_idx],
    "Final Account": [final_accounts[i] for i in sample_idx]
})
# Simple bar for now (detailed per-trade account history would require storing intermediate account curves)
fig_sample = px.bar(df_sample, x="Simulation", y="Final Account", title="Sample final accounts (subset)")
st.plotly_chart(fig_sample, use_container_width=True)

st.success("Monte Carlo run complete. Tweak inputs and rerun to explore different strategies.")
