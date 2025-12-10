"""
Health Check HTTP Server

Exposes /health endpoint for monitoring:
- Bot status
- Trading mode
- Uptime
- Active positions
- Redis connectivity
"""

import time
import asyncio
from typing import Dict
from aiohttp import web
import structlog
import redis.asyncio as aioredis

logger = structlog.get_logger()


class HealthCheckServer:
    """HTTP health check server"""

    def __init__(self, config: Dict, strategy=None):
        """
        Initialize health server

        Args:
            config: Configuration dict
            strategy: TradingStrategy instance (optional)
        """
        self.config = config
        self.strategy = strategy

        self.enabled = config.get("health", {}).get("enabled", True)
        self.port = config.get("health", {}).get("port", 8080)
        self.path = config.get("health", {}).get("path", "/health")

        # Start time
        self.start_time = time.time()

        # Redis client (for health check)
        redis_config = config.get("redis", {})
        self.redis_client = aioredis.from_url(
            f"redis://{redis_config.get('host', 'localhost')}:{redis_config.get('port', 6379)}/{redis_config.get('db', 0)}",
            password=redis_config.get("password"),
            decode_responses=True,
        )

        # Web app
        self.app = web.Application()
        self.app.router.add_get(self.path, self._handle_health)
        self.app.router.add_get("/", self._handle_root)

    async def start(self):
        """Start health check server"""
        if not self.enabled:
            logger.info("Health check server disabled")
            return

        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()

        logger.info(f"Health check server started on port {self.port}")

        # Keep running
        while True:
            await asyncio.sleep(3600)

    async def _handle_root(self, request: web.Request) -> web.Response:
        """Handle root path"""
        return web.Response(
            text="PumpFun Bot - Health check available at /health",
            status=200,
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle health check request"""
        try:
            # Calculate uptime
            uptime_seconds = int(time.time() - self.start_time)

            # Check Redis connectivity
            redis_healthy = await self._check_redis()

            # Get active positions count
            active_positions = 0
            if self.strategy:
                active_positions = len(self.strategy.positions)

            # Build response
            health_data = {
                "status": "healthy" if redis_healthy else "degraded",
                "mode": self.config.get("trading_mode", "unknown"),
                "uptime_seconds": uptime_seconds,
                "active_positions": active_positions,
                "redis_connected": redis_healthy,
                "timestamp": int(time.time()),
            }

            return web.json_response(health_data, status=200)

        except Exception as e:
            logger.error("Health check error", error=str(e))
            return web.json_response(
                {
                    "status": "unhealthy",
                    "error": str(e),
                },
                status=503,
            )

    async def _check_redis(self) -> bool:
        """Check Redis connectivity"""
        try:
            await self.redis_client.ping()
            return True
        except Exception as e:
            logger.error("Redis health check failed", error=str(e))
            return False

    async def close(self):
        """Cleanup resources"""
        await self.redis_client.close()


# Example usage
if __name__ == "__main__":

    async def test_health_server():
        """Test health server"""
        config = {
            "trading_mode": "paper",
            "health": {
                "enabled": True,
                "port": 8080,
                "path": "/health",
            },
            "redis": {
                "host": "localhost",
                "port": 6379,
                "db": 0,
            },
        }

        server = HealthCheckServer(config)

        # Run server
        await server.start()

    # asyncio.run(test_health_server())
    print("Health check module loaded successfully")
