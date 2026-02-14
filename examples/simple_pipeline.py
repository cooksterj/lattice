"""Simple example demonstrating Lattice asset definitions."""

from lattice import asset, get_global_registry


@asset
def raw_numbers() -> list[int]:
    """Source asset with no dependencies."""
    return [1, 2, 3, 4, 5]


@asset(deps=["raw_numbers"])
def doubled(raw_numbers: list[int]) -> list[int]:
    """Depends on raw_numbers - doubles each value."""
    return [x * 2 for x in raw_numbers]


@asset(deps=["doubled"])
def summed(doubled: list[int]) -> int:
    """Depends on doubled - sums all values."""
    return sum(doubled)


@asset(group="analytics", deps=["raw_numbers", "summed"])
def statistics(raw_numbers: list[int], summed: int) -> dict[str, float]:
    """Multiple dependencies with custom key."""
    return {
        "count": len(raw_numbers),
        "sum": summed,
        "mean": summed / len(raw_numbers),
    }


if __name__ == "__main__":
    registry = get_global_registry()

    print("Registered assets:")
    for asset_def in registry:
        deps = [str(d) for d in asset_def.dependencies]
        print(f"  {asset_def.key} -> depends on: {deps or '(none)'}")

    print("\nExecuting assets manually (Phase 2 will add proper execution):")
    raw = raw_numbers()
    print(f"  raw_numbers: {raw}")

    dbl = doubled(raw)
    print(f"  doubled: {dbl}")

    total = summed(dbl)
    print(f"  summed: {total}")

    stats = statistics(raw, total)
    print(f"  statistics: {stats}")
