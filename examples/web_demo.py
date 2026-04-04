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

import logging  # noqa: E402
import pathlib  # noqa: E402
import time  # noqa: E402

from lattice import AssetKey, SQLiteRunHistoryStore, asset, dbt_assets  # noqa: E402
from lattice.web import serve  # noqa: E402

logger = logging.getLogger("lattice")


# Source assets (no dependencies)
@asset
def raw_users() -> list[dict]:
    """Raw user data from CSV."""
    logger.info("Fetching raw user data from CSV source...")
    time.sleep(2.0)  # Simulate I/O
    data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    logger.info("Loaded %d raw users", len(data))
    return data


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
    logger.info("Querying raw orders from database...")
    time.sleep(2.0)  # Simulate DB query
    data = [{"order_id": 100, "user_id": 1, "amount": 50.0}]
    total = sum(o["amount"] for o in data)
    logger.info("Retrieved %d raw orders (total amount: $%.2f)", len(data), total)
    return data


@raw_orders.check
def orders_have_positive_amounts(data: list[dict]) -> bool:
    """All orders must have positive amounts."""
    return all(order.get("amount", 0) > 0 for order in data)


@asset
def raw_products() -> list[dict]:
    """Raw product catalog."""
    logger.info("Fetching product catalog from API...")
    time.sleep(2.0)  # Simulate API call
    data = [{"sku": "ABC", "price": 25.0}]
    logger.info("Loaded %d products from catalog", len(data))
    return data


@raw_products.check
def products_have_skus(data: list[dict]) -> bool:
    """All products must have SKU codes."""
    return all("sku" in product and product["sku"] for product in data)


@asset
def raw_inventory() -> list[dict]:
    """Raw inventory levels."""
    logger.info("Polling warehouse API for inventory levels...")
    time.sleep(2.5)  # Simulate warehouse API
    data = [{"sku": "ABC", "qty": 100}]
    logger.info("Inventory snapshot: %d SKUs, total qty %d", len(data), sum(i["qty"] for i in data))
    return data


@raw_inventory.check
def inventory_non_negative(data: list[dict]) -> bool:
    """Inventory quantities cannot be negative."""
    return all(item.get("qty", 0) >= 0 for item in data)


@asset
def raw_suppliers() -> list[dict]:
    """Raw supplier data."""
    logger.info("Loading supplier directory...")
    time.sleep(2.0)  # Simulate supplier API
    data = [{"id": 1, "name": "Acme Corp"}]
    logger.info("Loaded %d suppliers", len(data))
    return data


@asset
def raw_shipping() -> list[dict]:
    """Raw shipping rates."""
    logger.info("Fetching shipping rate tables...")
    time.sleep(2.0)  # Simulate shipping API
    data = [{"zone": "US", "rate": 5.99}]
    logger.info("Loaded shipping rates for %d zones", len(data))
    return data


@raw_shipping.check
def shipping_rates_positive(data: list[dict]) -> bool:
    """Shipping rates must be positive."""
    return all(rate.get("rate", 0) > 0 for rate in data)


# Cleaned/transformed assets
@asset(deps=["raw_users"])
def cleaned_users(raw_users: list[dict]) -> list[dict]:
    """Users with validated emails."""
    logger.info("Cleaning user records (%d input)...", len(raw_users))
    time.sleep(1.5)
    result = [u for u in raw_users if u.get("name")]
    removed = len(raw_users) - len(result)
    if removed:
        logger.warning("Removed %d users with missing names", removed)
    logger.info("Cleaned users: %d records retained", len(result))
    return result


@cleaned_users.check
def no_users_lost_in_cleaning(data: list[dict]) -> bool:
    """Cleaning should not remove all users."""
    return len(data) > 0


@asset(deps=["raw_orders"])
def cleaned_orders(raw_orders: list[dict]) -> list[dict]:
    """Orders with valid amounts."""
    logger.info("Validating order amounts (%d input)...", len(raw_orders))
    time.sleep(1.5)
    result = [o for o in raw_orders if o.get("amount", 0) > 0]
    removed = len(raw_orders) - len(result)
    if removed:
        logger.warning("Filtered %d orders with non-positive amounts", removed)
    logger.info("Cleaned orders: %d valid records", len(result))
    return result


# Joined assets
@asset(deps=["cleaned_users", "cleaned_orders"])
def user_orders(cleaned_users: list[dict], cleaned_orders: list[dict]) -> list[dict]:
    """Orders enriched with user information (slow join operation)."""
    logger.info("Joining %d orders with %d users...", len(cleaned_orders), len(cleaned_users))
    time.sleep(5.0)  # Simulate a slow database join
    user_map = {u["id"]: u for u in cleaned_users}
    result = [{**order, "user": user_map.get(order["user_id"])} for order in cleaned_orders]
    matched = sum(1 for r in result if r.get("user") is not None)
    logger.info("Join complete: %d/%d orders matched to users", matched, len(result))
    return result


@user_orders.check
def all_orders_have_users(data: list[dict]) -> bool:
    """Every order should be linked to a user."""
    return all(order.get("user") is not None for order in data)


