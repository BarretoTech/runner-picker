#!/usr/bin/env python3
"""Example only: a snapshot-based capacity endpoint, not a reservation system."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, quote
from urllib.request import Request, urlopen


def decide(labels, weight, overflow, org):
    scope = os.environ.get("RUNNER_SCOPE", "org")
    configured = os.environ["RUNNER_OWNER"]
    if org and org != configured.split("/")[0]:
        raise ValueError("organization is not allowed")
    if scope not in ("org", "repo"):
        raise ValueError("invalid scope")
    endpoint = "orgs" if scope == "org" else "repos"
    owner = quote(configured, safe="/" if scope == "repo" else "")
    idle = 0
    page = 1
    while True:
        req = Request(
            f"https://api.github.com/{endpoint}/{owner}/actions/runners?per_page=100&page={page}",
            headers={"Authorization": "Bearer " + os.environ["RUNNER_TOKEN"],
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
        )
        with urlopen(req, timeout=15) as response:
            data = json.load(response)
        runners = data["runners"]
        for runner in runners:
            available = {label["name"].lower() for label in runner["labels"]}
            if runner["status"] == "online" and runner["busy"] is False and set(labels) <= available:
                idle += 1
        if page * 100 >= data["total_count"]:
            break
        if not runners or page >= 1000:
            raise ValueError("incomplete runner listing")
        page += 1
    return {"choice": "self-hosted" if idle >= weight else "overflow" if overflow else "hosted",
            "reason": "idle runners available" if idle >= weight else "insufficient idle runners"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # Do not log query strings or upstream errors.

    def do_GET(self):
        try:
            url = urlsplit(self.path)
            if url.path != "/capacity":
                self.send_error(404)
                return
            query = parse_qs(url.query, strict_parsing=True)
            labels = query["labels"][0].lower().split(",")
            weight = int(query.get("weight", ["1"])[0])
            if not all(labels) or not 1 <= weight <= 999999:
                raise ValueError("invalid request")
            result = decide(labels, weight, query.get("overflow", [""])[0], query.get("org", [""])[0])
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_error(503, "Capacity unavailable")


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get("BIND", "localhost"), int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
