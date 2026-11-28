Do all work in git worktrees so that multiple sessions do not collide.

When you find a bug, find and fix the root cause so that we are not stacking bandaids.

When Ryan corrects you, fix the mistake and add its rule to this table. Enforce it at the
highest level that works: structure first, then a check whose error names the fix, then a
test. Use prose only for judgment calls. Drop a rule once its mistake cannot happen.

| Rule | Enforced by |
| --- | --- |
| Work in a git worktree. | Nothing; judgment. |
| Fix root causes, not symptoms. | Nothing; judgment. |
| Prefer end-to-end tests to unit tests; fake only paid or credentialed external services. | Nothing; judgment. |
| Run what CI runs. | `verify.sh` is what `.github/workflows/verify.yml` calls. |
| Changes reach `main` by a PR that passes CI. | Branch protection requires `verify` and `factory-guard`, admins included. |
| Ryan applies infrastructure to real AWS; factory sessions apply only to their emulator. | Sessions hold no AWS credentials beyond the lab bucket key. |
| Write a check, not Markdown: no new Markdown files. Point docs at the code that owns a value instead of copying it. When a judgment call needs nuance, ask Ryan instead of writing it down. | Nothing; judgment. Journal pages are excepted. |
| Do not write code comments. | Nothing; judgment. |
