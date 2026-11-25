# chaos-lab

Small Spark pipelines over synthetic retail data, built by an AI software factory and then
broken on purpose to see whether it can fix them.

## The lab

`lab/compose.yaml` is a single-node Spark cluster (`spark-master`, `spark-worker`) and a
`postgres` database seeded with the retail tables from `generator/retail.py`. The same seed
always produces the same data. Each factory work item gets a fresh lab, torn down when it ends.
The lab itself (this compose file, `lab/init/` and the generator) comes from `main` as it was
when the session started, so edits on a branch do not change the data a run sees.

- Source: Postgres database `retail`, user `pipeline` (read-only), tables `customers`
  (one row per attribute change), `products`, `orders`, `order_items`, `payments`.
- Lake: write Parquet under `/lake`, which the master and the worker both mount.
- Code: your working tree is mounted read-only at `/workspace/chaos-lab` in every Spark
  container, so jobs always run the code as you have it now.

Run a command on the cluster with `bin/lab`, for example
`bin/lab spark-submit --master spark://spark-master:7077 /workspace/chaos-lab/jobs/x.py`.
Inside a factory session `LAB_PROJECT` is already set; elsewhere bring a lab up with
`docker compose -f lab/compose.yaml -p mylab up -d --wait` and set `LAB_PROJECT=mylab`.

The Spark image is `lab/Dockerfile`, published to GHCR by `image.yml` when it changes on
`main`; pin the digest it prints in `lab/compose.yaml`.

## Checks

`./verify.sh` is what CI runs. It starts its own lab unless `LAB_PROJECT` is set, then runs
`tests/` on the cluster.
