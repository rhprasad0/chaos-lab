import argparse
import csv
import hashlib
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2025, 1, 1, tzinfo=timezone.utc)
DAYS = 365
CUSTOMERS = 5_000
PRODUCTS = 400
ORDERS = 60_000

FIRST = ["Ava", "Ben", "Chloe", "Dev", "Elena", "Femi", "Grace", "Hiro", "Isla", "Jon",
         "Kira", "Luis", "Maya", "Nate", "Omar", "Priya", "Quinn", "Rosa", "Sam", "Tara"]
LAST = ["Adams", "Baker", "Chen", "Diaz", "Evans", "Fischer", "Garcia", "Hughes", "Ito",
        "Jones", "Khan", "Lopez", "Moore", "Nguyen", "Okafor", "Patel", "Reyes", "Smith"]
CITIES = ["Arlington", "Alexandria", "Fairfax", "Reston", "Herndon", "Leesburg",
          "Manassas", "Vienna", "McLean", "Tysons", "Ashburn", "Springfield"]
SEGMENTS = ["consumer", "small_business", "enterprise"]
CATEGORIES = ["grocery", "home", "outdoor", "electronics", "apparel", "toys", "beauty"]
WORDS = ["Classic", "Deluxe", "Eco", "Compact", "Pro", "Everyday", "Ultra", "Mini", "Max"]
NOUNS = ["Kettle", "Lamp", "Jacket", "Blender", "Backpack", "Speaker", "Towel", "Mug",
         "Drone", "Puzzle", "Serum", "Tent", "Charger", "Skillet", "Sneaker", "Planter"]
STATUSES = [("delivered", 70), ("shipped", 12), ("placed", 6), ("cancelled", 7), ("returned", 5)]
METHODS = ["card", "card", "card", "paypal", "gift_card", "bank_transfer"]

TABLES = {
    "customers": ["customer_id", "email", "full_name", "city", "segment", "updated_at"],
    "products": ["product_id", "sku", "name", "category", "unit_price", "active"],
    "orders": ["order_id", "customer_id", "ordered_at", "status", "currency"],
    "order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price",
                    "discount"],
    "payments": ["payment_id", "order_id", "paid_at", "amount", "method", "status"],
}


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def weighted(rng: random.Random, choices: list[tuple[str, int]]) -> str:
    return rng.choices([c for c, _ in choices], weights=[w for _, w in choices])[0]


def generate(seed: int) -> dict[str, list[list[str]]]:
    rng = random.Random(seed)
    rows: dict[str, list[list[str]]] = {name: [] for name in TABLES}

    signup = {}
    for customer_id in range(1, CUSTOMERS + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        moment = START + timedelta(seconds=rng.randrange(DAYS * 86_400 // 2))
        signup[customer_id] = moment
        email = f"{first.lower()}.{last.lower()}{customer_id}@example.com"
        city, segment = rng.choice(CITIES), weighted(rng, [(s, w) for s, w in zip(SEGMENTS, (80, 15, 5))])
        rows["customers"].append([str(customer_id), email, f"{first} {last}", city, segment, stamp(moment)])
        for _ in range(rng.choices([0, 1, 2], weights=[55, 33, 12])[0]):
            moment += timedelta(seconds=rng.randrange(1, 120 * 86_400))
            if moment >= START + timedelta(days=DAYS):
                break
            change = rng.choice(["email", "city", "segment"])
            if change == "email":
                email = f"{first.lower()}{customer_id}.{rng.randrange(100, 999)}@example.net"
            elif change == "city":
                city = rng.choice([c for c in CITIES if c != city])
            else:
                segment = rng.choice([s for s in SEGMENTS if s != segment])
            rows["customers"].append([str(customer_id), email, f"{first} {last}", city, segment, stamp(moment)])

    prices = {}
    for product_id in range(1, PRODUCTS + 1):
        cents = rng.randrange(199, 49_999)
        prices[product_id] = cents
        name = f"{rng.choice(WORDS)} {rng.choice(NOUNS)}"
        rows["products"].append([str(product_id), f"SKU-{product_id:05d}", name,
                                 rng.choice(CATEGORIES), money(cents),
                                 "true" if rng.random() > 0.05 else "false"])

    item_id = payment_id = 0
    end = START + timedelta(days=DAYS)
    for order_id in range(1, ORDERS + 1):
        customer_id = rng.randrange(1, CUSTOMERS + 1)
        span = int((end - signup[customer_id]).total_seconds())
        ordered_at = signup[customer_id] + timedelta(seconds=rng.randrange(span))
        status = weighted(rng, STATUSES)
        rows["orders"].append([str(order_id), str(customer_id), stamp(ordered_at), status, "USD"])
        total = 0
        for product_id in rng.sample(range(1, PRODUCTS + 1), rng.choices([1, 2, 3, 4, 5], weights=[30, 30, 20, 12, 8])[0]):
            item_id += 1
            quantity = rng.choices([1, 2, 3, 4], weights=[70, 20, 7, 3])[0]
            discount = rng.choice([0, 0, 0, 0, prices[product_id] * quantity // 10])
            total += prices[product_id] * quantity - discount
            rows["order_items"].append([str(item_id), str(order_id), str(product_id), str(quantity),
                                        money(prices[product_id]), money(discount)])
        if status == "placed":
            continue
        paid_at = ordered_at + timedelta(seconds=rng.randrange(30, 3_600))
        if rng.random() < 0.04:
            payment_id += 1
            rows["payments"].append([str(payment_id), str(order_id), stamp(paid_at), money(total),
                                     rng.choice(METHODS), "failed"])
            paid_at += timedelta(seconds=rng.randrange(60, 7_200))
        payment_id += 1
        rows["payments"].append([str(payment_id), str(order_id), stamp(paid_at), money(total),
                                 rng.choice(METHODS), "captured"])
        if status in {"cancelled", "returned"}:
            payment_id += 1
            rows["payments"].append([str(payment_id), str(order_id),
                                     stamp(paid_at + timedelta(days=rng.randrange(1, 20))),
                                     money(total), "refund", "refunded"])
    return rows


def write(rows: dict[str, list[list[str]]], out: Path) -> str:
    out.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    for name, header in TABLES.items():
        path = out / f"{name}.csv"
        with path.open("w", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows[name])
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the synthetic retail tables as CSV.")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(write(generate(args.seed), args.out))


if __name__ == "__main__":
    main()
