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

## Daily retail ETL

`pipelines/retail_etl/` reads the Online Retail II workbook from the lab bucket, writes
`online-retail-ii/clean/online_retail_ii.parquet` and replaces `retail.transactions` in `chaos_lab`.
`infra/` is the Terraform for the Lambda, its 06:00 UTC schedule and two alarms.

Build the Lambda zip with `pipelines/package.sh` (needs `uv`); pass its path as `package_path`.
To prove the configuration against the AWS emulator, copy `infra/*.tf` and `infra/emulator/*.tf` into a
scratch directory, then `terraform apply -var-file=infra/emulator/emulator.tfvars -var emulator_url=$AWS_EMULATOR_URL -var package_path=<zip>`.
