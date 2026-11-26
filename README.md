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
