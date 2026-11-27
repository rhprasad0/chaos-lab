import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from .errors import PipelineError

PRODUCT = re.compile(r"^([0-9]{5}[A-Z]{0,2}|DCGS[A-Z0-9]+|SP[0-9]{4})$")
NON_MERCHANDISE = re.compile(
    r"^(POST|DOT|C[23]|D|M|S|CRUK|PADS|GIFT|GIFT_0001_[0-9]+|AMAZONFEE|BANK CHARGES|ADJUST2?)$"
)
VOID_WINDOW = timedelta(minutes=240)

OUTCOMES = (
    "sheet_overlap",
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


def _clean_row(row):
    invoice, code, description, quantity, date, price, customer, country = row
    description = " ".join(description.split()) if description is not None else ""
    return (
        invoice,
        code.strip().upper(),
        description or None,
        quantity,
        date,
        price,
        customer,
        country,
        invoice.startswith("C"),
    )


class _Lot:
    def __init__(self, index, quantity, price, date):
        self.index = index
        self.remaining = quantity
        self.quantity = quantity
        self.price = price
        self.date = date


def _voids(candidates):
    groups = defaultdict(list)
    for index, row in enumerate(candidates):
        if row[6] is not None:
            groups[(row[6], row[1])].append(index)
    dropped = set()
    for indexes in groups.values():
        events = sorted(indexes, key=lambda i: (candidates[i][4], candidates[i][8], i))
        lots = []
        for i in events:
            row = candidates[i]
            if not row[8]:
                lots.append(_Lot(i, row[3], row[5], row[4]))
                continue
            needed = -row[3]
            match = next(
                (
                    lot
                    for lot in reversed(lots)
                    if lot.remaining == lot.quantity
                    and lot.quantity == needed
                    and lot.price == row[5]
                    and lot.date <= row[4]
                    and row[4] - lot.date <= VOID_WINDOW
                ),
                None,
            )
            if match:
                lots.remove(match)
                dropped.update((i, match.index))
                continue
            for lot in reversed(lots):
                if needed <= 0:
                    break
                take = min(lot.remaining, needed)
                lot.remaining -= take
                needed -= take
    return dropped


def clean(sheets):
    counts = Counter({name: 0 for name in OUTCOMES})
    first = Counter(sheets[0])
    survivors = []
    for number, rows in enumerate(sheets):
        for row in rows:
            if number and first[row] > 0:
                first[row] -= 1
                counts["sheet_overlap"] += 1
            else:
                survivors.append(row)
    seen = set()
    candidates = []
    for row in survivors:
        if row in seen:
            counts["duplicate"] += 1
            continue
        seen.add(row)
        invoice, code, _, quantity, _, price, customer, _ = row
        code = code.strip().upper()
        if code in ("TEST001", "TEST002"):
            counts["test"] += 1
        elif invoice.startswith("A") or code == "B":
            counts["bad_debt"] += 1
        elif price == 0 and customer is None:
            counts["stock_adjustment"] += 1
        elif price == 0:
            counts["free_item"] += 1
        elif PRODUCT.match(code):
            if invoice.startswith("C"):
                valid = quantity < 0 < price
            else:
                valid = quantity > 0 and price > 0
            if not valid:
                raise PipelineError(
                    "clean", f"row is neither a sale nor a cancellation: {row!r}"
                )
            candidates.append(_clean_row(row))
        elif NON_MERCHANDISE.match(code):
            counts["non_merchandise"] += 1
        else:
            raise PipelineError("clean", f"stock code {code!r} is neither a product nor a known non-merchandise code: {row!r}")
    dropped = _voids(candidates)
    counts["void"] = len(dropped)
    kept = [row for i, row in enumerate(candidates) if i not in dropped]
    counts["return"] = sum(1 for row in kept if row[8])
    counts["sale"] = len(kept) - counts["return"]
    return kept, dict(counts)
