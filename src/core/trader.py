"""
Trading Execution Engine

Handles buy/sell transactions on Solana.
Respects trading_mode (paper vs. live) from config.

In PAPER mode:
- No real transactions sent
- Simulates trades using real on-chain prices
- Records P&L in Redis

In LIVE mode:
- Sends real transactions to Solana
- Requires LIVE_MODE_CONFIRMED=true in ENV
"""

import os
import asyncio
from typing import Dict, Optional, Tuple
from decimal import Decimal
import structlog
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
import time

from src.core.bonding_curve import BondingCurve
from src.utils.paper_engine import PaperTradingEngine

logger = structlog.get_logger()


class Trader:
    """Trading execution engine"""

    def __init__(self, config: Dict, keypair: Keypair):
        """
        Initialize trader

        Args:
            config: Configuration dict
            keypair: Solana keypair for trading
        """
        self.config = config
        self.keypair = keypair

        # Trading mode
        self.mode = config.get("trading_mode", "paper")
        self._validate_mode()

        # RPC client
        self.rpc_url = config["solana"]["rpc_url"]
        self.client = AsyncClient(self.rpc_url)

        # Backup RPC
        self.backup_rpc_url = config["solana"].get("backup_rpc_url")
        self.backup_client = (
            AsyncClient(self.backup_rpc_url) if self.backup_rpc_url else None
        )

        # Strategy params
        self.entry_amount_sol = config["strategy"]["entry_amount_sol"]
        self.entry_slippage_bps = config["strategy"]["entry_slippage_bps"]
        self.priority_fee_lamports = config["strategy"]["priority_fee_lamports"]

        # Bonding curve
        self.bonding_curve = BondingCurve(
            **config["pumpfun"].get("bonding_curve", {})
        )

        # Paper trading engine
        if self.mode == "paper":
            self.paper_engine = PaperTradingEngine(config)
        else:
            self.paper_engine = None

        # Pump.fun program ID
        self.pumpfun_program_id = Pubkey.from_string(config["pumpfun"]["program_id"])

        logger.info(
            f"Trader initialized",
            mode=self.mode,
            wallet=str(self.keypair.pubkey()),
            entry_amount_sol=self.entry_amount_sol,
        )

    def _validate_mode(self):
        """Validate trading mode and safety checks"""
        if self.mode not in ["paper", "live"]:
            raise ValueError(f"Invalid trading_mode: {self.mode}. Must be 'paper' or 'live'")

        if self.mode == "live":
            # Safety check: require explicit confirmation
            confirmed = os.getenv("LIVE_MODE_CONFIRMED", "").lower() == "true"
            if not confirmed:
                raise RuntimeError(
                    "LIVE trading mode requires LIVE_MODE_CONFIRMED=true in environment. "
                    "This prevents accidental live trading. "
                    "Set the env var and restart the bot."
                )
            logger.warning(
                "🔴 LIVE TRADING MODE ENABLED 🔴",
                mode="live",
                wallet=str(self.keypair.pubkey()),
            )
        else:
            logger.info("📄 Paper trading mode (no real transactions)")

    async def buy(
        self, mint: str, token_data: Dict
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Execute buy transaction

        Args:
            mint: Token mint address
            token_data: Token metadata

        Returns:
            Tuple of (success, trade_result)
        """
        if self.mode == "paper":
            return await self._buy_paper(mint, token_data)
        else:
            return await self._buy_live(mint, token_data)

    async def sell(
        self, mint: str, token_amount: float, reason: str
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Execute sell transaction

        Args:
            mint: Token mint address
            token_amount: Tokens to sell
            reason: Reason for selling (for logging)

        Returns:
            Tuple of (success, trade_result)
        """
        if self.mode == "paper":
            return await self._sell_paper(mint, token_amount, reason)
        else:
            return await self._sell_live(mint, token_amount, reason)

    async def _buy_paper(
        self, mint: str, token_data: Dict
    ) -> Tuple[bool, Optional[Dict]]:
        """Execute paper buy (simulation)"""
        logger.info("Simulating BUY", mint=mint, amount_sol=self.entry_amount_sol)

        # Get current on-chain price
        sol_in_curve = token_data.get("sol_in_curve", 5.0)

        # Simulate trade with bonding curve
        trade_sim = self.bonding_curve.simulate_trade_with_slippage(
            self.entry_amount_sol,
            sol_in_curve,
            self.entry_slippage_bps,
            is_buy=True,
        )

        # Record in paper engine
        trade_result = self.paper_engine.execute_buy(
            mint=mint,
            sol_amount=self.entry_amount_sol,
            tokens_received=trade_sim["tokens_out_with_slippage"],
            price=trade_sim["effective_price"],
            metadata=token_data,
        )

        logger.info(
            "Paper BUY executed",
            mint=mint,
            sol_spent=self.entry_amount_sol,
            tokens_received=trade_result["tokens_received"],
            price=trade_result["price"],
        )

        return (True, trade_result)

    async def _sell_paper(
        self, mint: str, token_amount: float, reason: str
    ) -> Tuple[bool, Optional[Dict]]:
        """Execute paper sell (simulation)"""
        logger.info("Simulating SELL", mint=mint, tokens=token_amount, reason=reason)

        # Get current position
        position = self.paper_engine.get_position(mint)
        if not position:
            logger.error("No position found for paper sell", mint=mint)
            return (False, None)

        # Get current on-chain price (fetch from RPC in real implementation)
        # For now, use a mock price increase of 50% for simulation
        sol_in_curve = 10.0  # Mock value
        current_price, _ = self.bonding_curve.get_price(sol_in_curve)

        # Simulate sell
        trade_sim = self.bonding_curve.simulate_trade_with_slippage(
            token_amount,
            sol_in_curve,
            self.entry_slippage_bps,
            is_buy=False,
        )

        # Record in paper engine
        trade_result = self.paper_engine.execute_sell(
            mint=mint,
            tokens_sold=token_amount,
            sol_received=trade_sim["sol_out_with_slippage"],
            price=trade_sim["effective_price"],
            reason=reason,
        )

        logger.info(
            "Paper SELL executed",
            mint=mint,
            tokens_sold=token_amount,
            sol_received=trade_result["sol_received"],
            profit_sol=trade_result["profit_sol"],
            profit_pct=trade_result["profit_pct"],
            reason=reason,
        )

        return (True, trade_result)

    async def _buy_live(
        self, mint: str, token_data: Dict
    ) -> Tuple[bool, Optional[Dict]]:
        """Execute live buy transaction"""
        logger.warning(
            "Executing LIVE BUY",
            mint=mint,
            amount_sol=self.entry_amount_sol,
        )

        try:
            # Build swap instruction (pump.fun specific)
            # This is a simplified example - real implementation needs full instruction building
            mint_pubkey = Pubkey.from_string(mint)

            # Get recent blockhash
            recent_blockhash = await self.client.get_latest_blockhash()

            # Build transaction
            # NOTE: This is a placeholder - real pump.fun swap requires:
            # 1. Derive bonding curve PDA
            # 2. Build proper instruction with program accounts
            # 3. Add compute budget for priority fee
            # 4. Sign and send

            # For now, return placeholder
            logger.error("Live trading not fully implemented yet")
            return (False, None)

        except Exception as e:
            logger.error("Buy transaction failed", error=str(e), mint=mint)
            return (False, None)

    async def _sell_live(
        self, mint: str, token_amount: float, reason: str
    ) -> Tuple[bool, Optional[Dict]]:
        """Execute live sell transaction"""
        logger.warning(
            "Executing LIVE SELL",
            mint=mint,
            tokens=token_amount,
            reason=reason,
        )

        try:
            # Build sell transaction (similar to buy, but reverse)
            # Placeholder for now

            logger.error("Live trading not fully implemented yet")
            return (False, None)

        except Exception as e:
            logger.error("Sell transaction failed", error=str(e), mint=mint)
            return (False, None)

    async def get_token_balance(self, mint: str) -> float:
        """
        Get token balance for wallet

        Args:
            mint: Token mint address

        Returns:
            Token balance (float)
        """
        if self.mode == "paper":
            # Get from paper engine
            position = self.paper_engine.get_position(mint)
            return position["tokens"] if position else 0.0

        try:
            # Get from on-chain
            mint_pubkey = Pubkey.from_string(mint)

            # Get token account
            response = await self.client.get_token_accounts_by_owner(
                self.keypair.pubkey(),
                {"mint": mint_pubkey},
            )

            if response.value:
                # Parse balance
                account = response.value[0]
                balance = account.account.data.parsed["info"]["tokenAmount"]["uiAmount"]
                return balance

            return 0.0

        except Exception as e:
            logger.error("Error fetching balance", error=str(e), mint=mint)
            return 0.0

    async def get_sol_balance(self) -> float:
        """
        Get SOL balance for wallet

        Returns:
            SOL balance (float)
        """
        if self.mode == "paper":
            return self.paper_engine.get_balance()

        try:
            response = await self.client.get_balance(self.keypair.pubkey())
            lamports = response.value
            return lamports / 1e9

        except Exception as e:
            logger.error("Error fetching SOL balance", error=str(e))
            return 0.0

    async def close(self):
        """Cleanup resources"""
        await self.client.close()
        if self.backup_client:
            await self.backup_client.close()


# Example usage
if __name__ == "__main__":

    async def test_trader():
        """Test trader in paper mode"""
        from src.utils.security import generate_test_keypair

        # Test config
        config = {
            "trading_mode": "paper",
            "solana": {
                "rpc_url": "https://api.mainnet-beta.solana.com",
            },
            "strategy": {
                "entry_amount_sol": 0.1,
                "entry_slippage_bps": 2000,
                "priority_fee_lamports": 400000,
            },
            "pumpfun": {
                "program_id": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
            },
            "paper_trading": {
                "initial_balance_sol": 10.0,
                "simulated_slippage_percent": 2.5,
            },
        }

        # Generate test keypair
        keypair = generate_test_keypair()

        # Initialize trader
        trader = Trader(config, keypair)

        # Test buy
        token_data = {
            "mint": "TEST123456",
            "name": "Test Token",
            "sol_in_curve": 5.0,
        }

        success, result = await trader.buy("TEST123456", token_data)
        print(f"Buy success: {success}")
        print(f"Result: {result}")

        # Check balance
        balance = await trader.get_sol_balance()
        print(f"SOL balance: {balance}")

        await trader.close()

    asyncio.run(test_trader())
