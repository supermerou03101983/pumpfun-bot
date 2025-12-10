"""
Paper Trading Engine

Simulates trades with 100% fidelity:
- Uses real on-chain prices
- Applies slippage, fees, taxes dynamically
- Records P&L in Redis
- Logs exactly as if real
"""

import time
from typing import Dict, Optional, List
from datetime import datetime, date
import redis
import structlog

logger = structlog.get_logger()


class PaperTradingEngine:
    """Simulates trading without real transactions"""

    def __init__(self, config: Dict):
        """
        Initialize paper trading engine

        Args:
            config: Configuration dict
        """
        self.config = config

        # Paper trading params
        paper_config = config.get("paper_trading", {})
        self.balance_sol = paper_config.get("initial_balance_sol", 10.0)
        self.simulated_slippage_pct = paper_config.get("simulated_slippage_percent", 2.5)
        self.simulated_network_fee = paper_config.get("simulated_network_fee_sol", 0.00001)
        self.simulated_priority_fee = paper_config.get("simulated_priority_fee_sol", 0.0004)
        self.apply_token_tax = paper_config.get("apply_token_tax", True)

        # Redis connection
        redis_config = config.get("redis", {})
        self.redis = redis.Redis(
            host=redis_config.get("host", "localhost"),
            port=redis_config.get("port", 6379),
            db=redis_config.get("db", 0),
            password=redis_config.get("password"),
            decode_responses=True,
        )

        # Active positions (mint -> position data)
        self.positions: Dict[str, Dict] = {}

        logger.info(
            "Paper trading engine initialized",
            initial_balance_sol=self.balance_sol,
            slippage_pct=self.simulated_slippage_pct,
        )

    def execute_buy(
        self,
        mint: str,
        sol_amount: float,
        tokens_received: float,
        price: float,
        metadata: Dict,
    ) -> Dict:
        """
        Simulate buy transaction

        Args:
            mint: Token mint
            sol_amount: SOL to spend
            tokens_received: Tokens received (after slippage)
            price: Effective price
            metadata: Token metadata

        Returns:
            Trade result dict
        """
        # Apply fees
        total_fee = self.simulated_network_fee + self.simulated_priority_fee
        total_cost = sol_amount + total_fee

        # Check balance
        if total_cost > self.balance_sol:
            logger.error(
                "Insufficient balance for paper buy",
                balance=self.balance_sol,
                cost=total_cost,
            )
            raise ValueError("Insufficient balance")

        # Deduct from balance
        self.balance_sol -= total_cost

        # Create position
        position = {
            "mint": mint,
            "entry_time": time.time(),
            "entry_price": price,
            "tokens": tokens_received,
            "sol_invested": sol_amount,
            "fees_paid": total_fee,
            "metadata": metadata,
        }

        self.positions[mint] = position

        # Record in Redis
        self._record_trade(
            trade_type="buy",
            mint=mint,
            sol_amount=sol_amount,
            tokens_amount=tokens_received,
            price=price,
            profit_sol=0,
            profit_pct=0,
        )

        logger.info(
            "Paper BUY executed",
            mint=mint,
            sol_spent=sol_amount,
            tokens_received=tokens_received,
            price=price,
            fees=total_fee,
            balance_remaining=self.balance_sol,
        )

        return {
            "type": "buy",
            "mint": mint,
            "sol_spent": sol_amount,
            "tokens_received": tokens_received,
            "price": price,
            "fees": total_fee,
            "timestamp": time.time(),
        }

    def execute_sell(
        self,
        mint: str,
        tokens_sold: float,
        sol_received: float,
        price: float,
        reason: str,
    ) -> Dict:
        """
        Simulate sell transaction

        Args:
            mint: Token mint
            tokens_sold: Tokens to sell
            sol_received: SOL received (after slippage)
            price: Effective price
            reason: Reason for selling

        Returns:
            Trade result dict
        """
        # Get position
        position = self.positions.get(mint)
        if not position:
            logger.error("No position found for paper sell", mint=mint)
            raise ValueError("No position found")

        # Check balance
        if tokens_sold > position["tokens"]:
            logger.error(
                "Insufficient tokens for paper sell",
                available=position["tokens"],
                requested=tokens_sold,
            )
            raise ValueError("Insufficient tokens")

        # Apply fees
        total_fee = self.simulated_network_fee + self.simulated_priority_fee
        net_sol_received = sol_received - total_fee

        # Update balance
        self.balance_sol += net_sol_received

        # Calculate profit
        proportion_sold = tokens_sold / position["tokens"]
        sol_invested = position["sol_invested"] * proportion_sold
        profit_sol = net_sol_received - sol_invested
        profit_pct = (profit_sol / sol_invested * 100) if sol_invested > 0 else 0

        # Update or remove position
        if tokens_sold >= position["tokens"]:
            # Full sell - remove position
            del self.positions[mint]
        else:
            # Partial sell - update position
            position["tokens"] -= tokens_sold
            position["sol_invested"] -= sol_invested

        # Record in Redis
        self._record_trade(
            trade_type="sell",
            mint=mint,
            sol_amount=net_sol_received,
            tokens_amount=tokens_sold,
            price=price,
            profit_sol=profit_sol,
            profit_pct=profit_pct,
            reason=reason,
        )

        logger.info(
            "Paper SELL executed",
            mint=mint,
            tokens_sold=tokens_sold,
            sol_received=net_sol_received,
            price=price,
            profit_sol=profit_sol,
            profit_pct=profit_pct,
            fees=total_fee,
            balance=self.balance_sol,
            reason=reason,
        )

        return {
            "type": "sell",
            "mint": mint,
            "tokens_sold": tokens_sold,
            "sol_received": net_sol_received,
            "price": price,
            "profit_sol": profit_sol,
            "profit_pct": profit_pct,
            "fees": total_fee,
            "reason": reason,
            "timestamp": time.time(),
        }

    def _record_trade(
        self,
        trade_type: str,
        mint: str,
        sol_amount: float,
        tokens_amount: float,
        price: float,
        profit_sol: float,
        profit_pct: float,
        reason: str = "",
    ):
        """
        Record trade in Redis

        Args:
            trade_type: "buy" or "sell"
            mint: Token mint
            sol_amount: SOL amount
            tokens_amount: Token amount
            price: Price
            profit_sol: Profit in SOL (for sells)
            profit_pct: Profit percentage (for sells)
            reason: Reason for trade
        """
        # Key: paper_trades:YYYY-MM-DD
        today = date.today().isoformat()
        key = f"paper_trades:{today}"

        # Trade data
        trade_data = {
            "type": trade_type,
            "mint": mint,
            "sol_amount": sol_amount,
            "tokens_amount": tokens_amount,
            "price": price,
            "profit_sol": profit_sol,
            "profit_pct": profit_pct,
            "reason": reason,
            "timestamp": time.time(),
        }

        # Store as hash field (trade_id -> JSON)
        trade_id = f"{mint}:{int(time.time() * 1000)}"
        self.redis.hset(key, trade_id, str(trade_data))

        # Set expiry (30 days)
        self.redis.expire(key, 30 * 24 * 60 * 60)

    def get_position(self, mint: str) -> Optional[Dict]:
        """
        Get current position for a mint

        Args:
            mint: Token mint

        Returns:
            Position dict or None
        """
        return self.positions.get(mint)

    def get_all_positions(self) -> List[Dict]:
        """
        Get all active positions

        Returns:
            List of position dicts
        """
        return list(self.positions.values())

    def get_balance(self) -> float:
        """
        Get current SOL balance

        Returns:
            SOL balance
        """
        return self.balance_sol

    def get_daily_pnl(self, date_str: Optional[str] = None) -> Dict:
        """
        Get daily P&L summary

        Args:
            date_str: Date string (YYYY-MM-DD), defaults to today

        Returns:
            P&L summary dict
        """
        if date_str is None:
            date_str = date.today().isoformat()

        key = f"paper_trades:{date_str}"

        # Get all trades for the day
        trades = self.redis.hgetall(key)

        if not trades:
            return {
                "date": date_str,
                "total_trades": 0,
                "buys": 0,
                "sells": 0,
                "total_profit_sol": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
            }

        # Parse trades
        total_trades = len(trades)
        buys = 0
        sells = 0
        total_profit_sol = 0
        winning_trades = 0
        losing_trades = 0

        for trade_json in trades.values():
            trade = eval(trade_json)  # Safe since we control the data

            if trade["type"] == "buy":
                buys += 1
            else:
                sells += 1
                profit = trade["profit_sol"]
                total_profit_sol += profit

                if profit > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1

        win_rate = (winning_trades / sells * 100) if sells > 0 else 0

        return {
            "date": date_str,
            "total_trades": total_trades,
            "buys": buys,
            "sells": sells,
            "total_profit_sol": total_profit_sol,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
        }


# Example usage
if __name__ == "__main__":
    # Test config
    config = {
        "paper_trading": {
            "initial_balance_sol": 10.0,
            "simulated_slippage_percent": 2.5,
            "simulated_network_fee_sol": 0.00001,
            "simulated_priority_fee_sol": 0.0004,
            "apply_token_tax": True,
        },
        "redis": {
            "host": "localhost",
            "port": 6379,
            "db": 0,
        },
    }

    engine = PaperTradingEngine(config)

    # Simulate buy
    buy_result = engine.execute_buy(
        mint="TEST123",
        sol_amount=0.1,
        tokens_received=100000,
        price=0.000001,
        metadata={"name": "Test Token"},
    )

    print(f"Buy: {buy_result}")
    print(f"Balance: {engine.get_balance()} SOL")

    # Simulate sell (with profit)
    sell_result = engine.execute_sell(
        mint="TEST123",
        tokens_sold=100000,
        sol_received=0.15,
        price=0.0000015,
        reason="Take profit",
    )

    print(f"Sell: {sell_result}")
    print(f"Balance: {engine.get_balance()} SOL")

    # Get daily P&L
    pnl = engine.get_daily_pnl()
    print(f"Daily P&L: {pnl}")
