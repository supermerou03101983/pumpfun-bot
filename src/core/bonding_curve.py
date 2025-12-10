"""
Pump.fun Bonding Curve Pricing Engine

Implements the constant product AMM formula used by pump.fun:
    x * y = k

Where:
    x = virtual_sol_reserves
    y = virtual_token_reserves
    k = constant product

Price calculation:
    price = virtual_sol_reserves / virtual_token_reserves
"""

import math
from typing import Tuple
from decimal import Decimal, getcontext

# Set precision for decimal calculations
getcontext().prec = 18


class BondingCurve:
    """Pump.fun bonding curve implementation"""

    def __init__(
        self,
        initial_virtual_sol_reserves: float = 30.0,
        initial_virtual_token_reserves: float = 1073000000.0,
        initial_real_token_reserves: float = 793100000.0,
    ):
        """
        Initialize bonding curve with pump.fun parameters

        Args:
            initial_virtual_sol_reserves: Virtual SOL reserves at start
            initial_virtual_token_reserves: Virtual token reserves at start
            initial_real_token_reserves: Real token reserves at start
        """
        self.initial_virtual_sol_reserves = Decimal(str(initial_virtual_sol_reserves))
        self.initial_virtual_token_reserves = Decimal(
            str(initial_virtual_token_reserves)
        )
        self.initial_real_token_reserves = Decimal(str(initial_real_token_reserves))

        # Calculate constant product (k = x * y)
        self.k = self.initial_virtual_sol_reserves * self.initial_virtual_token_reserves

    def get_price(
        self, sol_in_curve: float, tokens_sold: float = 0
    ) -> Tuple[float, float]:
        """
        Calculate current token price

        Args:
            sol_in_curve: Current SOL in bonding curve
            tokens_sold: Tokens already sold from curve

        Returns:
            Tuple of (price_in_sol, market_cap_sol)
        """
        # Current reserves
        virtual_sol = self.initial_virtual_sol_reserves + Decimal(str(sol_in_curve))
        virtual_tokens = self.initial_virtual_token_reserves - Decimal(
            str(tokens_sold)
        )

        # Prevent division by zero
        if virtual_tokens <= 0:
            return (float("inf"), float("inf"))

        # Price = SOL / Tokens
        price = float(virtual_sol / virtual_tokens)

        # Market cap = price * total_supply
        total_supply = float(self.initial_real_token_reserves)
        market_cap = price * total_supply

        return (price, market_cap)

    def calculate_tokens_out(
        self, sol_amount: float, current_sol_in_curve: float
    ) -> Tuple[float, float]:
        """
        Calculate tokens received for SOL input (buy)

        Uses formula:
            tokens_out = virtual_tokens - (k / (virtual_sol + sol_in))

        Args:
            sol_amount: SOL to spend
            current_sol_in_curve: Current SOL in curve

        Returns:
            Tuple of (tokens_out, effective_price)
        """
        sol_in = Decimal(str(sol_amount))
        current_sol = Decimal(str(current_sol_in_curve))

        # Current virtual reserves
        virtual_sol = self.initial_virtual_sol_reserves + current_sol
        virtual_tokens = self.k / virtual_sol

        # New reserves after buy
        new_virtual_sol = virtual_sol + sol_in
        new_virtual_tokens = self.k / new_virtual_sol

        # Tokens received
        tokens_out = virtual_tokens - new_virtual_tokens

        # Effective price
        effective_price = float(sol_in / tokens_out) if tokens_out > 0 else 0

        return (float(tokens_out), effective_price)

    def calculate_sol_out(
        self, token_amount: float, current_sol_in_curve: float
    ) -> Tuple[float, float]:
        """
        Calculate SOL received for token input (sell)

        Uses formula:
            sol_out = virtual_sol - (k / (virtual_tokens + tokens_in))

        Args:
            token_amount: Tokens to sell
            current_sol_in_curve: Current SOL in curve

        Returns:
            Tuple of (sol_out, effective_price)
        """
        tokens_in = Decimal(str(token_amount))
        current_sol = Decimal(str(current_sol_in_curve))

        # Current virtual reserves
        virtual_sol = self.initial_virtual_sol_reserves + current_sol
        virtual_tokens = self.k / virtual_sol

        # New reserves after sell
        new_virtual_tokens = virtual_tokens + tokens_in
        new_virtual_sol = self.k / new_virtual_tokens

        # SOL received
        sol_out = virtual_sol - new_virtual_sol

        # Effective price
        effective_price = float(sol_out / tokens_in) if tokens_in > 0 else 0

        return (float(sol_out), effective_price)

    def calculate_price_impact(
        self, sol_amount: float, current_sol_in_curve: float, is_buy: bool = True
    ) -> float:
        """
        Calculate price impact percentage for a trade

        Args:
            sol_amount: SOL amount for trade
            current_sol_in_curve: Current SOL in curve
            is_buy: True for buy, False for sell

        Returns:
            Price impact as percentage (e.g., 5.2 for 5.2%)
        """
        # Get current price
        current_price, _ = self.get_price(current_sol_in_curve)

        if is_buy:
            # Calculate effective price for buy
            _, effective_price = self.calculate_tokens_out(
                sol_amount, current_sol_in_curve
            )
        else:
            # For sell, need to convert SOL to tokens first
            tokens_out, _ = self.calculate_tokens_out(sol_amount, current_sol_in_curve)
            _, effective_price = self.calculate_sol_out(tokens_out, current_sol_in_curve)

        # Price impact = (effective_price - current_price) / current_price * 100
        if current_price == 0:
            return 0

        price_impact = abs((effective_price - current_price) / current_price * 100)
        return price_impact

    def simulate_trade_with_slippage(
        self,
        sol_amount: float,
        current_sol_in_curve: float,
        slippage_bps: int,
        is_buy: bool = True,
    ) -> dict:
        """
        Simulate trade with slippage applied

        Args:
            sol_amount: SOL amount
            current_sol_in_curve: Current SOL in curve
            slippage_bps: Slippage in basis points (e.g., 2000 = 20%)
            is_buy: True for buy, False for sell

        Returns:
            Dict with trade details
        """
        slippage_multiplier = 1 + (slippage_bps / 10000)

        if is_buy:
            # Calculate tokens received
            tokens_out, effective_price = self.calculate_tokens_out(
                sol_amount, current_sol_in_curve
            )

            # Apply slippage (receive fewer tokens)
            tokens_out_with_slippage = tokens_out / slippage_multiplier

            return {
                "type": "buy",
                "sol_in": sol_amount,
                "tokens_out": tokens_out,
                "tokens_out_with_slippage": tokens_out_with_slippage,
                "effective_price": effective_price,
                "slippage_bps": slippage_bps,
                "price_impact_pct": self.calculate_price_impact(
                    sol_amount, current_sol_in_curve, is_buy=True
                ),
            }
        else:
            # For sell, sol_amount is actually the token amount
            sol_out, effective_price = self.calculate_sol_out(
                sol_amount, current_sol_in_curve
            )

            # Apply slippage (receive less SOL)
            sol_out_with_slippage = sol_out / slippage_multiplier

            return {
                "type": "sell",
                "tokens_in": sol_amount,
                "sol_out": sol_out,
                "sol_out_with_slippage": sol_out_with_slippage,
                "effective_price": effective_price,
                "slippage_bps": slippage_bps,
                "price_impact_pct": self.calculate_price_impact(
                    sol_out, current_sol_in_curve, is_buy=False
                ),
            }


