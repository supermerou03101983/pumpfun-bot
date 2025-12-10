"""
Trading Strategy State Machine

State flow:
    IDLE → DETECT → FILTER → BUY → MONITOR → SELL → IDLE

Exit conditions:
1. Take profit: 50% at +50%
2. Trailing stop: -15% from peak if >+100%
3. Time-based: >90 minutes
4. Volume drop: >80% decrease
"""

import asyncio
import time
from typing import Dict, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
import structlog

from src.core.detector import TokenDetector
from src.core.filters import TokenFilters
from src.core.trader import Trader
from src.core.bonding_curve import BondingCurve

logger = structlog.get_logger()


class TradeState(Enum):
    """Trading state machine states"""

    IDLE = "idle"
    DETECT = "detect"
    FILTER = "filter"
    BUY = "buy"
    MONITOR = "monitor"
    SELL = "sell"


@dataclass
class Position:
    """Active trading position"""

    mint: str
    entry_time: float
    entry_price: float
    tokens: float
    sol_invested: float
    peak_price: float
    state: TradeState


class TradingStrategy:
    """Main trading strategy orchestrator"""

    def __init__(self, config: Dict, trader: Trader):
        """
        Initialize strategy

        Args:
            config: Configuration dict
            trader: Trader instance
        """
        self.config = config
        self.trader = trader

        # Components
        self.filters = TokenFilters(config["filters"])
        self.bonding_curve = BondingCurve(**config["pumpfun"].get("bonding_curve", {}))

        # Strategy parameters
        self.take_profit_pct = config["strategy"]["take_profit_percentage"]
        self.take_profit_target = config["strategy"]["take_profit_target"]
        self.trailing_stop_enabled = config["strategy"]["trailing_stop_enabled"]
        self.trailing_stop_activation = config["strategy"]["trailing_stop_activation"]
        self.trailing_stop_pct = config["strategy"]["trailing_stop_percentage"]
        self.max_hold_time_min = config["strategy"]["max_hold_time_minutes"]
        self.volume_drop_threshold = config["strategy"]["volume_drop_threshold"]

        # Active positions
        self.positions: Dict[str, Position] = {}

        # Detector (initialized later)
        self.detector = None

        logger.info(
            "Strategy initialized",
            take_profit_target=self.take_profit_target,
            trailing_stop_activation=self.trailing_stop_activation,
            max_hold_time_min=self.max_hold_time_min,
        )

    async def start(self):
        """Start strategy (detection + monitoring)"""
        logger.info("Starting trading strategy")

        # Initialize detector with callback
        self.detector = TokenDetector(self.config, self._on_token_detected)

        # Start detector task
        detector_task = asyncio.create_task(self.detector.start())

        # Start monitoring task
        monitor_task = asyncio.create_task(self._monitor_positions())

        # Run both
        await asyncio.gather(detector_task, monitor_task)

    async def _on_token_detected(self, token_data: Dict):
        """
        Callback when new token detected

        Args:
            token_data: Token data from detector
        """
        mint = token_data["mint"]

        logger.info("Processing detected token", mint=mint)

        # Step 1: Enrich token data (fetch on-chain metadata)
        enriched_data = await self._enrich_token_data(token_data)

        if not enriched_data:
            logger.warning("Failed to enrich token data", mint=mint)
            return

        # Step 2: Run filters
        passed, filter_results = self.filters.run_all_filters(enriched_data)

        if not passed:
            failed_filters = [r.reason for r in filter_results if not r.passed]
            logger.info(
                "Token failed filters",
                mint=mint,
                failed=failed_filters,
            )
            return

        logger.info("Token passed all filters", mint=mint)

        # Step 3: Execute buy
        success, trade_result = await self.trader.buy(mint, enriched_data)

        if not success:
            logger.error("Buy failed", mint=mint)
            return

        # Step 4: Create position for monitoring
        position = Position(
            mint=mint,
            entry_time=time.time(),
            entry_price=trade_result["price"],
            tokens=trade_result["tokens_received"],
            sol_invested=trade_result["sol_spent"],
            peak_price=trade_result["price"],
            state=TradeState.MONITOR,
        )

        self.positions[mint] = position

        logger.info(
            "Position opened",
            mint=mint,
            tokens=position.tokens,
            entry_price=position.entry_price,
        )

    async def _enrich_token_data(self, token_data: Dict) -> Optional[Dict]:
        """
        Enrich token data with on-chain metadata

        Args:
            token_data: Basic token data from detector

        Returns:
            Enriched dict or None
        """
        mint = token_data["mint"]

        try:
            # TODO: Fetch from on-chain:
            # - Mint authority
            # - Token name/symbol
            # - SOL in bonding curve
            # - Simulate sell transaction
            # - Calculate sell tax

            # For now, return mock data for paper trading
            enriched = {
                **token_data,
                "mint_authority": None,  # Mock: renounced
                "name": token_data.get("name", "Unknown"),
                "symbol": token_data.get("symbol", "UNK"),
                "sol_in_curve": 5.0,  # Mock
                "sell_tax_percent": 5.0,  # Mock
                "simulation_success": True,  # Mock
            }

            return enriched

        except Exception as e:
            logger.error("Error enriching token data", error=str(e), mint=mint)
            return None

    async def _monitor_positions(self):
        """Monitor active positions for exit conditions"""
        logger.info("Starting position monitor")

        while True:
            try:
                # Check each position
                for mint, position in list(self.positions.items()):
                    await self._check_exit_conditions(mint, position)

                # Sleep before next check
                await asyncio.sleep(1)

            except Exception as e:
                logger.error("Position monitoring error", error=str(e))
                await asyncio.sleep(5)

    async def _check_exit_conditions(self, mint: str, position: Position):
        """
        Check if position should be exited

        Args:
            mint: Token mint
            position: Position object
        """
        # Get current price
        current_price = await self._get_current_price(mint)

        if current_price is None:
            return

        # Calculate profit
        profit_pct = ((current_price - position.entry_price) / position.entry_price) * 100

        # Update peak price
        if current_price > position.peak_price:
            position.peak_price = current_price

        # Calculate hold time
        hold_time_min = (time.time() - position.entry_time) / 60

        # Exit condition 1: Take profit (50% at +50%)
        if profit_pct >= self.take_profit_target:
            sell_amount = position.tokens * (self.take_profit_pct / 100)
            await self._execute_sell(
                mint,
                sell_amount,
                f"Take profit {self.take_profit_pct}% at +{profit_pct:.1f}%",
            )
            return

        # Exit condition 2: Trailing stop (if >+100%)
        if self.trailing_stop_enabled and profit_pct > self.trailing_stop_activation:
            # Calculate stop price
            stop_price = position.peak_price * (1 - self.trailing_stop_pct / 100)

            if current_price <= stop_price:
                await self._execute_sell(
                    mint,
                    position.tokens,
                    f"Trailing stop triggered at +{profit_pct:.1f}% (peak was +{((position.peak_price - position.entry_price) / position.entry_price * 100):.1f}%)",
                )
                return

        # Exit condition 3: Time-based (>90 min)
        if hold_time_min >= self.max_hold_time_min:
            await self._execute_sell(
                mint,
                position.tokens,
                f"Max hold time reached ({hold_time_min:.0f} min)",
            )
            return

        # Exit condition 4: Volume drop (>80%)
        volume_drop = await self._check_volume_drop(mint)
        if volume_drop and volume_drop > self.volume_drop_threshold:
            await self._execute_sell(
                mint,
                position.tokens,
                f"Volume drop detected ({volume_drop:.0f}%)",
            )
            return

        # Log current status every 60 seconds
        if int(time.time()) % 60 == 0:
            logger.info(
                "Position status",
                mint=mint,
                profit_pct=f"{profit_pct:+.1f}%",
                hold_time_min=f"{hold_time_min:.1f}",
                current_price=f"{current_price:.10f}",
                peak_price=f"{position.peak_price:.10f}",
            )

    async def _get_current_price(self, mint: str) -> Optional[float]:
        """
        Get current token price

        Args:
            mint: Token mint

        Returns:
            Price in SOL or None
        """
        # TODO: Fetch real price from on-chain or DexScreener
        # For now, return mock price for testing
        return 0.00001  # Mock

    async def _check_volume_drop(self, mint: str) -> Optional[float]:
        """
        Check if volume has dropped significantly

        Args:
            mint: Token mint

        Returns:
            Volume drop percentage or None
        """
        # TODO: Implement volume tracking
        # For now, return None (no drop detected)
        return None

    async def _execute_sell(self, mint: str, amount: float, reason: str):
        """
        Execute sell and close position

        Args:
            mint: Token mint
            amount: Tokens to sell
            reason: Reason for selling
        """
        logger.info("Executing sell", mint=mint, amount=amount, reason=reason)

        success, result = await self.trader.sell(mint, amount, reason)

        if success:
            # Remove position
            if mint in self.positions:
                del self.positions[mint]

            logger.info(
                "Position closed",
                mint=mint,
                profit_sol=result.get("profit_sol"),
                profit_pct=result.get("profit_pct"),
                reason=reason,
            )
        else:
            logger.error("Sell failed", mint=mint)


