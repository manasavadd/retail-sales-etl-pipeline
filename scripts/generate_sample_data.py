"""Generate the SYNTHETIC raw retail sales dataset used by this project.

The data is randomly generated with a fixed seed so the result is reproducible.
It is NOT real company data. Realistic data-quality problems are injected on
purpose (missing values, duplicates, mixed date formats, invalid entries,
inconsistent spellings) so the cleaning step has something meaningful to do.

Usage (from the project root):
    python scripts/generate_sample_data.py
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
N_UNIQUE_ORDERS = 800
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "retail_sales.csv"

# product -> (category, typical unit price)
PRODUCTS = {
    "Wireless Mouse": ("Electronics", 899.0),
    "Bluetooth Speaker": ("Electronics", 2499.0),
    "USB-C Cable": ("Electronics", 299.0),
    "Laptop Stand": ("Electronics", 1299.0),
    "Office Chair": ("Furniture", 7499.0),
    "Standing Desk": ("Furniture", 15999.0),
    "Bookshelf": ("Furniture", 4599.0),
    "Notebook Pack": ("Office Supplies", 249.0),
    "Gel Pen Set": ("Office Supplies", 149.0),
    "Desk Organizer": ("Office Supplies", 599.0),
    "Stapler": ("Office Supplies", 199.0),
    "Cotton T-Shirt": ("Clothing", 599.0),
    "Denim Jeans": ("Clothing", 1799.0),
    "Running Shoes": ("Clothing", 3499.0),
    "Hoodie": ("Clothing", 1499.0),
    "Basmati Rice 5kg": ("Groceries", 649.0),
    "Olive Oil 1L": ("Groceries", 799.0),
    "Green Tea Box": ("Groceries", 349.0),
    "Almonds 500g": ("Groceries", 549.0),
}

REGIONS = ["North", "South", "East", "West", "Central"]
REGION_VARIANTS = {
    "North": ["north", "NORTH ", "N"],
    "South": ["south", " South", "S"],
    "East": ["east", "EAST", "E"],
    "West": ["west", "West ", "W"],
    "Central": ["central", "CENTRAL"],
}
CATEGORY_VARIANTS = {
    "Electronics": ["electronics", "ELECTRONICS ", "Electronic"],
    "Furniture": ["furniture", " Furniture", "FURNITURE"],
    "Office Supplies": ["office supplies", "Office  Supplies", "Stationery"],
    "Clothing": ["clothing", "Apparel", "CLOTHING"],
    "Groceries": ["groceries", "Grocery", "GROCERIES "],
}


def format_date(d: date, rng: random.Random) -> str:
    """Return the date as text using one of several inconsistent formats."""
    style = rng.choices(["iso", "dmy_slash", "d_mon_y", "mon_d_y"], weights=[70, 15, 10, 5])[0]
    if style == "iso":
        return d.strftime("%Y-%m-%d")
    if style == "dmy_slash":
        return d.strftime("%d/%m/%Y")
    if style == "d_mon_y":
        return d.strftime("%d-%b-%Y")
    return d.strftime("%b %d, %Y")


def build_clean_orders(rng: random.Random) -> list:
    """Create well-formed orders before data-quality issues are injected."""
    start, end = date(2024, 1, 1), date(2025, 6, 30)
    span = (end - start).days
    products = list(PRODUCTS)
    orders = []
    for i in range(N_UNIQUE_ORDERS):
        product = rng.choice(products)
        category, base_price = PRODUCTS[product]
        price = round(base_price * rng.uniform(0.95, 1.05), 2)
        qty = rng.choices([1, 2, 3, 4, 5, 6, 8, 10], weights=[35, 25, 15, 10, 6, 4, 3, 2])[0]
        orders.append(
            {
                "Order_ID": f"ORD-{10001 + i}",
                "Order_Date": format_date(start + timedelta(days=rng.randint(0, span)), rng),
                "Customer_ID": f"CUST-{rng.randint(1, 250):04d}",
                "Product": product,
                "Category": category,
                "Quantity": str(qty),
                "Unit_Price": f"{price:.2f}",
                "Region": rng.choice(REGIONS),
            }
        )
    return orders


def inject_issues(orders: list, rng: random.Random) -> list:
    """Corrupt a small share of rows to mimic real-world data quality problems."""
    n = len(orders)
    idx = list(range(n))
    rng.shuffle(idx)
    pick = lambda k: [idx.pop() for _ in range(k)]  # noqa: E731  (take k unused rows)

    for i in pick(20):                      # missing customer id
        orders[i]["Customer_ID"] = ""
    for i in pick(15):                      # missing quantity (cannot be recovered)
        orders[i]["Quantity"] = ""
    for i in pick(15):                      # missing unit price (can be imputed)
        orders[i]["Unit_Price"] = ""
    for i in pick(12):                      # missing region
        orders[i]["Region"] = ""
    for i in pick(12):                      # missing category (recoverable from product)
        orders[i]["Category"] = ""
    for i in pick(6):                       # missing product (cannot be recovered)
        orders[i]["Product"] = ""
    for i in pick(5):                       # missing order id
        orders[i]["Order_ID"] = ""
    for i in pick(10):                      # unparseable date
        orders[i]["Order_Date"] = rng.choice(["not available", "32/13/2024", "TBD", "2024-99-99"])
    for i in pick(4):                       # date far in the future
        orders[i]["Order_Date"] = "2099-01-15"
    for i in pick(12):                      # negative quantity
        orders[i]["Quantity"] = str(-rng.randint(1, 5))
    for i in pick(6):                       # zero quantity
        orders[i]["Quantity"] = "0"
    for i in pick(6):                       # text instead of a number
        orders[i]["Quantity"] = rng.choice(["two", "N/A", "abc"])
    for i in pick(10):                      # zero / negative price (imputed)
        orders[i]["Unit_Price"] = rng.choice(["0", "-499.00", "-1"])
    for i in pick(5):                       # absurd quantity
        orders[i]["Quantity"] = "5000"

    # Inconsistent spelling / casing / whitespace in category and region.
    for row in orders:
        if row["Category"] and rng.random() < 0.20:
            row["Category"] = rng.choice(CATEGORY_VARIANTS[_canonical_category(row["Category"])])
        if row["Region"] and rng.random() < 0.20:
            row["Region"] = rng.choice(REGION_VARIANTS[row["Region"]])
    return orders


def _canonical_category(value: str) -> str:
    for canonical in CATEGORY_VARIANTS:
        if value == canonical:
            return canonical
    return value


def add_duplicates(orders: list, rng: random.Random) -> list:
    """Append exact duplicate rows plus a few same-Order_ID rows with messy casing."""
    with_id = [o for o in orders if o["Order_ID"]]
    exact = [dict(o) for o in rng.sample(with_id, 25)]
    near = []
    for o in rng.sample(with_id, 5):
        copy = dict(o)
        copy["Region"] = copy["Region"].upper() if copy["Region"] else copy["Region"]
        near.append(copy)
    return orders + exact + near


def main() -> None:
    rng = random.Random(SEED)
    orders = inject_issues(build_clean_orders(rng), rng)
    rows = add_duplicates(orders, rng)
    rng.shuffle(rows)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = ["Order_ID", "Order_Date", "Customer_ID", "Product", "Category", "Quantity", "Unit_Price", "Region"]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
