# Runner Picker

Choose a runner pool before a downstream job is queued. Runner Picker uses a small preparation job to select self-hosted labels when matching runners appear idle, or an overflow target when the pool is busy. The overflow can be a GitHub-hosted runner or another provider, such as Blacksmith.

This is a composite action using Bash, jq and curl, available on GitHub-hosted Linux runners. There is no JavaScript build step for the picker. Optional Tailscale networking uses its upstream action and runtime.

## Quick start: GitHub runner API

```yaml
name: Build
on: [push]
permissions:
  contents: read
jobs:
  pick:
    runs-on: ubuntu-latest
    outputs:
      runs-on: ${{ steps.runner.outputs.runs-on }}
    steps:
      - uses: BarretoTech/runner-picker@v1
        id: runner
        with:
          self-hosted: '["self-hosted", "linux", "build"]'
          token: ${{ secrets.RUNNER_READ_TOKEN }}
          # Optional provider label, tried before hosted:
          # overflow: '"your-provider-label"'
          hosted: '"ubuntu-latest"'
  build:
    needs: pick
    runs-on: ${{ fromJSON(needs.pick.outputs.runs-on) }}
    steps:
      - run: echo "Build on the selected pool"
```

`v1` is a moving major tag created with the first release. Before release, use a reviewed commit SHA. For production, replace `@v1` with the full SHA of the release you reviewed.

Provide a GitHub App installation token or fine-grained PAT with organization **Self-hosted runners: read** permission. For `runner-scope: repo`, use repository **Administration: read** (repository administrator access). Install/authorize the token for the selected organization or repository. `GITHUB_TOKEN` cannot list self-hosted runners; increasing workflow `permissions` does not grant it this access. The owner and repository come from `github.repository`, and the API base comes from `github.api_url`.

## Quick start: capacity service

Use the same two-job structure, replacing the picker step with:

```yaml
- uses: BarretoTech/runner-picker@v1
  id: runner
  with:
    source: service
    self-hosted: '["self-hosted", "linux"]'
    capacity-url: https://capacity.example/capacity
    overflow: '"your-provider-label"'
    weight: '1'
```

Run your own service implementing the contract below. A [dependency-free Python example](examples/capacity-service/) queries GitHub on the server and keeps the API token there.

For an optional private service over Tailscale, add `tailnet-client-id: ${{ vars.CAPACITY_NETWORK_CLIENT }}` and `tailnet-tags: tag:ci`. The action supplies audience `api.tailscale.com/<client-id>`; configure that exact audience in the identity. Configure a Tailscale federated identity trusting the caller repository/workflow and its tags, then grant that identity access only to the service. Give the picker job `permissions: {contents: read, id-token: write}`. No Tailscale client secret is required. The SHA-pinned upstream action runs in userspace mode; curl uses its HTTP proxy at `localhost:1055` only for the capacity request. Connection failure falls back to self-hosted. Do not run multiple network setup actions in the same job. Plain HTTP is supported for private networks; use HTTPS for public services.

### Service contract

The action performs a GET on `capacity-url` with URL-encoded parameters:

| Parameter | Meaning |
| --- | --- |
| `labels` | Required self-hosted labels, comma-separated |
| `weight` | Positive integer request weight |
| `org` | Caller repository owner; sent only with an overflow offer |
| `blacksmith` | Optional overflow offer; a string target, or the first label of an array target |

Labels used with a service must not contain commas. The endpoint returns HTTP 200 and JSON `{"choice":"self-hosted","reason":"idle runners available"}`. Wire choices are `self-hosted`, `blacksmith`, and `hosted`. The `blacksmith` wire value selects the configured `overflow` input and is exposed as public output `choice: overflow`; selecting it without an input is an error. The provider-specific wire name is retained for service compatibility, even when the configured target uses another provider. `hosted` selects the hosted input. The reason must be a nonempty, single-line string of at most 500 characters, without percent or control characters. Malformed responses, any HTTP status other than 200 and timeouts return the self-hosted fallback. The action never sends its `token` input to the service. Protect the service through network access controls or your authenticated gateway.