# Example usage
if __name__ == "__main__":

    async def test_strategy():
        """Test strategy"""
        from src.utils.security import generate_test_keypair

        config = {
            "trading_mode": "paper",
            "solana": {"rpc_url": "https://api.mainnet-beta.solana.com"},
            "helius": {
                "api_key": "test",
                "webhook_url": "http://localhost:8080/webhook",
            },
            "dexscreener": {"enabled": False, "poll_interval_seconds": 5},
            "strategy": {
                "max_token_age_seconds": 12,
                "entry_amount_sol": 0.1,
                "entry_slippage_bps": 2000,
                "priority_fee_lamports": 400000,
                "take_profit_percentage": 50,
                "take_profit_target": 50,
                "trailing_stop_enabled": True,
                "trailing_stop_activation": 100,
                "trailing_stop_percentage": 15,
                "max_hold_time_minutes": 90,
                "volume_drop_threshold": 80,
            },
            "filters": {
                "min_first_buy_sol": 0.5,
                "require_mint_renounced": True,
                "max_sell_tax_percent": 15,
                "require_sell_simulation": True,
                "min_liquidity_sol": 1.0,
                "banned_name_keywords": ["test", "rug"],
            },
            "pumpfun": {
                "program_id": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
            },
            "health": {"port": 8080},
            "paper_trading": {"initial_balance_sol": 10.0},
        }

        keypair = generate_test_keypair()

        from src.core.trader import Trader

        trader = Trader(config, keypair)
        strategy = TradingStrategy(config, trader)

        # Run strategy (will block)
        await strategy.start()

    # asyncio.run(test_strategy())
    print("Strategy module loaded successfully")
