import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
from openpyxl import load_workbook

SHEETS = ("Year 2009-2010", "Year 2010-2011")
HEADER = ("Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country")
PRODUCT_CODE = re.compile(r"^([0-9]{5}[A-Z]{0,2}|DCGS[A-Z0-9]+|SP[0-9]{4})$")
VOID_WINDOW = timedelta(minutes=240)
PRICE_TYPE = pa.decimal128(18, 4)
SCHEMA = pa.schema(
    [
        ("invoice", pa.string()),
        ("stock_code", pa.string()),
        ("description", pa.string()),
        ("quantity", pa.int32()),
        ("invoice_date", pa.timestamp("us")),
        ("price", PRICE_TYPE),
        ("customer_id", pa.int32()),
        ("country", pa.string()),
        ("is_cancellation", pa.bool_()),
    ]
)


def _text(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"\.0$", "", str(value))


def _integer(value):
    if value is None or value == "":
        return None
    number = Decimal(str(value).strip())
    if number != number.to_integral_value():
        raise ValueError(f"{value!r} is not a whole number")
    return int(number)


def _price(value):
    if value is None or value == "":
        return None
    return Decimal(repr(value) if isinstance(value, float) else str(value).strip())


def _date(value):
    return value if value is None or isinstance(value, datetime) else datetime.fromisoformat(str(value).strip())


def read_sheet(workbook, name):
    sheet = workbook[name]
    rows = sheet.iter_rows(max_col=len(HEADER), values_only=True)
    header = tuple(str(cell).strip() if cell is not None else None for cell in next(rows))
    if header != HEADER:
        raise ValueError(f"sheet {name!r} has header {header}, expected {HEADER}")
    parsed = []
    for number, raw in enumerate(rows, start=2):
        if all(cell is None for cell in raw):
            continue
        try:
            invoice, stock, description, quantity, date, price, customer, country = raw
            parsed.append(
                (
                    _text(invoice),
                    _text(stock),
                    description,
                    _integer(quantity),
                    _date(date),
                    _price(price),
                    _integer(customer),
                    country,
                )
            )
        except (ValueError, ArithmeticError) as error:
            raise ValueError(f"sheet {name!r} row {number}: {error}") from error
    return parsed


def read_workbook(path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return [read_sheet(workbook, name) for name in SHEETS]
    finally:
        workbook.close()


def _normalise(row):
    invoice, stock, description, quantity, date, price, customer, country = row
    code = (stock or "").strip().upper()
    cleaned = " ".join(description.split()) if isinstance(description, str) else description
    return {
        "invoice": invoice,
        "stock_code": code,
        "description": cleaned or None,
        "quantity": quantity,
        "invoice_date": date,
        "price": price,
        "customer_id": customer,
        "country": country,
        "is_cancellation": (invoice or "").startswith("C"),
    }


def _drop_reason(row, record):
    code = record["stock_code"]
    price = record["price"]
    if code in ("TEST001", "TEST002"):
        return "test"
    if (row[0] or "").startswith("A") or code == "B":
        return "bad_debt"
    if price == 0:
        return "stock_adjustment" if record["customer_id"] is None else "free_item"
    if not code:
        raise ValueError(f"row without a stock code: {row}")
    if not PRODUCT_CODE.match(code):
        return "non_merchandise"
    return None


def _check_kind(row, record):
    quantity, price = record["quantity"], record["price"]
    if quantity is None or price is None or record["invoice_date"] is None:
        raise ValueError(f"row with a missing quantity, price or date: {row}")
    if not record["is_cancellation"] and quantity > 0 and price > 0:
        return "sale"
    if record["is_cancellation"] and quantity < 0 and price > 0:
        return "cancellation"
    raise ValueError(f"row is neither a sale nor a cancellation: {row}")


def _settle(events):
    lots = []
    outcomes = {}
    for _, _, index, record in events:
        if not record["is_cancellation"]:
            lots.append({"index": index, "record": record, "left": record["quantity"], "used": 0, "void": False})
            continue
        wanted = -record["quantity"]
        for lot in reversed(lots):
            sale = lot["record"]
            if (
                not lot["void"]
                and lot["used"] == 0
                and sale["quantity"] == wanted
                and sale["price"] == record["price"]
                and record["invoice_date"] - sale["invoice_date"] <= VOID_WINDOW
            ):
                lot["void"] = True
                lot["left"] = 0
                outcomes[lot["index"]] = outcomes[index] = "void"
                break
        else:
            outcomes[index] = "return"
            for lot in reversed(lots):
                if wanted == 0:
                    break
                take = min(wanted, lot["left"])
                lot["left"] -= take
                lot["used"] += take
                wanted -= take
    return outcomes


def clean(first, second):
    rows = [(row, "first") for row in first] + [(row, "second") for row in second]
    outcome = [None] * len(rows)
    in_first = Counter(first)
    seen = set()
    candidates = {}
    for index, (row, sheet) in enumerate(rows):
        if sheet == "second" and in_first[row] > 0:
            in_first[row] -= 1
            outcome[index] = "overlap"
        elif row in seen:
            outcome[index] = "duplicate"
        else:
            seen.add(row)
            record = _normalise(row)
            outcome[index] = _drop_reason(row, record)
            if outcome[index] is None:
                outcome[index] = _check_kind(row, record)
                candidates[index] = record
    groups = defaultdict(list)
    for index, record in candidates.items():
        if record["customer_id"] is not None:
            kind = 1 if record["is_cancellation"] else 0
            groups[(record["customer_id"], record["stock_code"])].append((record["invoice_date"], kind, index, record))
        elif record["is_cancellation"]:
            outcome[index] = "return"
    for events in groups.values():
        events.sort(key=lambda event: event[:3])
        for index, result in _settle(events).items():
            outcome[index] = result
    kept = [candidates[i] for i in sorted(candidates) if outcome[i] in ("sale", "return")]
    return kept, Counter(outcome)


def write_parquet(records, path):
    columns = {name: [record[name] for record in records] for name in SCHEMA.names}
    for price in columns["price"]:
        if price != price.quantize(Decimal("0.0001")):
            raise ValueError(f"price {price} has more than four decimal places")
    pq.write_table(pa.table(columns, schema=SCHEMA), path)
