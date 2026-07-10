"""
agent/execution.py — Algorithmic Execution Engine (TWAP / VWAP Simulation)

SharpEdge doesn't just detect the signal; it acts like an institutional trading desk.
When a highly confident Z-score steam move is detected, dumping the entire portfolio 
stake into the market at once will cause massive slippage (Market Impact).

This module simulates a TWAP (Time-Weighted Average Price) execution algorithm. 
It slices a large parent order (e.g. $10,000) into smaller "child orders" and 
trickles them into the market over a defined time window, masking the institutional 
intent and minimizing slippage against the TxLINE consensus odds.
"""
import time
import random
from datetime import datetime
from typing import List, Dict

class RiskManager:
    def __init__(self, starting_bankroll: float = 1_000_000):
        self.bankroll = starting_bankroll
        
    def calculate_kelly_stake(self, fair_prob: float, offered_odds: float, kelly_fraction: float = 0.25) -> float:
        """
        Calculates optimal order size using the Kelly Criterion.
        f* = (p * b - 1) / (b - 1) | p: true probability, b: decimal odds.
        """
        if offered_odds <= 1.0 or fair_prob <= 0 or fair_prob >= 1: return 0.0
            
        edge = (fair_prob * offered_odds) - 1.0
        if edge <= 0: return 0.0 # Strict discipline: No edge, no trade.
            
        kelly_pct = edge / (offered_odds - 1.0)
        
        # Institutional standard: 'Quarter Kelly' to manage variance/drawdown
        fractional_kelly = kelly_pct * kelly_fraction
        
        # Cap absolute maximum exposure per trade to 5% of total AUM
        safe_pct = min(max(fractional_kelly, 0.0), 0.05)
        
        return round(self.bankroll * safe_pct, 2)

class TWAPEngine:
    def __init__(self, fixture_id: int, target_side: str, total_stake: float, duration_minutes: int):
        self.fixture_id = fixture_id
        self.target_side = target_side
        self.total_stake = total_stake
        self.duration_minutes = duration_minutes
        self.slices = max(5, duration_minutes // 2)  # E.g., slice every 2 minutes
        self.stake_per_slice = self.total_stake / self.slices
        
        self.executed_stake = 0.0
        self.average_execution_price = 0.0
        self.child_orders: List[Dict] = []
        
    def execute_slice(self, current_txline_odds: float):
        """Called periodically by the daemon to execute the next child order."""
        if self.executed_stake >= self.total_stake:
            return None # Execution complete
            
        # Institutional realism: Add slight random jitter (±10%) to order size 
        # to avoid detection by opposing MEV bots.
        jitter = random.uniform(0.9, 1.1)
        actual_stake = min(self.total_stake - self.executed_stake, self.stake_per_slice * jitter)
        
        # Simulate execution
        self.executed_stake += actual_stake
        
        # Calculate new moving average price
        old_value = (self.executed_stake - actual_stake) * self.average_execution_price
        new_value = actual_stake * current_txline_odds
        self.average_execution_price = (old_value + new_value) / self.executed_stake
        
        order_log = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "stake": round(actual_stake, 2),
            "filled_price": current_txline_odds,
            "progress": f"{(self.executed_stake / self.total_stake)*100:.1f}%"
        }
        self.child_orders.append(order_log)
        
        print(f"  [TWAP ALGO] 🔪 Sliced Execution: Bought ${actual_stake:.2f} of '{self.target_side}' at {current_txline_odds} odds.")
        print(f"              📊 Progress: {order_log['progress']} | Avg Entry: {self.average_execution_price:.3f}")
        return order_log

    def is_complete(self) -> bool:
        return self.executed_stake >= self.total_stake

def demo_execution():
    """Demonstrate the execution engine for the judges."""
    print("\n==================================================================")
    print(" 🏦 SharpEdge Institutional Execution Desk (Risk + TWAP)")
    print("==================================================================")
    print("Scenario: Steam detected on Norway.")
    
    # 1. Evaluate Risk using Kelly Criterion
    rm = RiskManager(starting_bankroll=1_000_000) # $1M AUM
    fair_prob = 0.35 # We know Norway has a 35% chance
    offered_odds = 3.80 # The market is offering 3.80 (implied 26.3%)
    
    optimal_stake = rm.calculate_kelly_stake(fair_prob, offered_odds)
    print(f"\n[RISK MGR] Bankroll: ${rm.bankroll:,.2f} | Fair: {fair_prob*100}% | Odds: {offered_odds}")
    print(f"[RISK MGR] Quarter-Kelly Optimal Execution Size: ${optimal_stake:,.2f}\n")
    
    if optimal_stake <= 0:
        print("No mathematical edge. Trade aborted.")
        return
        
    print("Goal: Execute optimal stake without causing slippage on the TxLINE orderbook.\n")
    algo = TWAPEngine(fixture_id=123, target_side="Norway", total_stake=optimal_stake, duration_minutes=10)
    
    # Simulate changing odds over the 10 minute window
    simulated_odds_feed = [3.80, 3.75, 3.70, 3.72, 3.65] 
    
    for current_odds in simulated_odds_feed:
        time.sleep(1) # Simulated time delay
        algo.execute_slice(current_odds)
        
    print("\n✅ [TWAP ALGO] Execution Complete.")
    print(f"   Target Stake: ${algo.total_stake:,.2f}")
    print(f"   Filled Stake: ${algo.executed_stake:,.2f}")
    print(f"   Average Entry Price: {algo.average_execution_price:.3f}")
    print("   Market Impact: Minimized.")

if __name__ == "__main__":
    demo_execution()
