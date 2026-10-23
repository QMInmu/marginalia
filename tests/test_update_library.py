"""Behavioral tests using temporary libraries; never touch the real remote."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('updater', Path(__file__).parents[1] / 'scripts' / 'update_library.py')
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='marginalia-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'library'
        self.root.mkdir()
        self.sources = self.base / 'sources'
        self.sources.mkdir()
        self.config = {'schema_version': 1, 'title': 'Marginalia', 'title_zh': '书页之间',
                       'owner': 'test', 'repository': 'https://github.com/test/library',
                       'website': 'https://test.github.io/library/', 'default_language': 'en',
                       'branch': 'main', 'courses': []}
        (self.root / 'library.json').write_text(updater.json_text(self.config), encoding='utf-8')
        (self.root / 'catalog.json').write_text(updater.json_text(updater.build_catalog(self.root, self.config)), encoding='utf-8')
        (self.root / '.gitignore').write_text('.marginalia-work/\n', encoding='utf-8')

    def source(self, name='笔记 #1 [初稿].txt', content='原始内容\n'):
        path = self.sources / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = updater.main(['--root', str(self.root), *map(str, args)])
        return result, output.getvalue()

    def add(self, *sources, extra=()):
        return self.cli('add', '--course', '模拟电子技术', '--english-name', 'Analog Electronics',
                        '--category', '课件', *extra, *sources)

    def catalog(self):
        return updater.read_json(self.root / 'catalog.json')

    def test_new_course_and_idempotent_import(self):
        source = self.source()
        code, output = self.add(source)
        self.assertEqual(code, 0, output)
        course = self.catalog()['courses'][0]
        self.assertEqual(course['name'], {'en': 'Analog Electronics', 'zh': '模拟电子技术'})
        record = course['files'][0]
        target = self.root / record['path']
        self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertEqual(record['format'], 'TXT')
        self.assertIsNone(record['pages'])
        self.assertIn('%23', (self.root / course['directory'] / 'README.md').read_text(encoding='utf-8'))
        before = (self.root / 'catalog.json').read_bytes()
        modified = target.stat().st_mtime_ns
        code, output = self.add(source)
        self.assertEqual(code, 0, output)
        self.assertIn('相同，跳过复制', output)
        self.assertEqual(before, (self.root / 'catalog.json').read_bytes())
        self.assertEqual(modified, target.stat().st_mtime_ns)
        self.assertEqual(self.cli('sync', '--check')[0], 0)

    def test_dry_run_is_read_only(self):
        source = self.source()
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        code, output = self.add(source, extra=('--dry-run', '--publish'))
        self.assertEqual(code, 0, output)
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')))
        self.assertEqual(self.catalog()['courses'], [])

    def test_conflict_preserves_original_until_explicit_replace(self):
        source = self.source()
        self.assertEqual(self.add(source)[0], 0)
        record = self.catalog()['courses'][0]['files'][0]
        original = (self.root / record['path']).read_bytes()
        before = (self.root / 'catalog.json').read_bytes()
        source.write_text('更新版本', encoding='utf-8')
        code, output = self.add(source)
        self.assertEqual(code, 1)
        self.assertIn('同名文件内容不同', output)
        self.assertEqual((self.root / record['path']).read_bytes(), original)
        self.assertEqual((self.root / 'catalog.json').read_bytes(), before)
        self.assertEqual(self.add(source, extra=('--replace',))[0], 0)
        self.assertEqual((self.root / record['path']).read_bytes(), source.read_bytes())
        self.assertNotEqual(self.catalog()['courses'][0]['files'][0]['sha256'], record['sha256'])

    def test_bad_pdf_prevents_partial_import(self):
        valid, invalid = self.source('valid.txt'), self.source('broken.pdf', 'not a PDF')
        code, output = self.add(valid, invalid)
        self.assertEqual(code, 1)
        self.assertIn('PDF 无法读取', output)
        self.assertFalse((self.root / 'courses').exists())
        self.assertEqual(self.catalog()['courses'], [])

    def test_pdf_page_count_and_source_unchanged(self):
        from pypdf import PdfWriter
        source = self.sources / '中文讲义.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.add_blank_page(width=595, height=842)
        writer.write(source)
        before = source.read_bytes()
        self.assertEqual(self.add(source)[0], 0)
        file = self.catalog()['courses'][0]['files'][0]
        self.assertEqual(file['pages'], 2)
        self.assertEqual((self.root / file['path']).read_bytes(), before)
        self.assertEqual(source.read_bytes(), before)

    def test_nested_folder_skips_temporary_and_unsupported_files(self):
        self.source('chapter/第1章.txt')
        self.source('~$临时.docx')
        self.source('secret.env')
        self.source('.hidden/hidden.txt')
        self.source('_cache/cache.txt')
        code, output = self.add(self.sources)
        self.assertEqual(code, 0, output)
        files = self.catalog()['courses'][0]['files']
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0]['path'].endswith('chapter/第1章.txt'))

    def test_missing_files_require_explicit_catalog_removal(self):
        self.add(self.source())
        file = self.catalog()['courses'][0]['files'][0]
        (self.root / file['path']).unlink()
        code, output = self.cli('sync')
        self.assertEqual(code, 1)
        self.assertIn('--allow-removals', output)
        self.assertEqual(len(self.catalog()['courses'][0]['files']), 1)
        self.assertEqual(self.cli('sync', '--allow-removals')[0], 0)
        self.assertEqual(self.catalog()['courses'][0]['files'], [])

    def test_invalid_folder_and_duplicate_source_conflict(self):
        source = self.source()
        code, output = self.cli('add', '--course', '../outside', '--category', '课件', source)
        self.assertEqual(code, 1)
        duplicate = self.base / 'other' / source.name
        duplicate.parent.mkdir()
        duplicate.write_text('other bytes', encoding='utf-8')
        code, output = self.add(source, duplicate)
        self.assertEqual(code, 1)
        self.assertIn('重名冲突', output)
        self.assertFalse((self.root / 'courses').exists())

    def test_size_limit_prevents_import(self):
        source = self.source(content='long content')
        with patch.object(updater, 'MAX_BYTES', 2):
            code, output = self.add(source)
        self.assertEqual(code, 1)
        self.assertFalse((self.root / 'courses').exists())

    def test_transaction_rolls_back_on_write_failure(self):
        target = self.root / 'old.txt'
        target.write_bytes(b'original')
        replace = os.replace
        calls = 0

        def fail_once(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('simulated disk error')
            return replace(source, destination)

        with patch.object(updater.os, 'replace', side_effect=fail_once):
            with self.assertRaises(OSError):
                updater.transaction(self.root, {'old.txt': 'replacement', 'new.txt': 'new'})
        self.assertEqual(target.read_bytes(), b'original')
        self.assertFalse((self.root / 'new.txt').exists())

    def test_interactive_new_course_save_and_cancel(self):
        source = self.source()
        answers = ['1', '1', '模拟电子技术', 'Analog Electronics', '2', '2']
        with patch('builtins.input', side_effect=answers), patch.object(updater, 'refresh', return_value=False), \
                patch.object(updater, 'pick_sources', return_value=[str(source)]):
            code, output = self.cli()
        self.assertEqual(code, 0, output)
        self.assertEqual(len(self.catalog()['courses']), 1)
        before = (self.root / 'catalog.json').read_bytes()
        with patch('builtins.input', side_effect=['1', '1', '1']), patch.object(updater, 'refresh', return_value=False), \
                patch.object(updater, 'pick_sources', return_value=[]):
            code, output = self.cli()
        self.assertEqual(code, 0, output)
        self.assertEqual((self.root / 'catalog.json').read_bytes(), before)

    @unittest.skipUnless(shutil.which('git'), 'requires Git')
    def test_publish_to_local_bare_remote_and_retry_failed_push(self):
        def git(*args, root=None):
            return subprocess.run(['git', *args], cwd=root or self.root, check=True,
                                  capture_output=True, text=True, encoding='utf-8')
        git('init', '-b', 'main')
        git('config', 'user.name', 'Test')
        git('config', 'user.email', 'test@example.invalid')
        git('config', 'core.autocrlf', 'true')
        shutil.copy2(Path(__file__).parents[1] / '.gitattributes', self.root / '.gitattributes')
        git('add', '.')
        git('commit', '-m', 'initial')
        remote = self.base / 'remote.git'
        git('init', '--bare', str(remote))
        git('remote', 'add', 'origin', str(remote))
        git('push', '-u', 'origin', 'main')
        source = self.source('笔记 #1 [初稿].md')
        source.write_bytes('原始内容\r\nSecond line\r\n'.encode('utf-8'))
        self.assertEqual(self.add(source)[0], 0)
        config, catalog = updater.read_json(self.root / 'library.json'), self.catalog()
        real_git = updater.git

        def fail_push(root, *args, **kwargs):
            if args[:1] == ('push',):
                raise updater.LibraryError('simulated offline push')
            return real_git(root, *args, **kwargs)

        # Only bypass GitHub-specific identity/auth checks; Git staging, commits,
        # fetch state, and pushes use a real disposable local remote.
        with patch.object(updater, 'refresh', return_value=False):
            with patch.object(updater, 'git', side_effect=fail_push):
                with self.assertRaises(updater.LibraryError):
                    updater.publish(self.root, config, catalog, wait=False)
            self.assertIn('Update learning materials', git('log', '-1', '--format=%s').stdout)
            self.assertEqual(git('status', '--porcelain').stdout, '')
            self.assertTrue(updater.publish(self.root, config, catalog, wait=False))
        self.assertEqual(git('rev-parse', 'HEAD').stdout.strip(),
                         git('--git-dir=' + str(remote), 'rev-parse', 'main').stdout.strip())
        self.assertEqual(json.loads(git('--git-dir=' + str(remote), 'show', 'main:catalog.json').stdout), catalog)
        blob = subprocess.run(['git', '--git-dir=' + str(remote), 'show', 'main:' + catalog['courses'][0]['files'][0]['path']],
                              check=True, capture_output=True).stdout
        self.assertEqual(blob, source.read_bytes(), 'Imported text must retain original CRLF bytes in Git')


if __name__ == '__main__':
    unittest.main()
