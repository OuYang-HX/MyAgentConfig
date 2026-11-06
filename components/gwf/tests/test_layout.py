#!/usr/bin/env python3
"""End-to-end tests use disposable Git repositories and an isolated HOME."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / 'scripts' / 'gwf.py'


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.top = Path(self.tmp.name)
        self.home = self.top / 'home'
        self.home.mkdir()
        self.root = self.top / 'repo'
        self.root.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'GIT_CONFIG_NOSYSTEM': '1',
                    'GIT_CONFIG_GLOBAL': str(self.home / 'gitconfig'),
                    'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.test',
                    'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.test'}
        self.git('init', '--bare', '--initial-branch=main', str(self.root / '.git'), cwd=self.top)
        seed = self.top / 'seed'
        self.git('init', '--initial-branch=main', str(seed), cwd=self.top)
        (seed / 'base').write_text('base')
        self.git('add', '.', cwd=seed)
        self.git('commit', '-m', 'base', cwd=seed)
        self.git('remote', 'add', 'origin', str(self.root / '.git'), cwd=seed)
        self.git('push', 'origin', 'main', cwd=seed)
        self.git('worktree', 'add', str(self.root / 'main'), 'main')
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime' / 'keep').write_text('private')
        (self.root / 'AGENTS.md').write_text('instructions')
        self.cfg = {'main_branch': 'main', 'main_worktree': 'main', 'upstream_ref': '',
                    'upstream_remote': '', 'origin_remote': '', 'protected_dirs': ['runtime'],
                    'resource_worktrees': ['data']}
        self.config()

    def git(self, *args, cwd=None, input=None):
        return subprocess.run(['git', *args], cwd=cwd or self.root, env=self.env, input=input,
                              text=True, capture_output=True, check=True).stdout.strip()

    def config(self):
        (self.root / '.gwf.json').write_text(json.dumps(self.cfg))

    def gwf(self, *args, ok=True, cwd=None):
        p = subprocess.run(['python3', '-B', str(CLI), *args], cwd=cwd or self.root,
                           env=self.env, text=True, capture_output=True)
        if ok:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        else:
            self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout + p.stderr

    def add(self, name):
        self.git('worktree', 'add', '-b', name, str(self.root / name), 'main')
        return self.root / name

    def commit(self, path, name, content):
        file = path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
        self.git('add', name, cwd=path)
        self.git('commit', '-m', name, cwd=path)

    def snapshot(self):
        result = {}
        for base in (self.root, self.home):
            for p in base.rglob('*'):
                if p.is_file() and not p.is_symlink():
                    result[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        return result

    def test_read_only_missing_config_and_doctor(self):
        (self.root / '.gwf.json').unlink()
        before = self.snapshot()
        for command in ('status', 'scan', 'doctor', 'config'):
            self.assertIn('内存', self.gwf(command))
            self.assertEqual(before, self.snapshot(), command)

    def test_new_scan_and_resource(self):
        out = self.gwf('new', 'alpha')
        self.assertIn('完成', out)
        a = self.root / 'feat-alpha'
        b = self.add('feat-b')
        self.commit(a, 'committed.txt', 'a')
        self.commit(b, 'committed.txt', 'b')
        (a / 'staged').write_text('a')
        self.git('add', 'staged', cwd=a)
        (b / 'staged').write_text('b')
        (a / 'base').write_text('changed')
        (b / 'base').write_text('changed')
        for p in (a, b):
            (p / 'newdir').mkdir()
            (p / 'newdir' / 'file\nname').write_text('new')
            (p / '.gitignore').write_text('generated/\n')
            (p / 'generated').mkdir()
            (p / 'generated' / 'result').write_text('artifact')
        tree = self.git('mktree', input='')
        orphan = self.git('commit-tree', tree, '-m', 'orphan')
        self.git('branch', 'data', orphan)
        self.git('worktree', 'add', str(self.root / 'data'), 'data')
        tree2 = self.git('commit-tree', tree, '-m', 'other orphan')
        self.git('branch', 'other', tree2)
        self.git('worktree', 'add', str(self.root / 'other'), 'other')
        scan = self.gwf('scan')
        for name in ('committed.txt', 'staged', 'base', 'newdir/file\\nname'):
            self.assertIn(name, scan)
        self.assertIn('忽略路径', scan)
        self.assertIn('data: resource', scan)
        self.assertIn('other: unrelated', scan)
        status = self.gwf('status')
        self.assertIn('resource', status)
        self.assertIn('unrelated', status)
        self.assertNotIn('gwf sync data', status)
        self.assertTrue((self.root / 'runtime' / 'keep').exists())

    def test_invalid_targets_cannot_mutate_main(self):
        a = self.add('feat-a')
        self.commit(a, 'addition', 'feature')
        before = self.git('rev-parse', 'main')
        for target in ('runtime', '../repo/runtime', 'data'):
            self.gwf('archive', target, '--merge', '--no-push', ok=False)
            self.gwf('sync', target, '--skip-fetch', ok=False)
            self.assertEqual(before, self.git('rev-parse', 'main'))
        (self.root / 'alias').symlink_to(self.root / 'runtime', target_is_directory=True)
        self.gwf('archive', 'alias', '--merge', '--no-push', ok=False)
        self.gwf('sync', 'alias', '--skip-fetch', ok=False)
        self.gwf('new', '../runtime', ok=False)
        self.assertEqual(before, self.git('rev-parse', 'main'))
        (a / 'untracked').write_text('preserve')
        self.gwf('archive', 'feat-a', '--merge', '--no-push', '--force', ok=False)
        self.assertEqual(before, self.git('rev-parse', 'main'))
        self.assertTrue((a / 'untracked').exists())
        (a / 'untracked').unlink()
        self.cfg['protected_dirs'].append('feat-a/private')
        self.config()
        self.gwf('archive', 'feat-a', '--merge', '--no-push', ok=False)
        self.gwf('sync', 'feat-a', '--skip-fetch', ok=False)
        self.assertEqual(before, self.git('rev-parse', 'main'))

    def test_sync_all_skips_unrelated_and_resource(self):
        self.add('feat-a')
        tree = self.git('mktree', input='')
        orphan = self.git('commit-tree', tree, '-m', 'orphan')
        for name in ('data', 'other'):
            self.git('branch', name, orphan)
            self.git('worktree', 'add', str(self.root / name), name)
        result = self.gwf('sync', '--all', '--skip-fetch', '--dry-run')
        self.assertIn('data: resource', result)
        self.assertIn('other: unrelated', result)
        self.assertIn('feat-a', result)

    def test_invalid_config_is_not_ignored_and_init_keeps_roles(self):
        (self.root / '.gwf.json').write_text('{bad')
        self.gwf('new', 'unsafe', ok=False)
        self.gwf('config', ok=False)
        self.assertFalse((self.root / 'feat-unsafe').exists())
        self.config()
        self.gwf('config', 'init')
        config = json.loads((self.root / '.gwf.json').read_text())
        self.assertEqual(config['protected_dirs'], ['runtime'])
        self.assertEqual(config['resource_worktrees'], ['data'])

    def test_new_archive_preserves_ledger_and_guards_other_ignored(self):
        ignore = self.home / 'ignore'
        ignore.write_text('worktree.md\n.notes/\n')
        self.git('config', '--global', 'core.excludesfile', str(ignore))
        self.gwf('new', 'alpha')
        a = self.root / 'feat-alpha'
        ledger = (a / 'worktree.md').read_bytes()
        self.commit(a, 'feature', 'new feature')
        (a / '.notes').mkdir()
        (a / '.notes' / 'important').write_text('private material')
        before = self.git('rev-parse', 'main')
        self.gwf('archive', 'feat-alpha', '--merge', '--no-push', ok=False)
        self.assertEqual(before, self.git('rev-parse', 'main'))
        self.assertEqual((a / '.notes' / 'important').read_text(), 'private material')
        (a / '.notes' / 'important').unlink()
        (a / '.notes').rmdir()
        out = self.gwf('archive', 'feat-alpha', '--merge', '--no-push')
        digest = hashlib.sha256(ledger).hexdigest()
        saved = self.root / '.git' / 'gwf-archive' / (digest + '.md')
        self.assertEqual(saved.read_bytes(), ledger)
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertIn(digest, out)
        self.assertFalse(a.exists())
        # Without an ignore rule, the generated ledger is still preserved.
        ignore.write_text('.notes/\n')
        self.gwf('new', 'beta')
        b = self.root / 'feat-beta'
        ledger = (b / 'worktree.md').read_bytes()
        self.commit(b, 'feature2', 'second feature')
        self.gwf('archive', 'feat-beta', '--merge', '--no-push')
        digest = hashlib.sha256(ledger).hexdigest()
        self.assertEqual((self.root / '.git' / 'gwf-archive' / (digest + '.md')).read_bytes(), ledger)

    def test_scan_includes_main_uncommitted_paths_only(self):
        a = self.add('feat-a')
        (a / 'base').write_text('feature dirty')
        main = self.root / 'main'
        (main / 'base').write_text('main dirty')
        result = self.gwf('scan')
        self.assertIn('主工作树存在未提交变更', result)
        self.assertIn("'base' <- feat-a, main", result)
        self.assertIn('先处理主工作树', result)
        self.git('add', 'base', cwd=main)
        self.assertIn("'base' <- feat-a, main", self.gwf('scan'))
        self.git('reset', '--', 'base', cwd=main)
        (main / 'base').write_text('base')
        result = self.gwf('scan')
        self.assertNotIn('主工作树存在未提交变更', result)
        self.assertNotIn("'base' <-", result)
        (main / 'newdir').mkdir()
        (main / 'newdir' / 'shared').write_text('main new')
        (a / 'newdir').mkdir()
        (a / 'newdir' / 'shared').write_text('feature new')
        result = self.gwf('scan')
        self.assertIn("'newdir/shared' <- feat-a, main", result)

    def test_corrupt_ledger_archive_blocks_before_merge(self):
        self.gwf('new', 'alpha')
        a = self.root / 'feat-alpha'
        ledger = (a / 'worktree.md').read_bytes()
        self.commit(a, 'feature', 'new feature')
        directory = self.root / '.git' / 'gwf-archive'
        directory.mkdir(mode=0o700)
        saved = directory / (hashlib.sha256(ledger).hexdigest() + '.md')
        saved.write_bytes(b'not the ledger')
        before = self.git('rev-parse', 'main')
        self.gwf('archive', 'feat-alpha', '--merge', '--no-push', ok=False)
        self.assertEqual(before, self.git('rev-parse', 'main'))
        self.assertEqual((a / 'worktree.md').read_bytes(), ledger)
        self.assertEqual(saved.read_bytes(), b'not the ledger')

    def test_symlink_ledger_is_not_followed(self):
        self.gwf('new', 'alpha')
        a = self.root / 'feat-alpha'
        (a / 'worktree.md').unlink()
        (a / 'worktree.md').symlink_to(self.root / 'runtime' / 'keep')
        self.commit(a, 'feature', 'new feature')
        before = self.git('rev-parse', 'main')
        self.gwf('archive', 'feat-alpha', '--merge', '--no-push', ok=False)
        self.assertEqual(before, self.git('rev-parse', 'main'))
        self.assertEqual((self.root / 'runtime' / 'keep').read_text(), 'private')

    def test_regular_archive(self):
        a = self.add('feat-a')
        self.commit(a, 'addition', 'feature')
        self.gwf('archive', 'feat-a', '--merge', '--no-push')
        self.assertFalse(a.exists())
        self.assertTrue((self.root / 'main' / 'addition').exists())


if __name__ == '__main__':
    unittest.main()
