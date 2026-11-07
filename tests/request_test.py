"""Check request construction and error handling with a fake curl executable."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class RequestsTest(unittest.TestCase):
    def run_picker(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            curl = work / 'curl'
            curl.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['REQUEST_LOG'], 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
if os.environ.get('FAIL_CURL') == 'yes':
    sys.exit(22)
if os.environ.get('SOURCE') == 'service':
    body = os.environ.get('SERVICE_RESPONSE','{"choice":"hosted","reason":"pool busy"}')
else:
    body = '{"total_count":0,"runners":[]}'
if '--output' in sys.argv:
    with open(sys.argv[sys.argv.index('--output') + 1], 'w') as f:
        f.write(body)
    print(os.environ.get('HTTP_STATUS', '200'), end='')
else:
    print(body)
''')
            curl.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if not k.startswith('PICKER_')}
            env.update(PATH=str(work) + os.pathsep + os.environ['PATH'],
                       GITHUB_REPOSITORY='example-org/example-repo', TOKEN='test-secret-value',
                       GITHUB_OUTPUT=str(work / 'output'), REQUEST_LOG=str(work / 'requests'),
                       SELF_HOSTED='["self-hosted","linux"]', HOSTED='"ubuntu-latest"',
                       OVERFLOW='', SOURCE='github', RUNNER_SCOPE='org', MIN_IDLE='1', WEIGHT='1',
                       TAILNET_CLIENT_ID='', GITHUB_API_URL='https://api.github.com')
            env.update(overrides)
            completed = subprocess.run(['bash', 'src/pick.sh'], env=env, text=True, capture_output=True, check=True)
            self.assertNotIn('test-secret-value', completed.stdout + completed.stderr)
            return (work / 'output').read_text(), [json.loads(line) for line in (work / 'requests').read_text().splitlines()]

    def test_federated_audience(self):
        action = Path('action.yml').read_text()
        self.assertIn('audience: api.tailscale.com/${{ inputs.tailnet-client-id }}', action)

    def test_service_provider_response(self):
        output, calls = self.run_picker(SOURCE='service', CAPACITY_URL='https://capacity.example/capacity',
                                       OVERFLOW='["example-overflow","linux"]',
                                       SERVICE_RESPONSE='{"choice":"blacksmith","reason":"capacity available"}')
        self.assertIn('choice=overflow', output)
        self.assertIn('runs-on=["example-overflow","linux"]', output)
        self.assertIn('blacksmith=example-overflow', calls[0])
        self.assertIn('org=example-org', calls[0])
        self.assertNotIn('overflow=example-overflow,linux', calls[0])

    def test_no_provider_offer_omits_org(self):
        _, calls = self.run_picker(SOURCE='service', CAPACITY_URL='https://capacity.example/capacity')
        self.assertFalse(any(arg.startswith(('org=', 'blacksmith=')) for arg in calls[0]))

    def test_non_200_falls_back(self):
        for source in ['github', 'service']:
            for status in ['201', '204', '302', '401', '500']:
                with self.subTest(source=source, status=status):
                    output, _ = self.run_picker(SOURCE=source, HTTP_STATUS=status,
                                               CAPACITY_URL='https://capacity.example/capacity')
                    self.assertIn('choice=self-hosted', output)
                    self.assertIn('reason=fallback:', output)

    def test_real_http_redirect_is_not_a_decision(self):
        class Handler(BaseHTTPRequestHandler):
            status = 302

            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.send_response(self.status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"choice":"hosted","reason":"redirected"}')

        with ThreadingHTTPServer(('localhost', 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with tempfile.TemporaryDirectory() as directory:
                    env = {k: v for k, v in os.environ.items() if not k.startswith('PICKER_')}
                    env.update(SOURCE='service', TAILNET_CLIENT_ID='', OVERFLOW='',
                               SELF_HOSTED='["self-hosted"]', HOSTED='"ubuntu-latest"',
                               CAPACITY_URL=f'http://localhost:{server.server_port}/capacity',
                               GITHUB_OUTPUT=directory + '/output')
                    for status, expected in [(200, 'hosted'), (302, 'self-hosted')]:
                        Handler.status = status
                        Path(env['GITHUB_OUTPUT']).write_text('')
                        subprocess.run(['bash', 'src/pick.sh'], env=env, capture_output=True, check=True)
                        self.assertIn('choice=' + expected, Path(env['GITHUB_OUTPUT']).read_text())
            finally:
                server.shutdown()
                thread.join()

    def test_org_api(self):
        output, calls = self.run_picker()
        self.assertIn('choice=hosted', output)
        self.assertIn('https://api.github.com/orgs/example-org/actions/runners?per_page=100&page=1', calls[0])
        self.assertIn('X-GitHub-Api-Version: 2022-11-28', calls[0])
        self.assertIn('Authorization: Bearer test-secret-value', calls[0])

    def test_repo_api(self):
        _, calls = self.run_picker(RUNNER_SCOPE='repo')
        self.assertIn('https://api.github.com/repos/example-org/example-repo/actions/runners?per_page=100&page=1', calls[0])

    def test_http_error(self):
        output, _ = self.run_picker(FAIL_CURL='yes')
        self.assertIn('choice=self-hosted', output)
        self.assertIn('reason=fallback:', output)

    def test_service_contract_and_proxy(self):
        output, calls = self.run_picker(SOURCE='service', CAPACITY_URL='https://capacity.example/capacity',
                                       OVERFLOW='"example-overflow"', WEIGHT='2',
                                       TAILNET_CLIENT_ID='example', TAILNET_OUTCOME='success')
        self.assertIn('choice=hosted', output)
        for value in ['labels=self-hosted,linux', 'weight=2', 'org=example-org',
                      'blacksmith=example-overflow', 'http://localhost:1055']:
            self.assertIn(value, calls[0])
        self.assertFalse(any('test-secret-value' in arg for arg in calls[0]))


if __name__ == '__main__':
    unittest.main()
