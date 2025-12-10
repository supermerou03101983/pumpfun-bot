"""
Tests for paper trading engine

Run with: pytest src/tests/test_paper_engine.py -v
"""

import pytest
from unittest.mock import Mock, patch
from src.utils.paper_engine import PaperTradingEngine


@pytest.fixture
def config():
    """Configuration fixture"""
    return {
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


@pytest.fixture
def engine(config):
    """PaperTradingEngine instance with mocked Redis"""
    with patch("redis.Redis"):
        engine = PaperTradingEngine(config)
        engine.redis = Mock()  # Mock Redis client
        return engine


class TestInitialization:
    """Test engine initialization"""

    def test_initial_balance(self, engine):
        """Should initialize with correct balance"""
        assert engine.balance_sol == 10.0

    def test_empty_positions(self, engine):
        """Should start with no positions"""
        assert len(engine.positions) == 0


class TestBuyExecution:
    """Test buy transaction simulation"""

    def test_successful_buy(self, engine):
        """Should execute buy and update balance"""
        result = engine.execute_buy(
            mint="TEST123",
            sol_amount=0.1,
            tokens_received=100000,
            price=0.000001,
            metadata={"name": "Test Token"},
        )

        # Check result
        assert result["type"] == "buy"
        assert result["sol_spent"] == 0.1
        assert result["tokens_received"] == 100000

        # Check balance deducted
        expected_balance = 10.0 - 0.1 - 0.00001 - 0.0004
        assert engine.balance_sol == pytest.approx(expected_balance, rel=1e-6)

        # Check position created
        assert "TEST123" in engine.positions
        assert engine.positions["TEST123"]["tokens"] == 100000

    def test_buy_insufficient_balance(self, engine):
        """Should raise error on insufficient balance"""
        with pytest.raises(ValueError, match="Insufficient balance"):
            engine.execute_buy(
                mint="TEST123",
                sol_amount=20.0,  # More than available
                tokens_received=100000,
                price=0.0002,
                metadata={},
            )


class TestSellExecution:
    """Test sell transaction simulation"""

    def test_successful_sell_profit(self, engine):
        """Should execute sell with profit"""
        # First, buy
        engine.execute_buy(
            mint="TEST123",
            sol_amount=0.1,
            tokens_received=100000,
            price=0.000001,
            metadata={},
        )

        # Then, sell at profit
        result = engine.execute_sell(
            mint="TEST123",
            tokens_sold=100000,
            sol_received=0.15,  # Profit
            price=0.0000015,
            reason="Take profit",
        )

        # Check result
        assert result["type"] == "sell"
        assert result["tokens_sold"] == 100000
        assert result["profit_sol"] > 0
        assert result["profit_pct"] > 0
        assert result["reason"] == "Take profit"

        # Check position removed
        assert "TEST123" not in engine.positions

        # Check balance increased
        assert engine.balance_sol > 10.0

    def test_successful_sell_loss(self, engine):
        """Should execute sell with loss"""
        # Buy
        engine.execute_buy(
            mint="TEST123",
            sol_amount=0.1,
            tokens_received=100000,
            price=0.000001,
            metadata={},
        )

        # Sell at loss
        result = engine.execute_sell(
            mint="TEST123",
            tokens_sold=100000,
            sol_received=0.05,  # Loss
            price=0.0000005,
            reason="Stop loss",
        )

        # Check result
        assert result["profit_sol"] < 0
        assert result["profit_pct"] < 0

    def test_partial_sell(self, engine):
        """Should handle partial sell"""
        # Buy
        engine.execute_buy(
            mint="TEST123",
            sol_amount=0.1,
            tokens_received=100000,
            price=0.000001,
            metadata={},
        )

        # Sell half
        engine.execute_sell(
            mint="TEST123",
            tokens_sold=50000,
            sol_received=0.075,
            price=0.0000015,
            reason="Partial exit",
        )

        # Check position still exists with remaining tokens
        assert "TEST123" in engine.positions
        assert engine.positions["TEST123"]["tokens"] == 50000

    def test_sell_no_position(self, engine):
        """Should raise error when no position exists"""
        with pytest.raises(ValueError, match="No position found"):
            engine.execute_sell(
                mint="NONEXISTENT",
                tokens_sold=100000,
                sol_received=0.1,
                price=0.000001,
                reason="Test",
            )

    def test_sell_insufficient_tokens(self, engine):
        """Should raise error on insufficient tokens"""
        # Buy
        engine.execute_buy(
            mint="TEST123",
            sol_amount=0.1,
            tokens_received=100000,
            price=0.000001,
            metadata={},
        )

        # Try to sell more than owned
        with pytest.raises(ValueError, match="Insufficient tokens"):
            engine.execute_sell(
                mint="TEST123",
                tokens_sold=200000,  # More than owned
                sol_received=0.2,
                price=0.000001,
                reason="Test",
            )


class TestPositionManagement:
    """Test position tracking"""

    def test_get_position(self, engine):
        """Should retrieve position"""
        engine.execute_buy(
            mint="TEST123",
            sol_amount=0.1,
            tokens_received=100000,
            price=0.000001,
            metadata={},
        )

        position = engine.get_position("TEST123")
        assert position is not None
        assert position["tokens"] == 100000
        assert position["sol_invested"] == 0.1

    def test_get_position_not_found(self, engine):
        """Should return None for nonexistent position"""
        position = engine.get_position("NONEXISTENT")
        assert position is None

    def test_get_all_positions(self, engine):
        """Should retrieve all positions"""
        # Create multiple positions
        engine.execute_buy(
            mint="TEST1", sol_amount=0.1, tokens_received=100000, price=0.000001, metadata={}
        )
        engine.execute_buy(
            mint="TEST2", sol_amount=0.2, tokens_received=200000, price=0.000001, metadata={}
        )

        positions = engine.get_all_positions()
        assert len(positions) == 2


class TestBalance:
    """Test balance tracking"""

    def test_get_balance(self, engine):
        """Should return current balance"""
        assert engine.get_balance() == 10.0

    def test_balance_after_trades(self, engine):
        """Should track balance through trades"""
        initial = engine.get_balance()

        # Buy
        engine.execute_buy(
            mint="TEST123",
            sol_amount=0.1,
            tokens_received=100000,
            price=0.000001,
            metadata={},
        )

        after_buy = engine.get_balance()
        assert after_buy < initial

        # Sell at profit
        engine.execute_sell(
            mint="TEST123",
            tokens_sold=100000,
            sol_received=0.15,
            price=0.0000015,
            reason="Profit",
        )

        after_sell = engine.get_balance()
        assert after_sell > after_buy
        assert after_sell > initial  # Net profit


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
