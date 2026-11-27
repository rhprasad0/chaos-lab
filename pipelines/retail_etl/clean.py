import re
from collections import Counter, defaultdict
from datetime import timedelta

PRODUCT = re.compile(r"[0-9]{5}[A-Z]{0,2}|DCGS[A-Z0-9]+|SP[0-9]{4}")
NON_MERCHANDISE = re.compile(
    r"POST|DOT|C2|C3|D|M|S|BANK CHARGES|ADJUST2?|AMAZONFEE|PADS|CRUK|GIFT|GIFT_0001_[0-9]+"
)
VOID_WINDOW = timedelta(minutes=240)


class CleanError(Exception):
    pass


class _Lot:
    def __init__(self, index, quantity, price, when):
        self.index = index
        self.quantity = quantity
        self.remaining = quantity
        self.price = price
        self.when = when
        self.voided = False


def _find_voids(candidates):
    groups = defaultdict(list)
    for index, row, is_cancellation in candidates:
        if row[6] is not None:
            groups[(row[6], row[1].strip().upper())].append((row[4], is_cancellation, index, row))
    voided = set()
    for events in groups.values():
        events.sort(key=lambda event: (event[0], event[1], event[2]))
        lots = []
        for when, is_cancellation, index, row in events:
            if not is_cancellation:
                lots.append(_Lot(index, row[3], row[5], when))
                continue
            wanted = -row[3]
            match = next(
                (
                    lot
                    for lot in reversed(lots)
                    if not lot.voided
                    and lot.remaining == lot.quantity
                    and lot.quantity == wanted
                    and lot.price == row[5]
                    and lot.when <= when <= lot.when + VOID_WINDOW
                ),
                None,
            )
            if match:
                match.voided = True
                voided.update((match.index, index))
                continue
            for lot in reversed(lots):
                if wanted == 0:
                    break
                if not lot.voided:
                    taken = min(wanted, lot.remaining)
                    lot.remaining -= taken
                    wanted -= taken
    return voided


def clean(first_sheet, second_sheet):
    counts = Counter()
    first_copies = Counter(first_sheet)
    seen = set()
    candidates = []
    rows = [(row, False) for row in first_sheet] + [(row, True) for row in second_sheet]
    for index, (row, from_second) in enumerate(rows):
        if from_second and first_copies[row] > 0:
            first_copies[row] -= 1
            counts["overlap"] += 1
            continue
        if row in seen:
            counts["duplicate"] += 1
            continue
        seen.add(row)
        invoice, stock_code, price, customer = row[0], row[1].strip().upper(), row[5], row[6]
        if stock_code in ("TEST001", "TEST002"):
            counts["test"] += 1
        elif invoice.startswith("A") or stock_code == "B":
            counts["bad_debt"] += 1
        elif price == 0 and customer is None:
            counts["stock_adjustment"] += 1
        elif price == 0:
            counts["free_item"] += 1
        elif PRODUCT.fullmatch(stock_code):
            candidates.append((index, row, _classify(row)))
        elif NON_MERCHANDISE.fullmatch(stock_code):
            counts["non_merchandise"] += 1
        else:
            raise CleanError(f"unknown stock code {row[1]!r} on invoice {invoice}")
    voided = _find_voids(candidates)
    kept = []
    for index, row, is_cancellation in candidates:
        if index in voided:
            counts["void_cancellation" if is_cancellation else "void_sale"] += 1
        else:
            counts["return" if is_cancellation else "sale"] += 1
            kept.append(_output(row, is_cancellation))
    counts["raw"] = len(rows)
    counts["kept"] = len(kept)
    return kept, dict(counts)


def _classify(row):
    invoice, quantity, price = row[0], row[3], row[5]
    if not invoice.startswith("C") and quantity > 0 and price > 0:
        return False
    if invoice.startswith("C") and quantity < 0 and price > 0:
        return True
    raise CleanError(f"invoice {invoice} is neither a sale nor a cancellation: quantity {quantity}, price {price}")


def _output(row, is_cancellation):
    invoice, stock_code, description, quantity, when, price, customer, country = row
    description = " ".join(description.split()) if description else ""
    return (
        invoice,
        stock_code.strip().upper(),
        description or None,
        quantity,
        when,
        price,
        customer,
        country,
        is_cancellation,
    )
