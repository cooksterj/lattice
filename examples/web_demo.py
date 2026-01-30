#!/usr/bin/env python3
"""
Demo script for Lattice web visualization.

Run with:
    uv run python examples/web_demo.py

Then open http://localhost:8000 in your browser.
"""

from lattice import AssetKey, asset
from lattice.web import serve


# Source assets (no dependencies)
@asset
def raw_users() -> list[dict]:
    """Raw user data from CSV."""
    return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


@asset
def raw_orders() -> list[dict]:
    """Raw order data from database."""
    return [{"order_id": 100, "user_id": 1, "amount": 50.0}]


@asset
def raw_products() -> list[dict]:
    """Raw product catalog."""
    return [{"sku": "ABC", "price": 25.0}]


# Cleaned/transformed assets
@asset
def cleaned_users(raw_users: list[dict]) -> list[dict]:
    """Users with validated emails."""
    return [u for u in raw_users if u.get("name")]


@asset
def cleaned_orders(raw_orders: list[dict]) -> list[dict]:
    """Orders with valid amounts."""
    return [o for o in raw_orders if o.get("amount", 0) > 0]


# Joined assets
@asset
def user_orders(cleaned_users: list[dict], cleaned_orders: list[dict]) -> list[dict]:
    """Orders enriched with user information."""
    user_map = {u["id"]: u for u in cleaned_users}
    return [{**order, "user": user_map.get(order["user_id"])} for order in cleaned_orders]


# Analytics assets (in analytics group)
@asset(key=AssetKey(name="daily_revenue", group="analytics"))
def analytics_daily_revenue(user_orders: list[dict]) -> dict:
    """Daily revenue aggregation."""
    total = sum(o.get("amount", 0) for o in user_orders)
    return {"date": "2024-01-15", "revenue": total}


@asset(key=AssetKey(name="user_stats", group="analytics"))
def analytics_user_stats(cleaned_users: list[dict], user_orders: list[dict]) -> dict:
    """User statistics and metrics."""
    return {
        "total_users": len(cleaned_users),
        "users_with_orders": len({o["user_id"] for o in user_orders}),
    }


@asset(key=AssetKey(name="product_performance", group="analytics"))
def analytics_product_performance(raw_products: list[dict], user_orders: list[dict]) -> dict:
    """Product sales performance."""
    return {"total_products": len(raw_products), "orders": len(user_orders)}


# Final dashboard asset
@asset(key=AssetKey(name="executive_dashboard", group="analytics"))
def executive_dashboard(
    analytics_daily_revenue: dict,
    analytics_user_stats: dict,
    analytics_product_performance: dict,
) -> dict:
    """Executive summary dashboard."""
    return {
        "revenue": analytics_daily_revenue,
        "users": analytics_user_stats,
        "products": analytics_product_performance,
    }


if __name__ == "__main__":
    print("Starting Lattice web visualization...")
    print("Open http://localhost:8000 in your browser")
    print("Press Ctrl+C to stop\n")
    serve(host="127.0.0.1", port=8000)
