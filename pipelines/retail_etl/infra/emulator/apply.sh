#!/usr/bin/env bash
set -euo pipefail
infra="$(cd "$(dirname "$0")/.." && pwd)"
url="${1:?usage: pipelines/retail_etl/infra/emulator/apply.sh http://localhost:5000}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp "$infra"/*.tf "$infra"/emulator/*.tf "$infra"/emulator/emulator.tfvars "$work/"
cd "$work"
unset AWS_PROFILE AWS_SESSION_TOKEN AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_PROFILE
export AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null
emulator_aws() { aws --region us-east-1 --endpoint-url "$url" --output text "$@"; }
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
vpc="$(emulator_aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId')"
database_group="$(emulator_aws ec2 describe-security-groups --filters Name=vpc-id,Values="$vpc" Name=group-name,Values=default --query 'SecurityGroups[0].GroupId')"
args=(-var-file=emulator.tfvars -var "emulator_url=$url" -var "package_path=$infra/../build/etl.zip"
  -var "vpc_id=$vpc" -var "db_security_group_id=$database_group" -input=false)
terraform init -input=false >/dev/null
terraform validate
terraform apply -auto-approve "${args[@]}"
status=0
terraform plan -no-color -detailed-exitcode "${args[@]}" >plan.txt || status=$?
grep -E "#|~|Plan:" plan.txt || true
echo "second plan exit $status (moto prefixes referenced security group IDs with the account, so 2 is expected here)"
