# Example capacity service

This dependency-free Python 3 script demonstrates the contract. It is an example, not a production scheduler: it does not reserve capacity, authenticate callers, rate-limit requests or coordinate concurrent decisions. Put it behind authenticated HTTPS or a private network with restrictive access controls before exposing it. Keep the upstream API token on the service, not in query parameters.

```bash
export RUNNER_OWNER=example-org
export RUNNER_SCOPE=org
# Supply RUNNER_TOKEN through your secret manager or environment.
python3 examples/capacity-service/server.py
```

`RUNNER_OWNER` is an organization for `org`, or `owner/repository` for `repo`. `RUNNER_TOKEN` needs runner read access. `BIND` defaults to `localhost`; `PORT` defaults to `8080`.

GET `/capacity?labels=self-hosted,linux&weight=1&org=example-org&blacksmith=example-overflow` returns `{"choice":"self-hosted","reason":"idle runners available"}` or an overflow decision. Labels are comma-separated and matched without case sensitivity. Weight is the required number of idle runners. `org` is sent only with an overflow offer. Optional `org` is checked against the configured owner; it cannot redirect credential use. Optional `blacksmith` indicates that an alternate target exists. Insufficient capacity with that offer returns wire choice `blacksmith`; the action translates it to public output choice `overflow`. Without it, insufficient capacity returns `hosted`. Errors return HTTP 503 so the action falls back to self-hosted. API calls paginate with 100 runners per page and use API version 2022-11-28.
