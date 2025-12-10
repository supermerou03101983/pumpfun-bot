"""
Token Detection Engine

Monitors pump.fun for new token launches using:
1. Helius webhooks (primary, real-time)
2. DexScreener API (fallback, polling)

Triggers on first buy transaction (≤12 seconds after token creation).
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
import httpx
import structlog
from aiohttp import web

logger = structlog.get_logger()


class TokenDetector:
    """Detects new pump.fun tokens in real-time"""

    def __init__(self, config: Dict, callback: Callable):
        """
        Initialize detector

        Args:
            config: Configuration dict
            callback: Async function to call when token detected
                     Signature: async def callback(token_data: Dict) -> None
        """
        self.config = config
        self.callback = callback

        # Helius config
        self.helius_api_key = config["helius"]["api_key"]
        self.webhook_id = config["helius"].get("webhook_id")
        self.webhook_port = config["health"]["port"]  # Use same port as health

        # DexScreener config
        self.dexscreener_enabled = config["dexscreener"]["enabled"]
        self.dexscreener_poll_interval = config["dexscreener"]["poll_interval_seconds"]

        # Pump.fun program ID
        self.pumpfun_program_id = config["pumpfun"]["program_id"]

        # Detection window
        self.max_token_age = config["strategy"]["max_token_age_seconds"]

        # Seen tokens (prevent duplicates)
        self.seen_tokens = set()

        # HTTP client
        self.client = httpx.AsyncClient(timeout=30.0)

        # Webhook app
        self.app = web.Application()
        self.app.router.add_post("/webhook", self._handle_webhook)

    async def start(self):
        """Start detection (webhooks + polling)"""
        logger.info("Starting token detector")

        # Start webhook server
        webhook_task = asyncio.create_task(self._run_webhook_server())

        # Start DexScreener polling (if enabled)
        if self.dexscreener_enabled:
            polling_task = asyncio.create_task(self._poll_dexscreener())
            await asyncio.gather(webhook_task, polling_task)
        else:
            await webhook_task

    async def _run_webhook_server(self):
        """Run webhook HTTP server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.webhook_port)
        await site.start()

        logger.info(f"Webhook server listening on port {self.webhook_port}")

        # Keep running
        while True:
            await asyncio.sleep(3600)

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """
        Handle incoming Helius webhook

        Webhook payload format:
        [
            {
                "signature": "tx_signature",
                "timestamp": 1234567890,
                "slot": 123456,
                "accounts": [...],
                "instructions": [...]
            }
        ]
        """
        try:
            payload = await request.json()

            logger.debug("Received webhook", payload_size=len(payload))

            for tx in payload:
                # Extract token mint from transaction
                token_data = await self._parse_transaction(tx)

                if token_data:
                    await self._process_token(token_data)

            return web.Response(status=200, text="OK")

        except Exception as e:
            logger.error("Webhook error", error=str(e))
            return web.Response(status=500, text="Error")

    async def _parse_transaction(self, tx: Dict) -> Optional[Dict]:
        """
        Parse transaction to extract token data

        Args:
            tx: Transaction from webhook

        Returns:
            Token data dict or None
        """
        try:
            # Check if this is a pump.fun transaction
            instructions = tx.get("instructions", [])

            for ix in instructions:
                program_id = ix.get("programId")

                if program_id != self.pumpfun_program_id:
                    continue

                # Extract token mint and first buy details
                accounts = ix.get("accounts", [])
                if len(accounts) < 3:
                    continue

                # In pump.fun, account[1] is typically the token mint
                mint = accounts[1]

                # Get transaction timestamp
                timestamp = tx.get("timestamp")
                if not timestamp:
                    continue

                # Calculate token age
                age_seconds = time.time() - timestamp

                # Skip if too old
                if age_seconds > self.max_token_age:
                    logger.debug(
                        "Token too old",
                        mint=mint,
                        age_seconds=age_seconds,
                        max_age=self.max_token_age,
                    )
                    continue

                # Extract first buy amount (from transaction data)
                sol_amount = self._extract_sol_amount(tx)

                return {
                    "mint": mint,
                    "timestamp": timestamp,
                    "age_seconds": age_seconds,
                    "first_buy_sol": sol_amount,
                    "signature": tx.get("signature"),
                    "source": "helius_webhook",
                }

            return None

        except Exception as e:
            logger.error("Error parsing transaction", error=str(e), tx=tx)
            return None

    def _extract_sol_amount(self, tx: Dict) -> float:
        """
        Extract SOL amount from transaction

        Args:
            tx: Transaction dict

        Returns:
            SOL amount (float)
        """
        try:
            # Look for SOL transfer in inner instructions
            meta = tx.get("meta", {})
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])

            if len(pre_balances) > 1 and len(post_balances) > 1:
                # Calculate difference (lamports)
                diff = pre_balances[0] - post_balances[0]
                # Convert to SOL
                sol_amount = diff / 1e9
                return abs(sol_amount)

            return 0.0

        except Exception:
            return 0.0

    async def _poll_dexscreener(self):
        """Poll DexScreener for new pump.fun tokens (fallback)"""
        logger.info("Starting DexScreener polling")

        while True:
            try:
                # Fetch latest tokens from DexScreener
                url = "https://api.dexscreener.com/latest/dex/search/?q=pump.fun"
                response = await self.client.get(url)

                if response.status_code == 200:
                    data = response.json()
                    pairs = data.get("pairs", [])

                    for pair in pairs:
                        # Extract token data
                        token_data = self._parse_dexscreener_pair(pair)

                        if token_data:
                            await self._process_token(token_data)

                await asyncio.sleep(self.dexscreener_poll_interval)

            except Exception as e:
                logger.error("DexScreener polling error", error=str(e))
                await asyncio.sleep(self.dexscreener_poll_interval)

    def _parse_dexscreener_pair(self, pair: Dict) -> Optional[Dict]:
        """
        Parse DexScreener pair data

        Args:
            pair: Pair data from DexScreener API

        Returns:
            Token data dict or None
        """
        try:
            # Get token mint
            base_token = pair.get("baseToken", {})
            mint = base_token.get("address")

            if not mint:
                return None

            # Get token age (from pairCreatedAt)
            created_at = pair.get("pairCreatedAt")
            if not created_at:
                return None

            # Convert to timestamp
            created_timestamp = int(
                datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
            )

            age_seconds = time.time() - created_timestamp

            # Skip if too old
            if age_seconds > self.max_token_age:
                return None

            # Get liquidity (approximate first buy)
            liquidity = pair.get("liquidity", {})
            usd_liquidity = liquidity.get("usd", 0)

            # Approximate SOL (assume $100/SOL)
            sol_liquidity = usd_liquidity / 100

            return {
                "mint": mint,
                "timestamp": created_timestamp,
                "age_seconds": age_seconds,
                "first_buy_sol": sol_liquidity,
                "name": base_token.get("name"),
                "symbol": base_token.get("symbol"),
                "source": "dexscreener",
            }

        except Exception as e:
            logger.error("Error parsing DexScreener pair", error=str(e), pair=pair)
            return None

    async def _process_token(self, token_data: Dict):
        """
        Process detected token

        Args:
            token_data: Token data dict
        """
        mint = token_data["mint"]

        # Skip if already seen
        if mint in self.seen_tokens:
            return

        # Mark as seen
        self.seen_tokens.add(mint)

        logger.info(
            "New token detected",
            mint=mint,
            age_seconds=token_data["age_seconds"],
            first_buy_sol=token_data.get("first_buy_sol"),
            source=token_data["source"],
        )

        # Call callback
        try:
            await self.callback(token_data)
        except Exception as e:
            logger.error("Error in token callback", error=str(e), mint=mint)

    async def setup_helius_webhook(self):
        """
        Create Helius webhook (if not exists)

        Returns:
            Webhook ID
        """
        if self.webhook_id:
            logger.info("Using existing webhook", webhook_id=self.webhook_id)
            return self.webhook_id

        logger.info("Creating Helius webhook")

        url = f"https://api.helius.xyz/v0/webhooks?api-key={self.helius_api_key}"

        webhook_config = {
            "webhookURL": self.config["helius"]["webhook_url"],
            "transactionTypes": ["Any"],
            "accountAddresses": [self.pumpfun_program_id],
            "webhookType": "enhanced",
        }

        try:
            response = await self.client.post(url, json=webhook_config)

            if response.status_code == 200:
                data = response.json()
                webhook_id = data.get("webhookID")
                logger.info("Webhook created", webhook_id=webhook_id)
                return webhook_id
            else:
                logger.error(
                    "Failed to create webhook",
                    status=response.status_code,
                    response=response.text,
                )
                return None

        except Exception as e:
            logger.error("Error creating webhook", error=str(e))
            return None

    async def close(self):
        """Cleanup resources"""
        await self.client.aclose()


# Example usage
if __name__ == "__main__":

    async def example_callback(token_data: Dict):
        """Example callback function"""
        print(f"Detected token: {token_data['mint']}")
        print(f"  Age: {token_data['age_seconds']:.1f} seconds")
        print(f"  First buy: {token_data.get('first_buy_sol', 0)} SOL")

    # Example config
    config = {
        "helius": {
            "api_key": "YOUR_API_KEY",
            "webhook_id": None,
            "webhook_url": "http://your-server:8080/webhook",
        },
        "dexscreener": {"enabled": True, "poll_interval_seconds": 5},
        "pumpfun": {"program_id": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"},
        "strategy": {"max_token_age_seconds": 12},
        "health": {"port": 8080},
    }

    detector = TokenDetector(config, example_callback)

    # Run detector
    asyncio.run(detector.start())
