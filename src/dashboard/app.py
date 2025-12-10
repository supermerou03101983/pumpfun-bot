"""
Streamlit Dashboard

Provides real-time monitoring interface:
- Overview: Win-rate, P&L chart, active positions
- Trades: History table with filters
- Token Monitor: Real-time detected tokens
- Config: Read-only configuration view

Auto-refreshes every 5 seconds.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import redis
import yaml
from pathlib import Path
import time

# Page config
st.set_page_config(
    page_title="PumpFun Bot Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Auto-refresh
st_autorefresh = st.empty()


def load_config():
    """Load configuration from config.yaml"""
    config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"

    if not config_path.exists():
        st.error(f"Config file not found: {config_path}")
        st.stop()

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def connect_redis(config):
    """Connect to Redis"""
    redis_config = config.get("redis", {})
    return redis.Redis(
        host=redis_config.get("host", "localhost"),
        port=redis_config.get("port", 6379),
        db=redis_config.get("db", 0),
        password=redis_config.get("password"),
        decode_responses=True,
    )


def get_daily_pnl(redis_client, days=7):
    """Get P&L for last N days"""
    data = []

    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).date().isoformat()
        key = f"paper_trades:{date}"

        trades = redis_client.hgetall(key)

        if not trades:
            data.append({"date": date, "profit_sol": 0, "trades": 0})
            continue

        total_profit = 0
        trade_count = 0

        for trade_json in trades.values():
            try:
                trade = eval(trade_json)
                if trade.get("type") == "sell":
                    total_profit += trade.get("profit_sol", 0)
                    trade_count += 1
            except:
                continue

        data.append({"date": date, "profit_sol": total_profit, "trades": trade_count})

    return pd.DataFrame(data).sort_values("date")


def get_all_trades(redis_client, days=7):
    """Get all trades for last N days"""
    all_trades = []

    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).date().isoformat()
        key = f"paper_trades:{date}"

        trades = redis_client.hgetall(key)

        for trade_id, trade_json in trades.items():
            try:
                trade = eval(trade_json)
                trade["date"] = date
                trade["trade_id"] = trade_id
                all_trades.append(trade)
            except:
                continue

    return pd.DataFrame(all_trades) if all_trades else pd.DataFrame()


def render_overview_tab(config, redis_client):
    """Render Overview tab"""
    st.header("📊 Overview")

    # Trading mode indicator
    mode = config.get("trading_mode", "unknown")
    if mode == "paper":
        st.info("🔴 **PAPER TRADING MODE** - No real transactions")
    else:
        st.warning("🟢 **LIVE TRADING MODE** - Real transactions enabled")

    st.divider()

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)

    # Get P&L data
    pnl_df = get_daily_pnl(redis_client, days=7)

    with col1:
        total_profit = pnl_df["profit_sol"].sum()
        st.metric(
            "Total P&L (7d)",
            f"{total_profit:+.4f} SOL",
            delta=f"{total_profit:+.4f} SOL",
        )

    with col2:
        total_trades = pnl_df["trades"].sum()
        st.metric("Total Trades (7d)", f"{int(total_trades)}")

    with col3:
        # Calculate win rate
        trades_df = get_all_trades(redis_client, days=7)
        if not trades_df.empty:
            sell_trades = trades_df[trades_df["type"] == "sell"]
            if len(sell_trades) > 0:
                winning = len(sell_trades[sell_trades["profit_sol"] > 0])
                win_rate = (winning / len(sell_trades)) * 100
            else:
                win_rate = 0
        else:
            win_rate = 0

        st.metric("Win Rate (7d)", f"{win_rate:.1f}%")

    with col4:
        # Active positions (mock for now)
        st.metric("Active Positions", "0")

    st.divider()

    # P&L Chart
    st.subheader("Daily P&L")

    if not pnl_df.empty:
        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=pnl_df["date"],
                y=pnl_df["profit_sol"],
                marker_color=[
                    "green" if x > 0 else "red" for x in pnl_df["profit_sol"]
                ],
                name="Profit/Loss",
            )
        )

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Profit/Loss (SOL)",
            height=400,
            showlegend=False,
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No trading data available yet")


def render_trades_tab(redis_client):
    """Render Trades tab"""
    st.header("📋 Trade History")

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        days_filter = st.selectbox("Time Range", [7, 14, 30], index=0)

    with col2:
        type_filter = st.selectbox("Type", ["All", "Buy", "Sell"])

    with col3:
        profit_filter = st.selectbox(
            "Profit Filter", ["All", "Profitable", "Losing"]
        )

    # Get trades
    trades_df = get_all_trades(redis_client, days=days_filter)

    if trades_df.empty:
        st.info("No trades found")
        return

    # Apply filters
    if type_filter != "All":
        trades_df = trades_df[trades_df["type"] == type_filter.lower()]

    if profit_filter == "Profitable":
        trades_df = trades_df[trades_df["profit_sol"] > 0]
    elif profit_filter == "Losing":
        trades_df = trades_df[trades_df["profit_sol"] < 0]

    # Format for display
    if not trades_df.empty:
        display_df = trades_df[
            ["date", "type", "mint", "sol_amount", "tokens_amount", "profit_sol", "profit_pct", "reason"]
        ].copy()

        # Format columns
        display_df["mint"] = display_df["mint"].apply(lambda x: x[:8] + "...")
        display_df["sol_amount"] = display_df["sol_amount"].apply(lambda x: f"{x:.4f}")
        display_df["tokens_amount"] = display_df["tokens_amount"].apply(
            lambda x: f"{x:,.0f}"
        )
        display_df["profit_sol"] = display_df["profit_sol"].apply(
            lambda x: f"{x:+.4f}" if x != 0 else "-"
        )
        display_df["profit_pct"] = display_df["profit_pct"].apply(
            lambda x: f"{x:+.1f}%" if x != 0 else "-"
        )

        # Rename columns
        display_df.columns = [
            "Date",
            "Type",
            "Mint",
            "SOL",
            "Tokens",
            "Profit (SOL)",
            "Profit (%)",
            "Reason",
        ]

        st.dataframe(display_df, use_container_width=True, height=400)

        # Summary stats
        st.divider()
        col1, col2, col3 = st.columns(3)

        with col1:
            total_profit = trades_df["profit_sol"].sum()
            st.metric("Total Profit", f"{total_profit:+.4f} SOL")

        with col2:
            avg_profit = trades_df[trades_df["profit_sol"] != 0]["profit_sol"].mean()
            st.metric("Avg Profit/Loss", f"{avg_profit:+.4f} SOL")

        with col3:
            best_trade = trades_df["profit_sol"].max()
            st.metric("Best Trade", f"{best_trade:+.4f} SOL")
    else:
        st.info("No trades match the selected filters")


def render_monitor_tab():
    """Render Token Monitor tab"""
    st.header("📈 Token Monitor")

    st.info("Real-time token detection will appear here")

    # Mock data for demonstration
    mock_tokens = pd.DataFrame(
        {
            "Mint": ["GPNm...pump", "ABCD...pump", "XYZ1...pump"],
            "Age (s)": [5, 8, 11],
            "SOL in Curve": [2.5, 5.0, 1.2],
            "First Buy": [0.8, 1.5, 0.3],
            "Status": ["✅ Passed", "✅ Passed", "❌ Failed (Low liquidity)"],
        }
    )

    st.dataframe(mock_tokens, use_container_width=True)

    st.caption("Auto-refreshes every 5 seconds")


def render_config_tab(config):
    """Render Config tab"""
    st.header("⚙️ Configuration")

    st.info("Read-only view of current configuration")

    # Display config sections
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Trading Strategy")
        st.code(
            f"""
