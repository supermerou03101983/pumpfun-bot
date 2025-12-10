"""
Tests for token filters

Run with: pytest src/tests/test_filters.py -v
"""

import pytest
from src.core.filters import TokenFilters, FilterResult


@pytest.fixture
def filter_config():
    """Filter configuration fixture"""
    return {
        "min_first_buy_sol": 0.5,
        "require_mint_renounced": True,
        "max_sell_tax_percent": 15,
        "require_sell_simulation": True,
        "min_liquidity_sol": 1.0,
        "banned_name_keywords": ["test", "rug", "scam"],
    }


@pytest.fixture
def filters(filter_config):
    """TokenFilters instance"""
    return TokenFilters(filter_config)


class TestFirstBuyFilter:
    """Test first buy size filter"""

    def test_pass_minimum_buy(self, filters):
        """Should pass when buy meets minimum"""
        result = filters.check_first_buy_size(0.5)
        assert result.passed is True

    def test_pass_above_minimum(self, filters):
        """Should pass when buy exceeds minimum"""
        result = filters.check_first_buy_size(1.0)
        assert result.passed is True

    def test_fail_below_minimum(self, filters):
        """Should fail when buy is below minimum"""
        result = filters.check_first_buy_size(0.3)
        assert result.passed is False
        assert "0.3" in result.reason


class TestMintAuthorityFilter:
    """Test mint authority filter"""

    def test_pass_none(self, filters):
        """Should pass when mint authority is None (renounced)"""
        result = filters.check_mint_authority(None)
        assert result.passed is True

    def test_pass_burned(self, filters):
        """Should pass when mint authority is burned address"""
        result = filters.check_mint_authority("11111111111111111111111111111111")
        assert result.passed is True

    def test_fail_not_renounced(self, filters):
        """Should fail when mint authority exists"""
        result = filters.check_mint_authority("DevWalletAddress123")
        assert result.passed is False
        assert "not renounced" in result.reason


class TestSellTaxFilter:
    """Test sell tax filter"""

    def test_pass_zero_tax(self, filters):
        """Should pass with 0% tax"""
        result = filters.check_sell_tax(0)
        assert result.passed is True

    def test_pass_low_tax(self, filters):
        """Should pass with tax below max"""
        result = filters.check_sell_tax(10)
        assert result.passed is True

    def test_fail_high_tax(self, filters):
        """Should fail with tax above max"""
        result = filters.check_sell_tax(99)
        assert result.passed is False
        assert "99" in result.reason


class TestSellSimulationFilter:
    """Test sell simulation filter"""

    def test_pass_success(self, filters):
        """Should pass when simulation succeeds"""
        result = filters.check_sell_simulation(True)
        assert result.passed is True

    def test_fail_failure(self, filters):
        """Should fail when simulation fails"""
        result = filters.check_sell_simulation(False)
        assert result.passed is False
        assert "honeypot" in result.reason.lower()


class TestTokenNameFilter:
    """Test token name filter"""

    def test_pass_clean_name(self, filters):
        """Should pass with clean name"""
        result = filters.check_token_name("Good Token", "GOOD")
        assert result.passed is True

    def test_fail_banned_keyword_name(self, filters):
        """Should fail with banned keyword in name"""
        result = filters.check_token_name("Test Token", "TST")
        assert result.passed is False
        assert "test" in result.reason.lower()

    def test_fail_banned_keyword_symbol(self, filters):
        """Should fail with banned keyword in symbol"""
        result = filters.check_token_name("Good Token", "RUG")
        assert result.passed is False
        assert "rug" in result.reason.lower()

    def test_fail_suspicious_pattern(self, filters):
        """Should fail with suspicious patterns"""
        # Multiple dollar signs
        result = filters.check_token_name("$$$Token", "MONEY")
        assert result.passed is False

        # Excessive pump claims
        result = filters.check_token_name("100x Token", "PUMP")
        assert result.passed is False


class TestLiquidityFilter:
    """Test liquidity filter"""

    def test_pass_sufficient(self, filters):
        """Should pass with sufficient liquidity"""
        result = filters.check_liquidity(5.0)
        assert result.passed is True

    def test_fail_insufficient(self, filters):
        """Should fail with low liquidity"""
        result = filters.check_liquidity(0.5)
        assert result.passed is False
        assert "0.5" in result.reason


class TestRunAllFilters:
    """Test running all filters together"""

    def test_pass_all_filters(self, filters):
        """Should pass when all filters pass"""
        token_data = {
            "mint": "GoodToken123",
            "name": "Good Token",
            "symbol": "GOOD",
            "first_buy_sol": 1.0,
            "mint_authority": None,
            "sell_tax_percent": 5.0,
            "simulation_success": True,
            "sol_in_curve": 5.0,
        }

        passed, results = filters.run_all_filters(token_data)
        assert passed is True
        assert all(r.passed for r in results)

    def test_fail_one_filter(self, filters):
        """Should fail if any filter fails"""
        token_data = {
            "mint": "BadToken123",
            "name": "Test Token",  # Contains "test" (banned)
            "symbol": "TST",
            "first_buy_sol": 1.0,
            "mint_authority": None,
            "sell_tax_percent": 5.0,
            "simulation_success": True,
            "sol_in_curve": 5.0,
        }

        passed, results = filters.run_all_filters(token_data)
        assert passed is False
        assert any(not r.passed for r in results)

    def test_fail_missing_field(self, filters):
        """Should fail if required field is missing"""
        token_data = {
            "mint": "IncompleteToken",
            "name": "Token",
            # Missing other required fields
        }

        passed, results = filters.run_all_filters(token_data)
        assert passed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
