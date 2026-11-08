#!/usr/bin/env python3
"""Reject private vocabulary and address literals in tracked content and history."""
import hashlib
import pathlib
import re
import subprocess
import sys

# One-way fingerprints avoid publishing the private vocabulary itself.
fingerprints = {'7b6cab976ab6fab4a7a9206824a8e17a0f50b4d67800d79bc5f7d426a2f89a3e', '670f3c7ad403e4459b0b475ced6d4d797677f8035ae204ffbe12de77c4b69e8d', '50af53d015f1cf829b7ab86bb9126afb3e6949b108ecb9728666dae24fe5e9f9', '5dd0d7c07e9221f516510958f149e7c2e6bc4b175af34e90e68349210fbb9047', '31611159e7e6ff7843ea4627745e89225fc866621cfcfdbd40871af4413747cc', '9b97ac5e767e5393cd0eed09a8e51b6f3775eba38f792593ea016e8ba9e996b0', '9e78b43ea00edcac8299e0cc8df7f6f913078171335f733a21d5d911b6999132', '9e9386c5119e89378942dc383794621bbf18bac3f0491be4ef48c8540cab7d46', 'd303b19ffeb0e7928510eb9d3a1693c9c8fbc5d17f89510c939f46649a109d64'}
sizes = [4, 8, 10, 11, 13, 24]
addresses = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def restricted(text):
    if addresses.search(text):
        return True
    for token in re.findall(r"[a-z0-9_-]+", text.lower()):
        for size in sizes:
            for offset in range(len(token) - size + 1):
                digest = hashlib.sha256(token[offset:offset + size].encode()).hexdigest()
                if digest in fingerprints:
                    return True
    return False


failures = []
for path in pathlib.Path(".").rglob("*"):
    if path.is_file() and ".git" not in path.parts:
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if restricted(line):
                failures.append(f"{path}:{number}")
log = subprocess.check_output(["git", "log", "-p", "--all"], text=True)
if restricted(log):
    failures.append("commit history")
if failures:
    print("FAIL: restricted content at " + ", ".join(failures))
    sys.exit(1)
print("PASS: whole tree and git log -p --all: no prohibited strings or IPv4 addresses")
