"""
Token Safety Filters

All filters must pass for a token to be tradeable.
Filters prevent trading scams, rugs, honeypots, and low-quality tokens.
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class FilterResult:
    """Result of a filter check"""

    passed: bool
    reason: Optional[str] = None
    details: Optional[Dict] = None


class TokenFilters:
    """Safety filters for pump.fun tokens"""

    def __init__(self, config: Dict):
        """
        Initialize filters with configuration

        Args:
            config: Filter configuration from config.yaml
        """
        self.config = config
        self.min_first_buy_sol = config.get("min_first_buy_sol", 0.5)
        self.require_mint_renounced = config.get("require_mint_renounced", True)
        self.max_sell_tax_percent = config.get("max_sell_tax_percent", 15)
        self.require_sell_simulation = config.get("require_sell_simulation", True)
        self.min_liquidity_sol = config.get("min_liquidity_sol", 1.0)
        self.banned_keywords = [
            kw.lower() for kw in config.get("banned_name_keywords", [])
        ]

    def check_first_buy_size(self, first_buy_sol: float) -> FilterResult:
        """
        Filter: First buy must be >= minimum SOL

        Rationale: Large first buys indicate serious projects, not spam

        Args:
            first_buy_sol: SOL amount of first buy

        Returns:
            FilterResult
        """
        passed = first_buy_sol >= self.min_first_buy_sol

        return FilterResult(
            passed=passed,
            reason=None
            if passed
            else f"First buy {first_buy_sol} SOL < {self.min_first_buy_sol} SOL minimum",
            details={"first_buy_sol": first_buy_sol, "minimum": self.min_first_buy_sol},
        )

    def check_mint_authority(self, mint_authority: Optional[str]) -> FilterResult:
        """
        Filter: Mint authority must be renounced (None or burned address)

        Rationale: Prevents dev from minting infinite supply (rug)

        Args:
            mint_authority: Mint authority address (None if renounced)

        Returns:
            FilterResult
        """
        if not self.require_mint_renounced:
            return FilterResult(passed=True)

        # Renounced if None or burned address
        burned_addresses = [
            "11111111111111111111111111111111",
            "So11111111111111111111111111111111111111112",
        ]

        renounced = mint_authority is None or mint_authority in burned_addresses

        return FilterResult(
            passed=renounced,
            reason=None if renounced else f"Mint authority not renounced: {mint_authority}",
            details={"mint_authority": mint_authority},
        )

    def check_sell_tax(self, sell_tax_percent: float) -> FilterResult:
        """
        Filter: Sell tax must be < maximum

        Rationale: High sell tax = honeypot (can't sell profitably)

        Args:
            sell_tax_percent: Sell tax percentage (0-100)

        Returns:
            FilterResult
        """
        passed = sell_tax_percent < self.max_sell_tax_percent

        return FilterResult(
            passed=passed,
            reason=None
            if passed
            else f"Sell tax {sell_tax_percent}% >= {self.max_sell_tax_percent}% maximum",
            details={
                "sell_tax_percent": sell_tax_percent,
                "maximum": self.max_sell_tax_percent,
            },
        )

    def check_sell_simulation(self, simulation_success: bool) -> FilterResult:
        """
        Filter: Sell transaction must simulate successfully

        Rationale: If sell simulation fails, it's a honeypot

        Args:
            simulation_success: True if sell simulation succeeded

        Returns:
            FilterResult
        """
        if not self.require_sell_simulation:
            return FilterResult(passed=True)

        return FilterResult(
            passed=simulation_success,
            reason=None if simulation_success else "Sell simulation failed (honeypot)",
            details={"simulation_success": simulation_success},
        )

    def check_token_name(self, name: str, symbol: str) -> FilterResult:
        """
        Filter: Token name/symbol must not contain banned keywords

        Rationale: Scam tokens often have obvious red flags in name

        Args:
            name: Token name
            symbol: Token symbol

        Returns:
            FilterResult
        """
        name_lower = name.lower()
        symbol_lower = symbol.lower()

        # Check for banned keywords
        for keyword in self.banned_keywords:
            if keyword in name_lower or keyword in symbol_lower:
                return FilterResult(
                    passed=False,
                    reason=f"Name/symbol contains banned keyword: '{keyword}'",
                    details={"name": name, "symbol": symbol, "keyword": keyword},
                )

        # Check for suspicious patterns
        suspicious_patterns = [
            r"\$\$\$",  # Multiple dollar signs
            r"🚀{3,}",  # Excessive rocket emojis
            r"x\d{2,}",  # "x100", "x1000" (pump claims)
            r"\d{3,}x",  # "100x", "1000x"
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, name, re.IGNORECASE) or re.search(
                pattern, symbol, re.IGNORECASE
            ):
                return FilterResult(
                    passed=False,
                    reason=f"Name/symbol contains suspicious pattern: {pattern}",
                    details={"name": name, "symbol": symbol, "pattern": pattern},
                )

        return FilterResult(passed=True)

    def check_liquidity(self, sol_in_curve: float) -> FilterResult:
        """
        Filter: Bonding curve must have minimum liquidity

        Rationale: Low liquidity = high slippage + easy to manipulate

        Args:
            sol_in_curve: SOL in bonding curve

        Returns:
            FilterResult
        """
        passed = sol_in_curve >= self.min_liquidity_sol

        return FilterResult(
            passed=passed,
            reason=None
            if passed
            else f"Liquidity {sol_in_curve} SOL < {self.min_liquidity_sol} SOL minimum",
            details={"sol_in_curve": sol_in_curve, "minimum": self.min_liquidity_sol},
        )

    def check_holder_distribution(
        self, top_10_holders_pct: float, dev_hold_pct: float
    ) -> FilterResult:
        """
        Filter: Holder distribution should be reasonable

        Rationale: If dev or few holders own >90%, it's a rug waiting to happen

        Args:
            top_10_holders_pct: % of supply held by top 10 wallets
            dev_hold_pct: % of supply held by dev wallet

        Returns:
            FilterResult
        """
        # Check dev holding (should be < 10%)
        if dev_hold_pct > 10:
            return FilterResult(
                passed=False,
                reason=f"Dev holds {dev_hold_pct}% of supply (> 10% max)",
                details={"dev_hold_pct": dev_hold_pct},
            )

        # Check top 10 concentration (should be < 80%)
        if top_10_holders_pct > 80:
            return FilterResult(
                passed=False,
                reason=f"Top 10 holders own {top_10_holders_pct}% (> 80% max)",
                details={"top_10_holders_pct": top_10_holders_pct},
            )

        return FilterResult(passed=True)

    def run_all_filters(self, token_data: Dict) -> Tuple[bool, List[FilterResult]]:
        """
        Run all filters on a token

        Args:
            token_data: Dict with token metadata and stats

        Returns:
            Tuple of (all_passed, list_of_results)
        """
        results = []

        # Required fields
        required_fields = [
            "first_buy_sol",
            "mint_authority",
            "sell_tax_percent",
            "simulation_success",
            "name",
            "symbol",
            "sol_in_curve",
        ]

        for field in required_fields:
            if field not in token_data:
                logger.warning(f"Missing required field: {field}", token_data=token_data)
                return (
                    False,
                    [FilterResult(passed=False, reason=f"Missing field: {field}")],
                )

        # Run each filter
        results.append(self.check_first_buy_size(token_data["first_buy_sol"]))
        results.append(self.check_mint_authority(token_data["mint_authority"]))
        results.append(self.check_sell_tax(token_data["sell_tax_percent"]))
        results.append(self.check_sell_simulation(token_data["simulation_success"]))
        results.append(self.check_token_name(token_data["name"], token_data["symbol"]))
        results.append(self.check_liquidity(token_data["sol_in_curve"]))

        # Optional: holder distribution (if available)
        if "top_10_holders_pct" in token_data and "dev_hold_pct" in token_data:
            results.append(
                self.check_holder_distribution(
                    token_data["top_10_holders_pct"], token_data["dev_hold_pct"]
                )
            )

        # Check if all passed
        all_passed = all(r.passed for r in results)

        # Log results
        failed_filters = [r for r in results if not r.passed]
        if failed_filters:
            logger.info(
                "Token failed filters",
                mint=token_data.get("mint"),
                failed_count=len(failed_filters),
                reasons=[r.reason for r in failed_filters],
            )
        else:
            logger.info("Token passed all filters", mint=token_data.get("mint"))

        return (all_passed, results)


# Example usage
if __name__ == "__main__":
    # Example filter config
    config = {
        "min_first_buy_sol": 0.5,
        "require_mint_renounced": True,
        "max_sell_tax_percent": 15,
        "require_sell_simulation": True,
        "min_liquidity_sol": 1.0,
        "banned_name_keywords": ["test", "rug", "scam"],
    }

    filters = TokenFilters(config)

    # Example token data (PASS)
    good_token = {
        "mint": "GPNm7x8JhzFKEjzvLH5TnKXjK3LqPJbP3Jgg9Lb7pump",
        "name": "Good Token",
        "symbol": "GOOD",
        "first_buy_sol": 1.0,
        "mint_authority": None,
        "sell_tax_percent": 5.0,
        "simulation_success": True,
        "sol_in_curve": 5.0,
    }

    # Example token data (FAIL)
    bad_token = {
        "mint": "BAD1234567890",
        "name": "Test Rug Token",
        "symbol": "RUG",
        "first_buy_sol": 0.1,
        "mint_authority": "SomeDeveloperAddress123",
        "sell_tax_percent": 99.0,
        "simulation_success": False,
        "sol_in_curve": 0.5,
    }

    print("=== Testing Good Token ===")
    passed, results = filters.run_all_filters(good_token)
    print(f"Passed: {passed}")
    for r in results:
        print(f"  {r}")

    print("\n=== Testing Bad Token ===")
    passed, results = filters.run_all_filters(bad_token)
    print(f"Passed: {passed}")
    for r in results:
        if not r.passed:
            print(f"  ❌ {r.reason}")