Entry Amount: {config['strategy']['entry_amount_sol']} SOL
Slippage: {config['strategy']['entry_slippage_bps'] / 100}%
Priority Fee: {config['strategy']['priority_fee_lamports']} lamports

Take Profit: {config['strategy']['take_profit_percentage']}% at +{config['strategy']['take_profit_target']}%
Trailing Stop: {config['strategy']['trailing_stop_percentage']}% (activates at +{config['strategy']['trailing_stop_activation']}%)
Max Hold Time: {config['strategy']['max_hold_time_minutes']} min
        """.strip()
        )

    with col2:
        st.subheader("Filters")
        st.code(
            f"""
Min First Buy: {config['filters']['min_first_buy_sol']} SOL
Max Sell Tax: {config['filters']['max_sell_tax_percent']}%
Min Liquidity: {config['filters']['min_liquidity_sol']} SOL
Require Mint Renounced: {config['filters']['require_mint_renounced']}
        """.strip()
        )

    st.divider()

    # Full config (expandable)
    with st.expander("View Full Configuration"):
        st.json(config)


def main():
    """Main dashboard app"""
    # Title
    st.title("🚀 PumpFun Bot Dashboard")

    # Load config
    try:
        config = load_config()
    except Exception as e:
        st.error(f"Failed to load config: {e}")
        st.stop()

    # Connect to Redis
    try:
        redis_client = connect_redis(config)
        redis_client.ping()
    except Exception as e:
        st.error(f"Failed to connect to Redis: {e}")
        st.info("Ensure Redis is running: `sudo systemctl start redis-server`")
        st.stop()

    # Sidebar
    with st.sidebar:
        st.image(
            "https://via.placeholder.com/150x150.png?text=PumpFun",
            width=150,
        )
        st.title("Navigation")

        # Auto-refresh toggle
        auto_refresh = st.checkbox("Auto-refresh (5s)", value=True)

        if auto_refresh:
            refresh_interval = config.get("dashboard", {}).get(
                "auto_refresh_seconds", 5
            )
            time.sleep(refresh_interval)
            st.rerun()

        st.divider()

        # Bot status
        st.subheader("Bot Status")
        st.success("🟢 Running")
        st.caption(f"Mode: {config.get('trading_mode', 'unknown').upper()}")

        st.divider()

        # Quick stats
        st.subheader("Quick Stats")
        pnl_df = get_daily_pnl(redis_client, days=1)
        today_profit = pnl_df["profit_sol"].sum() if not pnl_df.empty else 0
        st.metric("Today's P&L", f"{today_profit:+.4f} SOL")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "📋 Trades", "📈 Monitor", "⚙️ Config"])

    with tab1:
        render_overview_tab(config, redis_client)

    with tab2:
        render_trades_tab(redis_client)

    with tab3:
        render_monitor_tab()

    with tab4:
        render_config_tab(config)

    # Footer
    st.divider()
    st.caption(
        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"PumpFun Bot v1.0.0"
    )


if __name__ == "__main__":
    main()