# Analytics assets (in analytics group)
@asset(group="analytics", deps=["user_orders"])
def daily_revenue(user_orders: list[dict]) -> dict:
    """Daily revenue aggregation."""
    logger.info("Aggregating daily revenue from %d orders...", len(user_orders))
    time.sleep(0.2)
    total = sum(o.get("amount", 0) for o in user_orders)
    logger.info("Daily revenue calculated: $%.2f", total)
    return {"date": "2024-01-15", "revenue": total}


@daily_revenue.check
def revenue_is_non_negative(data: dict) -> bool:
    """Revenue cannot be negative."""
    return data.get("revenue", 0) >= 0


@daily_revenue.check
def revenue_has_date(data: dict) -> bool:
    """Revenue record must have a date."""
    return "date" in data and data["date"] is not None


@asset(group="analytics", deps=["cleaned_users", "user_orders"])
def user_stats(cleaned_users: list[dict], user_orders: list[dict]) -> dict:
    """User statistics and metrics."""
    logger.info("Computing user statistics...")
    time.sleep(0.2)
    result = {
        "total_users": len(cleaned_users),
        "users_with_orders": len({o["user_id"] for o in user_orders}),
    }
    logger.info(
        "User stats: %d total, %d with orders", result["total_users"], result["users_with_orders"]
    )
    return result


@user_stats.check
def users_with_orders_not_greater_than_total(data: dict) -> bool:
    """Users with orders cannot exceed total users."""
    return data.get("users_with_orders", 0) <= data.get("total_users", 0)


@asset(group="analytics", deps=["raw_products", "user_orders"])
def product_performance(raw_products: list[dict], user_orders: list[dict]) -> dict:
    """Product sales performance."""
    logger.info("Analyzing product performance across %d products...", len(raw_products))
    time.sleep(0.2)
    result = {"total_products": len(raw_products), "orders": len(user_orders)}
    logger.info(
        "Product performance: %d products, %d orders",
        result["total_products"],
        result["orders"],
    )
    return result


@asset(group="analytics", deps=["raw_inventory", "raw_suppliers"])
def inventory_status(raw_inventory: list[dict], raw_suppliers: list[dict]) -> dict:
    """Current inventory status with supplier info."""
    logger.info(
        "Building inventory status from %d items and %d suppliers...",
        len(raw_inventory),
        len(raw_suppliers),
    )
    time.sleep(0.25)
    result = {"total_items": sum(i["qty"] for i in raw_inventory), "suppliers": len(raw_suppliers)}
    logger.info(
        "Inventory status: %d total items across %d suppliers",
        result["total_items"],
        result["suppliers"],
    )
    return result


@inventory_status.check
def has_at_least_one_supplier(data: dict) -> bool:
    """Must have at least one supplier."""
    return data.get("suppliers", 0) >= 1


@asset(group="analytics", deps=["raw_shipping", "user_orders"])
def shipping_costs(raw_shipping: list[dict], user_orders: list[dict]) -> dict:
    """Shipping cost analysis."""
    logger.info("Calculating shipping costs for %d orders...", len(user_orders))
    time.sleep(0.2)
    avg_rate = raw_shipping[0]["rate"] if raw_shipping else 0
    result = {"avg_rate": avg_rate, "orders": len(user_orders)}
    logger.info("Shipping analysis: avg rate $%.2f across %d orders", avg_rate, len(user_orders))
    return result


# Final dashboard asset — pulls from analytics group AND dbt group
@asset(
    group="analytics",
    deps=[
        AssetKey(name="daily_revenue", group="analytics"),
        AssetKey(name="user_stats", group="analytics"),
        AssetKey(name="product_performance", group="analytics"),
        AssetKey(name="customer_orders", group="jaffle_shop"),
    ],
)
def executive_dashboard(revenue: dict, stats: dict, products: dict, customer_orders: dict) -> dict:
    """Executive summary dashboard."""
    logger.info("Assembling executive dashboard from 4 data sources...")
    time.sleep(0.3)
    result = {
        "revenue": revenue,
        "users": stats,
        "products": products,
        "customer_orders": customer_orders,
    }
    logger.info(
        "Dashboard ready: revenue=$%.2f, %d users, %d products",
        revenue.get("revenue", 0),
        stats.get("total_users", 0),
        products.get("total_products", 0),
    )
    return result


@executive_dashboard.check
def dashboard_has_all_sections(data: dict) -> bool:
    """Dashboard must have revenue, users, and products sections."""
    return all(key in data for key in ["revenue", "users", "products"])


# dbt integration: register all models from the sample manifest as Lattice assets
@dbt_assets(manifest=pathlib.Path(__file__).parent / "sample_manifest.json", group="jaffle_shop")
def jaffle_shop(assets):
    """Jaffle-shop dbt project (sample manifest)."""
    logger.info("Loaded %d dbt assets from jaffle_shop manifest", len(assets))


# Create a history store for run tracking (uses LATTICE_DB_PATH env var or default)
history_store = SQLiteRunHistoryStore()


if __name__ == "__main__":
    print("Starting Lattice web visualization...")
    print("Open http://localhost:8000 in your browser")
    print()
    print("Routes:")
    print("  /               Asset groups landing page")
    print("  /pipeline       Full dependency pipeline")
    print("  /group/{name}   Group detail with scoped graph (e.g. /group/analytics)")
    print("  /assets         Asset catalog")
    print("  /history        Run history")
    print()
    print("Press Ctrl+C to stop\n")
    serve(history_store=history_store)
