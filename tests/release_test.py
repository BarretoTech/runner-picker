"""Check major-tag advancement against real local Git tag sets."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = str(Path('scripts/is-latest-release.sh').resolve())


class ReleaseTest(unittest.TestCase):
    def test_highest_version_only(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(['git', '-C', directory, *args], text=True).strip()
            git('init', '--quiet')
            env = dict(os.environ, GIT_AUTHOR_NAME='Rhuan Barreto', GIT_AUTHOR_EMAIL='rhuan@barreto.work',
                       GIT_COMMITTER_NAME='Rhuan Barreto', GIT_COMMITTER_EMAIL='rhuan@barreto.work')
            tree = subprocess.check_output(['git', '-C', directory, 'mktree'], input='', text=True).strip()
            commit = subprocess.check_output(['git', '-C', directory, 'commit-tree', tree, '-m', 'test'], env=env, text=True).strip()
            for tag in ['v1.2.9', 'v1.2.10', 'v2.0.0', 'v1.4.0-rc.1', 'v1']:
                git('tag', tag, commit)
            for tag, expected in [('v1.2.9', 1), ('v1.2.10', 0), ('v2.0.0', 0),
                                  ('v1.4.0-rc.1', 1), ('v1', 1)]:
                with self.subTest(tag=tag):
                    result = subprocess.run(['bash', SCRIPT, tag], cwd=directory, capture_output=True)
                    self.assertEqual(result.returncode, expected, result.stderr)
            for tag in ['v1.3.0', 'v1.10.0']:
                git('tag', tag, commit)
            for tag, expected in [('v1.2.10', 1), ('v1.3.0', 1), ('v1.10.0', 0)]:
                with self.subTest(tag=tag):
                    result = subprocess.run(['bash', SCRIPT, tag], cwd=directory, capture_output=True)
                    self.assertEqual(result.returncode, expected, result.stderr)

    def test_release_workflow_checks_before_moving(self):
        workflow = Path('.github/workflows/release.yml').read_text()
        self.assertLess(workflow.index('bash scripts/is-latest-release.sh "$TAG"'),
                        workflow.index('gh api --method PATCH'))


if __name__ == '__main__':
    unittest.main()
