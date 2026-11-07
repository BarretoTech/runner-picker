#!/usr/bin/env bash
# Inputs are environment variables; fixture files bypass network access in tests.
set -Eeuo pipefail
SELF_HOSTED=${SELF_HOSTED:-'["self-hosted"]'}
HOSTED=${HOSTED:-'"ubuntu-latest"'}
OVERFLOW=${OVERFLOW:-}
SOURCE=${SOURCE:-github}
MIN_IDLE=${MIN_IDLE:-1}
WEIGHT=${WEIGHT:-1}
TOKEN=${TOKEN:-}
RUNNER_SCOPE=${RUNNER_SCOPE:-org}
CAPACITY_URL=${CAPACITY_URL:-}
TAILNET_CLIENT_ID=${TAILNET_CLIENT_ID:-}
result=$SELF_HOSTED
choice=self-hosted
reason='fallback: decision unavailable'
work=$(mktemp -d)
cleanup() { rm -rf "$work"; }
trap cleanup EXIT
emit() {
  local target=${GITHUB_OUTPUT:-/dev/stdout}
  printf 'runs-on=%s\nchoice=%s\nreason=%s\n' "$result" "$choice" "$reason" >> "$target"
  printf '::notice::Runner picker: %s (%s)\n' "$choice" "$reason"
}
fail() {
  printf '::notice::Runner picker: decision failed; using self-hosted labels\n'
  result=$SELF_HOSTED; choice=self-hosted; reason='fallback: decision unavailable'
  emit
  exit 0
}
invalid() { printf '::error::Runner picker: invalid %s\n' "$1"; fail; }
trap fail ERR
labels='type == "array" and length > 0 and all(.[]; type == "string" and length > 0 and (test("[\\x00-\\x1f\\x7f]") | not))'
target='(type == "string" and length > 0) or (type == "array" and length > 0 and all(.[]; type == "string" and length > 0))'
if ! SELF_HOSTED=$(jq -sce "select(length == 1) | .[0] | select($labels)" <<< "$SELF_HOSTED" 2>/dev/null); then
  SELF_HOSTED='["self-hosted"]'; invalid self-hosted
fi
result=$SELF_HOSTED
HOSTED=$(jq -sce "select(length == 1) | .[0] | select($target)" <<< "$HOSTED" 2>/dev/null) || invalid hosted
if [[ -n $OVERFLOW ]]; then OVERFLOW=$(jq -sce "select(length == 1) | .[0] | select($target)" <<< "$OVERFLOW" 2>/dev/null) || invalid overflow; fi
[[ $SOURCE == github || $SOURCE == service ]] || invalid source
[[ $RUNNER_SCOPE == org || $RUNNER_SCOPE == repo ]] || invalid runner-scope
[[ $MIN_IDLE =~ ^[1-9][0-9]{0,5}$ ]] || invalid min-idle
[[ $WEIGHT =~ ^[1-9][0-9]{0,5}$ ]] || invalid weight
choose_overflow() {
  if [[ -n $OVERFLOW ]]; then result=$OVERFLOW; choice=overflow; else result=$HOSTED; choice=hosted; fi
}
if [[ $SOURCE == github ]]; then
  if [[ -z $TOKEN && -z ${PICKER_FIXTURE_DIR:-} ]]; then fail; fi
  repository=${GITHUB_REPOSITORY:-}
  [[ $repository =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || invalid GITHUB_REPOSITORY
  api=${GITHUB_API_URL:-https://api.github.com}
  [[ $api == https://* ]] || invalid GITHUB_API_URL
  if [[ $RUNNER_SCOPE == org ]]; then endpoint="orgs/${repository%%/*}"; else endpoint="repos/$repository"; fi
  page=1
  while :; do
    if [[ -n ${PICKER_FIXTURE_DIR:-} ]]; then
      cp "$PICKER_FIXTURE_DIR/page-$page.json" "$work/page.json"
    else
      curl --silent --fail --connect-timeout 5 --max-time 20 \
        --header "Authorization: Bearer $TOKEN" --header 'Accept: application/vnd.github+json' \
        --header 'X-GitHub-Api-Version: 2022-11-28' \
        "$api/$endpoint/actions/runners?per_page=100&page=$page" > "$work/page.json"
    fi
    jq -sce 'select(length == 1) | .[0]' "$work/page.json" > "$work/validated.json"
    mv "$work/validated.json" "$work/page.json"
    jq -e '(.total_count | type == "number" and . >= 0) and (.runners | type == "array") and all(.runners[]; (.status | type == "string") and (.busy | type == "boolean") and (.labels | type == "array") and all(.labels[]; .name | type == "string"))' "$work/page.json" >/dev/null
    jq -c '.runners[]' "$work/page.json" >> "$work/runners.jsonl"
    count=$(jq '.runners | length' "$work/page.json")
    total=$(jq '.total_count' "$work/page.json")
    (( page * 100 >= total )) && break
    (( count > 0 && page < 1000 )) || fail
    page=$((page + 1))
  done
  idle=$(jq -s --argjson labels "$SELF_HOSTED" '[.[] | select(.status == "online" and .busy == false) | ([.labels[].name | ascii_downcase]) as $available | select(all($labels[]; ascii_downcase as $label | $available | index($label)))] | length' "$work/runners.jsonl")
  if (( idle >= MIN_IDLE )); then reason='idle runners available'; else choose_overflow; reason='insufficient idle runners'; fi
else
  [[ $CAPACITY_URL =~ ^https?://[^[:space:]]+$ && $CAPACITY_URL != *'@'* && $CAPACITY_URL != *'#'* ]] || invalid capacity-url
  jq -e 'all(.[]; contains(",") | not)' <<< "$SELF_HOSTED" >/dev/null || invalid self-hosted
  proxy=()
  if [[ -n $TAILNET_CLIENT_ID ]]; then
    [[ ${TAILNET_OUTCOME:-failure} == success ]] || fail
    proxy=(--proxy http://localhost:1055 --noproxy '')
  fi
  if [[ -n ${PICKER_SERVICE_FIXTURE:-} ]]; then
    cp "$PICKER_SERVICE_FIXTURE" "$work/service.json"
  else
    query=(--data-urlencode "labels=$(jq -r 'join(",")' <<< "$SELF_HOSTED")" --data-urlencode "weight=$WEIGHT")
    [[ -z ${GITHUB_REPOSITORY:-} ]] || query+=(--data-urlencode "org=${GITHUB_REPOSITORY%%/*}")
    [[ -z $OVERFLOW ]] || query+=(--data-urlencode "overflow=$(jq -r 'if type == "array" then join(",") else . end' <<< "$OVERFLOW")")
    curl --silent --fail --connect-timeout 5 --max-time 20 "${proxy[@]}" --get "${query[@]}" "$CAPACITY_URL" > "$work/service.json"
  fi
  jq -sce 'select(length == 1) | .[0]' "$work/service.json" > "$work/validated.json"
  mv "$work/validated.json" "$work/service.json"
  jq -e 'type == "object" and (.choice == "self-hosted" or .choice == "overflow" or .choice == "hosted") and (.reason | type == "string" and length > 0 and length <= 500 and (test("[\\x00-\\x1f\\x7f%]") | not))' "$work/service.json" >/dev/null
  choice=$(jq -r .choice "$work/service.json")
  reason=$(jq -r .reason "$work/service.json")
  case $choice in
    overflow) [[ -n $OVERFLOW ]] || fail; result=$OVERFLOW ;;
    hosted) result=$HOSTED ;;
  esac
fi
emit
