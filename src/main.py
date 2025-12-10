#!/usr/bin/env python3
"""
PumpFun Bot - Main Entry Point

Orchestrates:
- Configuration loading
- Wallet loading (encrypted)
- Strategy initialization
- Health check server
- Graceful shutdown

Run with:
    python -m src.main
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Dict

import yaml
import structlog

from src.utils.logger import setup_logging
from src.utils.security import load_key
from src.utils.health import HealthCheckServer
from src.core.trader import Trader
from src.core.strategy import TradingStrategy

logger = structlog.get_logger()


class PumpFunBot:
    """Main bot orchestrator"""

    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize bot

        Args:
            config_path: Path to config.yaml
        """
        self.config_path = Path(config_path)
        self.config = None
        self.trader = None
        self.strategy = None
        self.health_server = None
        self.running = False

    def load_config(self) -> Dict:
        """Load configuration from YAML"""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config not found: {self.config_path}. "
                f"Copy config.example.yaml to config.yaml and configure it."
            )

        logger.info(f"Loading config from {self.config_path}")

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        return config

    async def start(self):
        """Start the bot"""
        logger.info("Starting PumpFun Bot")

        # Load config
        self.config = self.load_config()

        # Setup logging
        setup_logging(self.config.get("logging", {}))

        # Log startup info
        logger.info(
            "Bot starting",
            mode=self.config.get("trading_mode", "unknown"),
            version="1.0.0",
        )

        # Load wallet (encrypted)
        try:
            keypair = load_key(self.config)
            logger.info("Wallet loaded", pubkey=str(keypair.pubkey()))
        except Exception as e:
            logger.error("Failed to load wallet", error=str(e))
            logger.error(
                "Run encryption script: python scripts/encrypt_key.py"
            )
            sys.exit(1)

        # Initialize trader
        self.trader = Trader(self.config, keypair)

        # Initialize strategy
        self.strategy = TradingStrategy(self.config, self.trader)

        # Initialize health server
        self.health_server = HealthCheckServer(self.config, self.strategy)

        # Mark as running
        self.running = True

        # Start components
        logger.info("Starting components")

        # Run health server and strategy concurrently
        health_task = asyncio.create_task(self.health_server.start())
        strategy_task = asyncio.create_task(self.strategy.start())

        # Wait for both
        try:
            await asyncio.gather(health_task, strategy_task)
        except asyncio.CancelledError:
            logger.info("Shutdown signal received")

    async def stop(self):
        """Stop the bot gracefully"""
        logger.info("Stopping PumpFun Bot")

        self.running = False

        # Close components
        if self.trader:
            await self.trader.close()

        if self.health_server:
            await self.health_server.close()

        logger.info("Bot stopped")


# Global bot instance for signal handling
bot_instance = None


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {sig}, shutting down...")

    if bot_instance:
        # Schedule shutdown
        asyncio.create_task(bot_instance.stop())


async def main():
    """Main entry point"""
    global bot_instance

    # Create bot
    bot_instance = PumpFunBot()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start bot
    try:
        await bot_instance.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error("Fatal error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        await bot_instance.stop()


if __name__ == "__main__":
    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
        sys.exit(0)
