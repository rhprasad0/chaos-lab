import re
from collections import Counter, defaultdict
from datetime import timedelta

INVOICE, STOCK_CODE, DESCRIPTION, QUANTITY, INVOICE_DATE, PRICE, CUSTOMER_ID, COUNTRY = range(8)

OUTCOMES = (
    "sheet_overlap",
    "duplicate",
    "test",
    "bad_debt",
    "stock_adjustment",
    "free_item",
    "non_merchandise",
    "void_sale",
    "void_cancellation",
    "sale",
    "return",
)

PRODUCT_CODE = re.compile(r"^(?:[0-9]{5}[A-Z]{0,2}|DCGS[A-Z0-9]+|SP[0-9]{4})$")
NON_MERCHANDISE_CODE = re.compile(
    r"^(?:POST|DOT|M|C2|D|S|BANK CHARGES|ADJUST2?|AMAZONFEE|PADS|CRUK|GIFT_0001_[0-9]+)$"
)
VOID_WINDOW = timedelta(minutes=240)


class CleaningError(Exception):
    pass


def _drop_reason(row):
    code = row[STOCK_CODE].upper().strip()
    if code in ("TEST001", "TEST002"):
        return "test"
    if row[INVOICE].startswith("A") or code == "B":
        return "bad_debt"
    if row[PRICE] == 0:
        return "stock_adjustment" if row[CUSTOMER_ID] is None else "free_item"
    if not PRODUCT_CODE.match(code):
        if not NON_MERCHANDISE_CODE.match(code):
            raise CleaningError(f"unrecognised stock code {row[STOCK_CODE]!r} on invoice {row[INVOICE]}")
        return "non_merchandise"
    return None


def _is_cancellation(row):
    cancelled = row[INVOICE].startswith("C")
    if cancelled and row[QUANTITY] < 0 < row[PRICE]:
        return True
    if not cancelled and row[QUANTITY] > 0 and row[PRICE] > 0:
        return False
    raise CleaningError(
        f"invoice {row[INVOICE]} stock code {row[STOCK_CODE]!r} is neither a sale nor a cancellation "
        f"(quantity {row[QUANTITY]}, price {row[PRICE]})"
    )


def _resolve_voids(candidates):
    fates = {}
    lots = defaultdict(list)
    cancellations = defaultdict(list)
    for index, row, cancelled in candidates:
        key = (row[CUSTOMER_ID], row[STOCK_CODE].upper().strip())
        if row[CUSTOMER_ID] is None:
            fates[index] = "return" if cancelled else "sale"
        elif cancelled:
            cancellations[key].append((row[INVOICE_DATE], 1, index, row))
        else:
            lots[key].append((row[INVOICE_DATE], 0, index, row))
    for key, sales in lots.items():
        cancellations[key].extend(sales)
    for key, events in cancellations.items():
        remaining = {}
        lot_list = []
        for _, _, index, row in sorted(events, key=lambda event: event[:3]):
            if row[QUANTITY] > 0:
                remaining[index] = row[QUANTITY]
                lot_list.append((index, row))
                fates[index] = "sale"
                continue
            wanted = -row[QUANTITY]
            for lot_index, lot in reversed(lot_list):
                if (
                    lot_index in remaining
                    and remaining[lot_index] == lot[QUANTITY] == wanted
                    and lot[PRICE] == row[PRICE]
                    and timedelta(0) <= row[INVOICE_DATE] - lot[INVOICE_DATE] <= VOID_WINDOW
                ):
                    del remaining[lot_index]
                    lot_list.remove((lot_index, lot))
                    fates[lot_index] = "void_sale"
                    fates[index] = "void_cancellation"
                    break
            else:
                fates[index] = "return"
                for lot_index, lot in reversed(lot_list):
                    if wanted == 0:
                        break
                    taken = min(wanted, remaining[lot_index])
                    remaining[lot_index] -= taken
                    wanted -= taken
    return fates


def clean(sheets):
    first, second = sheets
    outcomes = {}
    rows = []
    seen_in_first = Counter(first)
    seen = set()
    for sheet_number, sheet in enumerate(sheets):
        for row in sheet:
            index = len(rows)
            rows.append(row)
            if sheet_number == 1 and seen_in_first[row] > 0:
                seen_in_first[row] -= 1
                outcomes[index] = "sheet_overlap"
            elif row in seen:
                outcomes[index] = "duplicate"
            else:
                outcomes[index] = _drop_reason(row)
                seen.add(row)
    candidates = [
        (index, rows[index], _is_cancellation(rows[index]))
        for index in range(len(rows))
        if outcomes[index] is None
    ]
    outcomes.update(_resolve_voids(candidates))
    counts = Counter(outcomes.values())
    kept = [
        _normalise(row)
        for index, row in enumerate(rows)
        if outcomes[index] in ("sale", "return")
    ]
    return kept, {name: counts[name] for name in OUTCOMES}


def _normalise(row):
    description = " ".join(row[DESCRIPTION].split()) if row[DESCRIPTION] is not None else ""
    return (
        row[INVOICE],
        row[STOCK_CODE].upper().strip(),
        description or None,
        row[QUANTITY],
        row[INVOICE_DATE],
        row[PRICE],
        row[CUSTOMER_ID],
        row[COUNTRY],
        row[INVOICE].startswith("C"),
    )
