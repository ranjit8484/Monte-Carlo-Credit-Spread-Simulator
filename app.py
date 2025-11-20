import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import math

st.title("Credit Spread Monte Carlo Simulator")

# ---------------------------
# Streamlit input widgets
# ---------------------------
account_size = st.number_input("Account Size ($)", value=100000)
spread_width = st.number_input("Spread Width ($)", value=25)
collateral_per_contract = st.number_input("Collateral per Contract ($)", value=2500)
starting_contracts = st.number_input("Starting Contracts", value=6)
profit_target_percent = st.slider("Profit Target (% of collateral)", 0.1, 1.0, 0.5)
max_loss_percent = st.slider("Max Loss (% of collateral)", 0.1, 1.0, 0.5)
starting_delta = st.number_input("Starting Delta", value=50)
delta_ladder_input = st.text_input("Delta Ladder (comma-separated)", "50,40,35,30,25")
delta_ladder = [int(x) for x in delta_ladder_input.split(",")]
max_doublings = st.number_input("Max Doublings", min_value=0, max_value=5, value=2)
num_trades_per_sim = st.number_input("Number of Trades per Simulation", value=10)
num_simulations = st.number_input("Number of Simulations", value=100)

# Probability mapping (simplified example)
delta_probs_map = {50: 0.5, 40: 0.6, 35: 0.65, 30: 0.7, 25: 0.75}

profit_per_contract = collateral_per_contract * profit_target_percent
max_loss_per_contract = collateral_per_contract * max_loss_percent

# ---------------------------
# Monte Carlo Simulation
# ---------------------------
all_results = []
for sim_id in range(1, num_simulations + 1):
    account = account_size
    contracts = starting_contracts
    
    for trade in range(num_trades_per_sim):
        delta_index = min(trade, len(delta_ladder) - 1)
        delta = delta_ladder[delta_index]
        win_prob = delta_probs_map.get(delta, 0.5)
        win = np.random.rand() < win_prob
        
        if win:
            pnl = contracts * profit_per_contract
            account += pnl
            contracts = starting_contracts
        else:
            pnl = -contracts * max_loss_per_contract
            account += pnl
            if contracts < starting_contracts * 2**max_doublings:
                contracts *= 2
            else:
                contracts = starting_contracts * 2**max_doublings
        
        all_results.append({
            'Simulation': sim_id,
            'Trade': trade+1,
            'Contracts': contracts,
            'Delta': delta,
            'P&L': pnl,
            'Account': account
        })

df_results = pd.DataFrame(all_results)

# ---------------------------
# Display summary
# ---------------------------
st.subheader("Simulation Results (first 10 rows)")
st.dataframe(df_results.head(10))

st.subheader("Summary Statistics")
summary_stats = df_results.groupby('Simulation')['Account'].agg(['max','min']).reset_index()
st.dataframe(summary_stats.head(10))

# ---------------------------
# Plot sample equity curves
# ---------------------------
st.subheader("Sample Equity Curves")
sample_sims = df_results['Simulation'].unique()[:5]
for sim_id in sample_sims:
    df_sim = df_results[df_results['Simulation'] == sim_id]
    st.line_chart(df_sim.set_index('Trade')['Account'])
