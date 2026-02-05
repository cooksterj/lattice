#!/usr/bin/env python3
"""
Demo script for Lattice web visualization.

Run with:
    uv run python examples/web_demo.py

Then open http://localhost:8000 in your browser.
"""

from lattice import configure_logging

# Configure logging before defining assets to see registration logs
configure_logging()

import time  # noqa: E402

from lattice import AssetKey, SQLiteRunHistoryStore, asset  # noqa: E402
from lattice.web import serve  # noqa: E402


# Source assets (no dependencies)
@asset
def raw_users() -> list[dict]:
    """Raw user data from CSV."""
    time.sleep(0.3)  # Simulate I/O
    return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


@raw_users.check
def users_not_empty(data: list[dict]) -> bool:
    """Must have at least one user."""
    return len(data) > 0


@raw_users.check
def users_have_ids(data: list[dict]) -> bool:
    """All users must have an id field."""
    return all("id" in user for user in data)


@asset
def raw_orders() -> list[dict]:
    """Raw order data from database."""
    time.sleep(0.2)  # Simulate DB query
    return [{"order_id": 100, "user_id": 1, "amount": 50.0}]


@raw_orders.check
def orders_have_positive_amounts(data: list[dict]) -> bool:
    """All orders must have positive amounts."""
    return all(order.get("amount", 0) > 0 for order in data)


@asset
def raw_products() -> list[dict]:
    """Raw product catalog."""
    time.sleep(0.2)  # Simulate API call
    return [{"sku": "ABC", "price": 25.0}]


@raw_products.check
def products_have_skus(data: list[dict]) -> bool:
    """All products must have SKU codes."""
    return all("sku" in product and product["sku"] for product in data)


@asset
def raw_inventory() -> list[dict]:
    """Raw inventory levels."""
    time.sleep(0.4)  # Simulate warehouse API
    return [{"sku": "ABC", "qty": 100}]


@raw_inventory.check
def inventory_non_negative(data: list[dict]) -> bool:
    """Inventory quantities cannot be negative."""
    return all(item.get("qty", 0) >= 0 for item in data)


@asset
def raw_suppliers() -> list[dict]:
    """Raw supplier data."""
    time.sleep(0.3)  # Simulate supplier API
    return [{"id": 1, "name": "Acme Corp"}]


@asset
def raw_shipping() -> list[dict]:
    """Raw shipping rates."""
    time.sleep(0.35)  # Simulate shipping API
    return [{"zone": "US", "rate": 5.99}]


@raw_shipping.check
def shipping_rates_positive(data: list[dict]) -> bool:
    """Shipping rates must be positive."""
    return all(rate.get("rate", 0) > 0 for rate in data)


# Cleaned/transformed assets
@asset
def cleaned_users(raw_users: list[dict]) -> list[dict]:
    """Users with validated emails."""
    time.sleep(0.2)
    return [u for u in raw_users if u.get("name")]


@cleaned_users.check
def no_users_lost_in_cleaning(data: list[dict]) -> bool:
    """Cleaning should not remove all users."""
    return len(data) > 0


@asset
def cleaned_orders(raw_orders: list[dict]) -> list[dict]:
    """Orders with valid amounts."""
    time.sleep(0.2)
    return [o for o in raw_orders if o.get("amount", 0) > 0]


# Joined assets
@asset
def user_orders(cleaned_users: list[dict], cleaned_orders: list[dict]) -> list[dict]:
    """Orders enriched with user information (slow join operation)."""
    time.sleep(5.0)  # Simulate a slow database join
    user_map = {u["id"]: u for u in cleaned_users}
    return [{**order, "user": user_map.get(order["user_id"])} for order in cleaned_orders]


@user_orders.check
def all_orders_have_users(data: list[dict]) -> bool:
    """Every order should be linked to a user."""
    return all(order.get("user") is not None for order in data)


# Analytics assets (in analytics group)
@asset(key=AssetKey(name="daily_revenue", group="analytics"))
def daily_revenue(user_orders: list[dict]) -> dict:
    """Daily revenue aggregation."""
    time.sleep(0.2)
    total = sum(o.get("amount", 0) for o in user_orders)
    return {"date": "2024-01-15", "revenue": total}


@daily_revenue.check
def revenue_is_non_negative(data: dict) -> bool:
    """Revenue cannot be negative."""
    return data.get("revenue", 0) >= 0


@daily_revenue.check
def revenue_has_date(data: dict) -> bool:
    """Revenue record must have a date."""
    return "date" in data and data["date"] is not None


@asset(key=AssetKey(name="user_stats", group="analytics"))
def user_stats(cleaned_users: list[dict], user_orders: list[dict]) -> dict:
    """User statistics and metrics."""
    time.sleep(0.2)
    return {
        "total_users": len(cleaned_users),
        "users_with_orders": len({o["user_id"] for o in user_orders}),
    }


@user_stats.check
def users_with_orders_not_greater_than_total(data: dict) -> bool:
    """Users with orders cannot exceed total users."""
    return data.get("users_with_orders", 0) <= data.get("total_users", 0)


@asset(key=AssetKey(name="product_performance", group="analytics"))
def product_performance(raw_products: list[dict], user_orders: list[dict]) -> dict:
    """Product sales performance."""
    time.sleep(0.2)
    return {"total_products": len(raw_products), "orders": len(user_orders)}


@asset(key=AssetKey(name="inventory_status", group="analytics"))
def inventory_status(raw_inventory: list[dict], raw_suppliers: list[dict]) -> dict:
    """Current inventory status with supplier info."""
    time.sleep(0.25)
    return {"total_items": sum(i["qty"] for i in raw_inventory), "suppliers": len(raw_suppliers)}


@inventory_status.check
def has_at_least_one_supplier(data: dict) -> bool:
    """Must have at least one supplier."""
    return data.get("suppliers", 0) >= 1


@asset(key=AssetKey(name="shipping_costs", group="analytics"))
def shipping_costs(raw_shipping: list[dict], user_orders: list[dict]) -> dict:
    """Shipping cost analysis."""
    time.sleep(0.2)
    return {"avg_rate": raw_shipping[0]["rate"] if raw_shipping else 0, "orders": len(user_orders)}


# Final dashboard asset - uses deps to specify grouped dependencies
@asset(
    key=AssetKey(name="executive_dashboard", group="analytics"),
    deps={
        "revenue": AssetKey(name="daily_revenue", group="analytics"),
        "stats": AssetKey(name="user_stats", group="analytics"),
        "products": AssetKey(name="product_performance", group="analytics"),
    },
)
def executive_dashboard(revenue: dict, stats: dict, products: dict) -> dict:
    """Executive summary dashboard."""
    time.sleep(0.3)
    return {
        "revenue": revenue,
        "users": stats,
        "products": products,
    }


@executive_dashboard.check
def dashboard_has_all_sections(data: dict) -> bool:
    """Dashboard must have revenue, users, and products sections."""
    return all(key in data for key in ["revenue", "users", "products"])


# Create a history store for run tracking
history_store = SQLiteRunHistoryStore("lattice_demo_runs.db")


if __name__ == "__main__":
    print("Starting Lattice web visualization...")
    print("Open http://localhost:8000 in your browser")
    print("Visit http://localhost:8000/history to see run history")
    print("Press Ctrl+C to stop\n")
    serve(host="127.0.0.1", port=8000, history_store=history_store)
