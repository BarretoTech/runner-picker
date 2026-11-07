# Contributing

Open an issue for substantial changes. Submit focused pull requests with a description and validation results. Use Bash and jq for the action; keep the service example dependency-free.

Run `bash tests/test.sh`, `python3 tests/service_test.py`, `python3 tests/request_test.py`, `python3 tests/release_test.py`, `shellcheck src/*.sh scripts/*.sh tests/*.sh`, `actionlint`, `zizmor --offline .`, and `python3 scripts/check-public.py` before submitting. Test tools are pinned in `.github/workflows/ci.yml`. Bash, jq, curl and Python 3 are prerequisites. Never include credentials, private infrastructure details, or raw API responses in logs or fixtures.

Releases are maintainer-driven: update the changelog, merge reviewed changes, then push a semantic version tag such as `v1.0.0`. The release workflow publishes release notes and advances the major tag only when the new version is the highest stable tag in that major series. Review major-tag changes before use; consumers should pin a full commit SHA.