## Inputs

All runs-on inputs are JSON, including strings: use `'"ubuntu-latest"'`, not `'ubuntu-latest'`.

| Input | Default | Description |
| --- | --- | --- |
| `self-hosted` | `["self-hosted"]` | Nonempty JSON array of required labels |
| `hosted` | `"ubuntu-latest"` | Final alternate runs-on JSON string or array |
| `overflow` | empty | Optional alternate JSON string or array preferred over hosted |
| `source` | `github` | `github` or `service` |
| `token` | empty | Runner read token; only used by GitHub source |
| `runner-scope` | `org` | `org` or `repo`; GitHub source |
| `min-idle` | `1` | Matching idle runners needed; GitHub source |
| `capacity-url` | empty | Required HTTP(S) endpoint for service source |
| `tailnet-client-id` | empty | Optional Tailscale federated identity client ID |
| `tailnet-tags` | `tag:ci` | Comma-separated identity tags |
| `weight` | `1` | Service request weight, interpreted by the service |

Integers must be between 1 and 999999. Invalid inputs produce a clear error annotation and successful action completion with self-hosted fallback. If `self-hosted` itself is invalid, the only usable fallback is `["self-hosted"]`.

## Outputs

| Output | Description |
| --- | --- |
| `runs-on` | Compact JSON for `fromJSON(...)` |
| `choice` | `self-hosted`, `overflow`, or `hosted` |
| `reason` | Decision explanation, or `fallback: decision unavailable` |

## How it decides

The GitHub source lists `/orgs/{org}/actions/runners` or `/repos/{owner}/{repo}/actions/runners` with `per_page=100`, pagination and `X-GitHub-Api-Version: 2022-11-28`. A runner counts only when online, not busy, and carrying every requested label, compared case-insensitively. At least `min-idle` matches selects self-hosted; otherwise a configured overflow is selected, then hosted. This does not probe overflow availability. The service source delegates that decision, passing `weight` instead of `min-idle`.

Any API, parsing, validation or network error keeps self-hosted labels so capacity detection does not fail the job. Requests have connection and total timeouts. Runner listings stop at 1000 pages; incomplete listings fail safely.

## Security

- Pin this action and other workflow actions to full commit SHAs. Review updates before adopting them.
- Use a least-privilege, short-lived GitHub App token where possible. This action never prints the token or API response bodies. Do not enable shell tracing around secrets.
- Fork pull requests receive no secrets by default and therefore fall back to self-hosted. **Only use that fallback for code you trust to execute on your self-hosted fleet.** Gate untrusted contributions with workflow policy; never expose privileged runners or secrets to untrusted code via `pull_request_target`.
- Limit federated identity trust and private network policy to the intended workflow and service. Grant `id-token: write` only when networking needs it.
- Consult [SECURITY.md](SECURITY.md) for private reporting.

## Limits and FAQ

**Is this a reservation?** No. An idle runner can be claimed immediately after the API snapshot. Queued jobs may already be waiting for it. Concurrent pickers can choose the same idle capacity. For stronger guarantees, implement reservation logic in your own service.

**Why does it still queue?** Runner groups, repository visibility, workflow restrictions and other scheduler policies are not evaluated. The API may list a runner that this job cannot use. Configure labels and access carefully.

**Can the action move its own job?** No. Run it in a separate preparation job and use the output on a dependent job, as shown above. The preparation job has its own startup time and cost.

**Does overflow guarantee success?** No. Provider labels, entitlement and capacity must be configured by the caller. The action only selects runs-on; downstream jobs can still fail or wait.

**Are runner groups supported?** Runs-on objects are currently unsupported. Use string/array targets and labels unique to the desired pool. The Bash picker is intended for Linux preparation jobs with Bash, jq and curl installed.

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md) and the [MIT license](LICENSE).
