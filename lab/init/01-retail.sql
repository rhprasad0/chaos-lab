CREATE TABLE customers (
  customer_id integer NOT NULL,
  email text NOT NULL,
  full_name text NOT NULL,
  city text NOT NULL,
  segment text NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (customer_id, updated_at)
);

CREATE TABLE products (
  product_id integer PRIMARY KEY,
  sku text NOT NULL UNIQUE,
  name text NOT NULL,
  category text NOT NULL,
  unit_price numeric(10, 2) NOT NULL,
  active boolean NOT NULL
);

CREATE TABLE orders (
  order_id integer PRIMARY KEY,
  customer_id integer NOT NULL,
  ordered_at timestamptz NOT NULL,
  status text NOT NULL,
  currency text NOT NULL
);

CREATE TABLE order_items (
  order_item_id integer PRIMARY KEY,
  order_id integer NOT NULL REFERENCES orders,
  product_id integer NOT NULL REFERENCES products,
  quantity integer NOT NULL,
  unit_price numeric(10, 2) NOT NULL,
  discount numeric(10, 2) NOT NULL
);

CREATE TABLE payments (
  payment_id integer PRIMARY KEY,
  order_id integer NOT NULL REFERENCES orders,
  paid_at timestamptz NOT NULL,
  amount numeric(12, 2) NOT NULL,
  method text NOT NULL,
  status text NOT NULL
);

COPY customers FROM '/seed/customers.csv' WITH (FORMAT csv, HEADER true);
COPY products FROM '/seed/products.csv' WITH (FORMAT csv, HEADER true);
COPY orders FROM '/seed/orders.csv' WITH (FORMAT csv, HEADER true);
COPY order_items FROM '/seed/order_items.csv' WITH (FORMAT csv, HEADER true);
COPY payments FROM '/seed/payments.csv' WITH (FORMAT csv, HEADER true);

CREATE ROLE pipeline LOGIN PASSWORD 'pipeline';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pipeline;
