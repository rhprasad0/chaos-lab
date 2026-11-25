# chaos-lab

Small Spark pipelines over synthetic retail data, built by an AI software factory and then
broken on purpose to see whether it can fix them.

## The lab

`lab/compose.yaml` is a single-node Spark cluster (`spark-master`, `spark-worker`) and a
`postgres` database seeded with the retail tables from `generator/retail.py`. The same seed
always produces the same data. Each factory run gets a fresh copy, torn down when the run ends.

- Source: Postgres database `retail`, user `pipeline` (read-only), tables `customers`
  (one row per attribute change), `products`, `orders`, `order_items`, `payments`.
- Lake: write Parquet under `/lake`, which the master and the worker both mount.
- Code: the repository is mounted read-only at `/workspace/chaos-lab` in every Spark container.

Run a command on the cluster with `bin/lab`, for example
`bin/lab spark-submit --master spark://spark-master:7077 /workspace/chaos-lab/jobs/x.py`.
Inside a factory session `LAB_PROJECT` is already set; elsewhere bring a lab up with
`docker compose -f lab/compose.yaml -p mylab up -d --wait` and set `LAB_PROJECT=mylab`.

## Checks

`./verify.sh` is what CI runs. It starts its own lab unless `LAB_PROJECT` is set, then runs
`tests/` on the cluster.
