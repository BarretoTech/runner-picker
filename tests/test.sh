#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export SELF_HOSTED='["self-hosted","linux"]' GITHUB_REPOSITORY=example-org/example-repo
export PICKER_FIXTURE_DIR="$work" GITHUB_OUTPUT="$work/output"
export SOURCE=github TOKEN='' HOSTED='"ubuntu-latest"' OVERFLOW='' MIN_IDLE=1 WEIGHT=1 RUNNER_SCOPE=org
unset PICKER_SERVICE_FIXTURE TAILNET_CLIENT_ID
runner='{"status":"online","busy":false,"labels":[{"name":"SELF-HOSTED"},{"name":"Linux"}]}'
page() { jq -n --argjson r "$1" '{total_count:($r|length),runners:$r}' > "$work/page-1.json"; }
check() {
  : > "$GITHUB_OUTPUT"
  bash src/pick.sh > "$work/log" 2>&1
  if ! grep -q "^choice=$2$" "$GITHUB_OUTPUT"; then cat "$work/log" "$GITHUB_OUTPUT"; exit 1; fi
  if [[ -n ${3:-} ]]; then grep -q -- "$3" "$work/log"; fi
  jq -e . <<< "$(sed -n 's/^runs-on=//p' "$GITHUB_OUTPUT")" >/dev/null
  printf 'PASS %s\n' "$1"
}
page "[$runner]"; check 'matching labels and case-insensitivity' self-hosted
page "[$runner]"; MIN_IDLE=2 check 'minimum idle threshold' hosted
page "[$runner]"; sed -i 's/false/true/' "$work/page-1.json"; check busy hosted
page "[$runner]"; sed -i 's/online/offline/' "$work/page-1.json"; check offline hosted
page "[$runner]"; sed -i 's/Linux/windows/' "$work/page-1.json"; check 'missing label' hosted
page '[]'; OVERFLOW='["example-overflow"]' check 'preferred overflow' overflow
check 'hosted fallback' hosted
jq -n '{total_count:101,runners:[range(100)|{status:"offline",busy:false,labels:[]}]}' > "$work/page-1.json"
jq -n --argjson r "$runner" '{total_count:101,runners:[$r]}' > "$work/page-2.json"
check pagination self-hosted
printf 'invalid' > "$work/page-1.json"; check 'bad API JSON' self-hosted
printf '{"message":"denied"}' > "$work/page-1.json"; check 'API error payload' self-hosted
rm "$work/page-1.json"; check 'API transport failure' self-hosted
SELF_HOSTED=invalid check 'bad self-hosted JSON' self-hosted 'invalid self-hosted'
SELF_HOSTED='["self-hosted"] ["linux"]' check 'multiple JSON values' self-hosted 'invalid self-hosted'
HOSTED=invalid check 'bad hosted JSON' self-hosted 'invalid hosted'
OVERFLOW='{}' check 'bad overflow JSON' self-hosted 'invalid overflow'
MIN_IDLE=0 check 'invalid threshold' self-hosted
SOURCE=unknown check 'invalid source' self-hosted
PICKER_FIXTURE_DIR='' check 'missing token' self-hosted
export SOURCE=service CAPACITY_URL=https://capacity.example/capacity PICKER_SERVICE_FIXTURE="$work/service.json"
printf '{"choice":"blacksmith","reason":"pool busy"}' > "$PICKER_SERVICE_FIXTURE"
OVERFLOW='"example-overflow"' check 'service overflow' overflow
check 'unconfigured service overflow' self-hosted
printf '{"choice":"hosted","reason":"pool busy"}' > "$PICKER_SERVICE_FIXTURE"
check 'service hosted' hosted
printf '{"choice":"self-hosted","reason":"available"}' > "$PICKER_SERVICE_FIXTURE"
check 'service self-hosted' self-hosted
printf '{"choice":"hosted","reason":"bad\noutput"}' > "$PICKER_SERVICE_FIXTURE"
check 'malformed service response' self-hosted
TAILNET_CLIENT_ID=example TAILNET_OUTCOME=failure check 'network setup failure' self-hosted
printf 'All decision tests passed.\n'
