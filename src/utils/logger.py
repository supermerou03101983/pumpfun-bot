"""
Structured Logging Configuration

Uses structlog for JSON-formatted logs:
- stdout (for systemd journalctl)
- file (for long-term storage)
- Grafana Loki compatible
"""

import sys
import logging
from pathlib import Path
from typing import Optional
import structlog
from pythonjsonlogger import jsonlogger


def setup_logging(config: dict) -> None:
    """
    Configure structured logging

    Args:
        config: Logging configuration from config.yaml
    """
    log_level_str = config.get("level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Setup stdlib logging
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers = []

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if config.get("json_format", True):
        # JSON formatter for structured logs
        json_formatter = jsonlogger.JsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s"
        )
        console_handler.setFormatter(json_formatter)
    else:
        # Plain text formatter
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(console_handler)

    # File handler (if enabled)
    if config.get("file_enabled", True):
        log_file_path = Path(config.get("file_path", "logs/pumpfun_bot.log"))

        # Create log directory if needed
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Rotating file handler
        from logging.handlers import RotatingFileHandler

        max_bytes = config.get("max_file_size_mb", 100) * 1024 * 1024
        backup_count = config.get("backup_count", 5)

        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(log_level)

        if config.get("json_format", True):
            file_handler.setFormatter(json_formatter)
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

        root_logger.addHandler(file_handler)

    # Log startup message
    logger = structlog.get_logger()
    logger.info(
        "Logging configured",
        level=log_level_str,
        json_format=config.get("json_format", True),
        file_enabled=config.get("file_enabled", True),
    )


def get_logger(name: Optional[str] = None):
    """
    Get a logger instance

    Args:
        name: Logger name (defaults to caller's module)

    Returns:
        structlog logger
    """
    return structlog.get_logger(name)


# Example usage
if __name__ == "__main__":
    # Test logging configuration
    config = {
        "level": "DEBUG",
        "json_format": True,
        "file_enabled": False,
    }

    setup_logging(config)

    logger = get_logger(__name__)

    logger.debug("Debug message", key="value")
    logger.info("Info message", user="alice", action="login")
    logger.warning("Warning message", attempts=3)
    logger.error("Error message", error_code=500)

    try:
        raise ValueError("Test exception")
    except Exception as e:
        logger.exception("Exception caught", error=str(e))
