import re
from collections import Counter, defaultdict
from datetime import timedelta

PRODUCT = re.compile(r"^([0-9]{5}[A-Z]{0,2}|DCGS[A-Z0-9]+|SP[0-9]{4})$")
NON_MERCHANDISE = re.compile(
    r"^(POST|DOT|C2|C3|D|M|S|BANK CHARGES|AMAZONFEE|ADJUST2?|CRUK|PADS|GIFT_0001_[0-9]+)$"
)
VOID_WINDOW = timedelta(minutes=240)
OUTCOMES = (
    "overlap",
    "duplicate",
    "test",
    "bad_debt",
    "stock_adjustment",
    "free_item",
    "non_merchandise",
    "void",
    "sale",
    "return",
)


def _screen(row):
    invoice, stock, _, quantity, _, price, customer, _ = row
    code = stock.strip().upper()
    if code in ("TEST001", "TEST002"):
        return "test"
    if invoice.startswith("A") or code == "B":
        return "bad_debt"
    if price == 0:
        return "stock_adjustment" if customer is None else "free_item"
    if not PRODUCT.match(code):
        if NON_MERCHANDISE.match(code):
            return "non_merchandise"
        raise ValueError(f"unrecognised stock code {stock!r} on invoice {invoice}")
    if invoice.startswith("C"):
        if quantity < 0 and price > 0:
            return "cancellation"
    elif quantity > 0 and price > 0:
        return "sale"
    raise ValueError(
        f"invoice {invoice} stock code {stock!r} is neither a sale nor a cancellation: "
        f"quantity {quantity}, price {price}"
    )


def _settle_voids(rows, outcomes, indexes):
    groups = defaultdict(list)
    for i in indexes:
        customer = rows[i][6]
        if customer is not None:
            groups[(customer, rows[i][1].strip().upper())].append(i)
    for members in groups.values():
        members.sort(key=lambda i: (rows[i][4], outcomes[i] == "cancellation"))
        lots = []
        for i in members:
            _, _, _, quantity, moment, price, _, _ = rows[i]
            if outcomes[i] == "sale":
                lots.append({"row": i, "time": moment, "quantity": quantity, "left": quantity})
                continue
            for lot in reversed(lots):
                if (
                    lot["left"] == lot["quantity"] == -quantity
                    and rows[lot["row"]][5] == price
                    and timedelta(0) <= moment - lot["time"] <= VOID_WINDOW
                ):
                    outcomes[i] = outcomes[lot["row"]] = "void"
                    lots.remove(lot)
                    break
            else:
                need = -quantity
                for lot in reversed(lots):
                    taken = min(lot["left"], need)
                    lot["left"] -= taken
                    need -= taken
                    if not need:
                        break


def clean(first, second):
    rows = first + second
    outcomes = [None] * len(rows)
    in_first = Counter(first)
    for i in range(len(first), len(rows)):
        if in_first[rows[i]]:
            in_first[rows[i]] -= 1
            outcomes[i] = "overlap"
    seen = set()
    for i, row in enumerate(rows):
        if outcomes[i]:
            continue
        if row in seen:
            outcomes[i] = "duplicate"
        seen.add(row)
    pending = []
    for i, row in enumerate(rows):
        if not outcomes[i]:
            outcomes[i] = _screen(row)
            pending.append(i)
    _settle_voids(rows, outcomes, pending)
    kept = []
    for i, row in enumerate(rows):
        if outcomes[i] == "cancellation":
            outcomes[i] = "return"
        if outcomes[i] in ("sale", "return"):
            invoice, stock, description, quantity, moment, price, customer, country = row
            description = " ".join(description.split()) if description is not None else ""
            kept.append(
                (
                    invoice,
                    stock.strip().upper(),
                    description or None,
                    quantity,
                    moment,
                    price,
                    customer,
                    country,
                    outcomes[i] == "return",
                )
            )
    return kept, Counter(outcomes)
