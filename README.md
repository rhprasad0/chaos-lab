# chaos-lab

Small data pipelines that clean and load the
[UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) dataset into
PostgreSQL, built by an AI software factory and then broken on purpose to see whether it can
fix them.

The lab is being rebuilt on a real development PostgreSQL instance; the plan is
[rhprasad0/nova-toll-budget-agent#851](https://github.com/rhprasad0/nova-toll-budget-agent/issues/851).

## Checks

`./verify.sh` is what CI runs: the protected `tests/` and the pipelines' own `pipelines/tests/`.
The factory may not change `tests/`, `bin/`, `verify.sh` or `.github/`.

## Retail ETL

`pipelines/retail_etl/` is the daily ETL that runs live in the development account: Lambda
`chaos-lab-retail-etl` reads `s3://chaos-lab-903859731897/online-retail-ii/online_retail_II.xlsx` at
06:00 UTC, writes `online-retail-ii/clean/online_retail_ii.parquet` and replaces
`chaos_lab.retail.transactions`. Two alarms (`-errors`, `-no-success`) publish to the
`chaos-lab-retail-etl-alarms` topic; their descriptions say where to start looking.

The cleaning rules come from
[adwitiyashukla/online-retail-data-profiling-and-analysis](https://github.com/adwitiyashukla/online-retail-data-profiling-and-analysis)
(MIT), fetched at a pinned commit by `package.sh`.

- Build: `pipelines/retail_etl/package.sh` (needs `uv`).
- Deploy (by hand, never by the factory): in `pipelines/retail_etl/infra`,
  `terraform init -backend-config=backend.development.hcl` then
  `terraform apply -var-file=development.tfvars`.
- Emulator: `pipelines/retail_etl/infra/emulator/apply.sh http://localhost:5000` applies the same
  stack to moto.

Faults are applied by the host at run time and are never committed here.

## Journal

Experiment results, one entry per day, in [`journal/`](journal/).