# Factory function for easy initialization
def create_bonding_curve() -> BondingCurve:
    """Create bonding curve with default pump.fun parameters"""
    return BondingCurve()


# Example usage
if __name__ == "__main__":
    curve = create_bonding_curve()

    # Example: Buy 0.1 SOL worth of tokens when curve has 5 SOL
    sol_in_curve = 5.0
    buy_amount = 0.1

    print("=== Bonding Curve Simulation ===")
    print(f"Current SOL in curve: {sol_in_curve}")
    print()

    # Current price
    price, mcap = curve.get_price(sol_in_curve)
    print(f"Current Price: {price:.12f} SOL")
    print(f"Market Cap: {mcap:.2f} SOL")
    print()

    # Buy simulation
    buy_sim = curve.simulate_trade_with_slippage(
        buy_amount, sol_in_curve, slippage_bps=2000, is_buy=True
    )
    print(f"Buy {buy_amount} SOL:")
    print(f"  Tokens out (no slippage): {buy_sim['tokens_out']:,.0f}")
    print(f"  Tokens out (20% slippage): {buy_sim['tokens_out_with_slippage']:,.0f}")
    print(f"  Effective price: {buy_sim['effective_price']:.12f} SOL")
    print(f"  Price impact: {buy_sim['price_impact_pct']:.2f}%")
