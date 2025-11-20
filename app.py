import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px
import math

st.set_page_config(layout="wide")
st.title("Credit Spread Monte Carlo Simulator")

# ---------------------------
# SIDEBAR INPUTS
# ---------------------------
st.sidebar.header("Simulation Parameters")

account_size = st.sidebar.number_input("Account Size ($)", value=100000)
spread_width = st.sidebar.number_input("Spread Width ($)", value=25)
collateral_per_contract = st.sidebar.number_input("Collateral per Contract ($)", value=2500)

starting_contracts = st.sidebar.number_input("Starting Contracts (Main Trade)", value=6)
main_trade_delta = st.sidebar.selectbox("Main Trade Delta", [50, 40, 35])

profit_target_percent = 0.5  # 50% of credit for win
max_loss_percent = st.sidebar.slider("Max Loss (% of collateral)", 0.1, 1.0, 0.5)

# Rollovers
max_rollovers = st.sidebar.selectbox("Max Rollovers on Loss", [1, 2, 3, 4])
rollover_deltas = st.sidebar.multiselect("Rollover Delta Options", [50, 40, 35], default=[50, 40, 35])

num_trades_per_sim = st.sidebar.number_input("Number of Trades per Simulation", value=10)
num_simulations = st.sidebar.number_input("Number of Simulations", value=500)

# ---------------------------
# Probability mapping
# ---------------------------
delta_probs_map = {50: 0.5, 40: 0.6, 35: 0.65}

profit_per_contract = collateral_per_contract * profit_target_percent
max_loss_per_contract = collateral_per_contract * max_loss_percent

# ---------------------------
# MONTE CARLO SIMULATION FUNCTION
# ---------------------------
def run_monte_carlo():
    all_results = []

    for sim_id in range(1, num_simulations + 1):
        account = account_size
        contracts = starting_contracts
        rollover_count = 0

        for trade in range(num_trades_per_sim):
            # Choose delta
            if trade == 0:
                delta = main_trade_delta
            else:
                delta = np.random.choice(rollover_deltas)
            win_prob = delta_probs_map.get(delta, 0.5)

            win = np.random.rand() < win_prob

            if win:
                pnl = contracts * profit_per_contract
                account += pnl
                outcome = 'Win'
                contracts = starting_contracts
                rollover_count = 0
            else:
                pnl = -contracts * max_loss_per_contract
                account += pnl
                outcome = 'Loss'
                rollover_count += 1
                if rollover_count <= max_rollovers:
                    contracts *= 2
                else:
                    contracts = starting_contracts
                    rollover_count = 0

            all_results.append({
                'Simulation': sim_id,
                'Trade': trade+1,
                'Contracts': contracts,
                'Delta': delta,
                'Outcome': outcome,
                'P&L': pnl,
                'Account': account,
                'Rollover Count': rollover_count
            })

            if account <= 0:
                break

    return pd.DataFrame(all_results)

# ---------------------------
# RUN SIMULATION
# ---------------------------
df_results = run_monte_carlo()

# ---------------------------
# DASHBOARD METRICS
# ---------------------------
st.subheader("Simulation Dashboard")
total_simulations = df_results['Simulation'].nunique()
final_accounts = df_results.groupby('Simulation')['Account'].last()
avg_final_account = final_accounts.mean()
max_final_account = final_accounts.max()
min_final_account = final_accounts.min()
drawdowns = df_results.groupby('Simulation')['Account'].agg(lambda x: x.max() - x.min())
avg_drawdown = drawdowns.mean()
max_drawdown = drawdowns.max()
prob_profit = (final_accounts > account_size).mean() * 100  # in %

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Total Simulations", total_simulations)
col2.metric("Avg Final Account", f"${avg_final_account:,.0f}")
col3.metric("Max Final Account", f"${max_final_account:,.0f}")
col4.metric("Min Final Account", f"${min_final_account:,.0f}")
col5.metric("Avg Drawdown", f"${avg_drawdown:,.0f}")
col6.metric("Prob. of Profit", f"{prob_profit:.1f}%")

# ---------------------------
# EQUITY CURVES
# ---------------------------
st.subheader("Sample Equity Curves")
sample_sims = df_results['Simulation'].unique()[:5]
fig = px.line(df_results[df_results['Simulation'].isin(sample_sims)],
              x='Trade', y='Account', color='Simulation',
              markers=True, title="Equity Curves for Sample Simulations")
st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# HISTOGRAM OF FINAL ACCOUNT VALUES
# ---------------------------
st.subheader("Distribution of Final Account Values")
fig_hist = px.histogram(final_accounts, nbins=20,
                        title="Histogram of Final Account Values",
                        labels={'value':'Final Account'})
st.plotly_chart(fig_hist, use_container_width=True)

# ---------------------------
# SUMMARY TABLE
# ---------------------------
st.subheader("Simulation Results (first 20 rows)")
st.dataframe(df_results.head(20))
