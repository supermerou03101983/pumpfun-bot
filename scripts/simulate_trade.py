#!/usr/bin/env python3
"""
Trade Simulation Script

Manually simulate a trade (buy/sell) for testing purposes.

Usage:
    python scripts/simulate_trade.py <MINT> [--mode=paper|live]

Example:
    python scripts/simulate_trade.py GPNm7x8JhzFKEjzvLH5TnKXjK3LqPJbP3Jgg9Lb7pump --mode=paper
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import argparse
from src.core.bonding_curve import BondingCurve
from src.utils.paper_engine import PaperTradingEngine


def load_config():
    """Load configuration"""
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"

    if not config_path.exists():
        print("❌ Config not found. Using defaults.")
        return {
            "trading_mode": "paper",
            "strategy": {
                "entry_amount_sol": 0.1,
                "entry_slippage_bps": 2000,
            },
            "pumpfun": {
                "bonding_curve": {
                    "initial_virtual_sol_reserves": 30.0,
                    "initial_virtual_token_reserves": 1073000000.0,
                    "initial_real_token_reserves": 793100000.0,
                }
            },
            "paper_trading": {
                "initial_balance_sol": 10.0,
                "simulated_slippage_percent": 2.5,
                "simulated_network_fee_sol": 0.00001,
                "simulated_priority_fee_sol": 0.0004,
            },
            "redis": {
                "host": "localhost",
                "port": 6379,
                "db": 0,
            },
        }

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def simulate_buy(mint: str, config: dict):
    """Simulate buy transaction"""
    print(f"\n{'=' * 60}")
    print(f"Simulating BUY for {mint}")
    print(f"{'=' * 60}\n")

    # Initialize bonding curve
    curve_params = config["pumpfun"].get("bonding_curve", {})
    curve = BondingCurve(**curve_params)

    # Simulate current state
    sol_in_curve = 5.0  # Mock: 5 SOL already in curve
    entry_amount = config["strategy"]["entry_amount_sol"]
    slippage_bps = config["strategy"]["entry_slippage_bps"]

    print(f"Entry Amount: {entry_amount} SOL")
    print(f"Slippage: {slippage_bps / 100}%")
    print(f"Current SOL in Curve: {sol_in_curve} SOL")
    print()

    # Calculate trade
    trade_sim = curve.simulate_trade_with_slippage(
        entry_amount,
        sol_in_curve,
        slippage_bps,
        is_buy=True,
    )

    print("Trade Simulation:")
    print(f"  Tokens Out (no slippage): {trade_sim['tokens_out']:,.0f}")
    print(f"  Tokens Out (with slippage): {trade_sim['tokens_out_with_slippage']:,.0f}")
    print(f"  Effective Price: {trade_sim['effective_price']:.12f} SOL")
    print(f"  Price Impact: {trade_sim['price_impact_pct']:.2f}%")
    print()

    # Execute in paper engine
    paper_engine = PaperTradingEngine(config)

    try:
        result = paper_engine.execute_buy(
            mint=mint,
            sol_amount=entry_amount,
            tokens_received=trade_sim["tokens_out_with_slippage"],
            price=trade_sim["effective_price"],
            metadata={"name": "Test Token", "symbol": "TEST"},
        )

        print("✅ Paper Trade Executed:")
        print(f"   SOL Spent: {result['sol_spent']}")
        print(f"   Tokens Received: {result['tokens_received']:,.0f}")
        print(f"   Fees: {result['fees']} SOL")
        print(f"   Balance Remaining: {paper_engine.get_balance()} SOL")

    except Exception as e:
        print(f"❌ Trade failed: {e}")
        return False

    return True


def simulate_sell(mint: str, config: dict):
    """Simulate sell transaction"""
    print(f"\n{'=' * 60}")
    print(f"Simulating SELL for {mint}")
    print(f"{'=' * 60}\n")

    # Initialize paper engine
    paper_engine = PaperTradingEngine(config)

    # First, create a position (simulate previous buy)
    print("Step 1: Creating test position...")
    paper_engine.execute_buy(
        mint=mint,
        sol_amount=0.1,
        tokens_received=100000,
        price=0.000001,
        metadata={"name": "Test Token"},
    )
    print(f"✅ Position created: 100,000 tokens\n")

    # Now simulate sell at profit
    print("Step 2: Simulating sell at +50% profit...")

    curve = BondingCurve(**config["pumpfun"].get("bonding_curve", {}))
    sol_in_curve = 10.0  # Mock: more liquidity now
    token_amount = 100000

    trade_sim = curve.simulate_trade_with_slippage(
        token_amount,
        sol_in_curve,
        config["strategy"]["entry_slippage_bps"],
        is_buy=False,
    )

    print(f"  SOL Out (no slippage): {trade_sim['sol_out']:.6f}")
    print(f"  SOL Out (with slippage): {trade_sim['sol_out_with_slippage']:.6f}")
    print(f"  Effective Price: {trade_sim['effective_price']:.12f} SOL")
    print()

    # Execute sell
    try:
        result = paper_engine.execute_sell(
            mint=mint,
            tokens_sold=token_amount,
            sol_received=trade_sim["sol_out_with_slippage"],
            price=trade_sim["effective_price"],
            reason="Simulated profit taking",
        )

        print("✅ Paper Sell Executed:")
        print(f"   Tokens Sold: {result['tokens_sold']:,.0f}")
        print(f"   SOL Received: {result['sol_received']:.6f}")
        print(f"   Profit: {result['profit_sol']:+.6f} SOL ({result['profit_pct']:+.1f}%)")
        print(f"   Balance: {paper_engine.get_balance()} SOL")

    except Exception as e:
        print(f"❌ Sell failed: {e}")
        return False

    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Simulate trades for testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simulate buy
  python scripts/simulate_trade.py GPNm7x8JhzFKEjzvLH5TnKXjK3LqPJbP3Jgg9Lb7pump --action=buy

  # Simulate sell
  python scripts/simulate_trade.py GPNm7x8JhzFKEjzvLH5TnKXjK3LqPJbP3Jgg9Lb7pump --action=sell

  # Simulate both
  python scripts/simulate_trade.py GPNm7x8JhzFKEjzvLH5TnKXjK3LqPJbP3Jgg9Lb7pump --action=both
        """,
    )

    parser.add_argument("mint", help="Token mint address")
    parser.add_argument(
        "--action",
        choices=["buy", "sell", "both"],
        default="both",
        help="Action to simulate (default: both)",
    )

    args = parser.parse_args()

    # Load config
    config = load_config()

    print("\n🎮 PumpFun Bot - Trade Simulator")

    # Run simulations
    if args.action in ["buy", "both"]:
        success = simulate_buy(args.mint, config)
        if not success:
            sys.exit(1)

    if args.action in ["sell", "both"]:
        success = simulate_sell(args.mint, config)
        if not success:
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print("✅ Simulation complete!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
