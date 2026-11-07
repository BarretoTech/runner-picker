#!/usr/bin/env bash
# Advance a major tag only to its highest stable semantic version.
set -euo pipefail
tag=${1:-}
version='(0|[1-9][0-9]*)'
[[ $tag =~ ^v${version}\.${version}\.${version}$ ]] || exit 1
major=${tag%%.*}
tags=$(git tag --list "$major.*.*")
latest=$(printf '%s\n' "$tags" | grep -E "^${major}\\.${version}\\.${version}$" | sort -V | tail -n 1)
[[ $tag == "$latest" ]]
