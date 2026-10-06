import datetime as dt
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location('metadata', Path(__file__).with_name('prepare-publication-metadata.py'))
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)

class PublicationMetadataTest(unittest.TestCase):
    def test_history_rename_update_and_explicit_date(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args, time=None):
                env = dict(os.environ)
                if time:
                    env.update(GIT_AUTHOR_DATE=time, GIT_COMMITTER_DATE=time)
                return subprocess.check_output(['git', '-C', directory, *args], env=env, stderr=subprocess.DEVNULL)
            git('init'); git('config', 'user.name', 'Test'); git('config', 'user.email', 'test@example.invalid')
            content = repo / 'content'; content.mkdir()
            original = content / '日本語.md'
            original.write_text('---\ntitle: First\ndraft: false\n---\nBody\n')
            git('add', '.'); git('commit', '-m', 'first', time='2026-10-05T16:30:00+00:00')
            renamed = content / 'renamed.md'
            git('mv', 'content/日本語.md', 'content/renamed.md')
            git('commit', '-m', 'rename', time='2026-10-06T02:00:00+00:00')
            # Reproduce an older undated first post, then a fixed client stamping its update.
            renamed.write_text(metadata.set_scalar(renamed.read_text() + 'Update\n', 'published', '2026-10-06T05:39:05+00:00'))
            explicit = content / 'explicit.md'
            explicit.write_bytes(b'---\r\ndate: "2020-01-02" # keep\r\npublished: 2020-01-02T01:00:00+09:00\r\n---\r\nBody\r\n')
            draft = content / 'draft.md'; draft.write_text('---\ndraft: true\n---\nDraft\n')
            git('add', '.'); git('commit', '-m', 'update', time='2026-10-06T05:39:06+00:00')
            before = explicit.read_bytes()
            self.assertEqual(metadata.prepare(content, ZoneInfo('Asia/Tokyo')), 1)
            self.assertEqual(metadata.scalar(renamed.read_text(), 'date'), '2026-10-06')
            self.assertEqual(metadata.scalar(renamed.read_text(), 'published'), '2026-10-05T16:30:00+00:00')
            self.assertTrue(renamed.read_text().endswith('Body\nUpdate\n'))
            self.assertEqual(explicit.read_bytes(), before)
            self.assertEqual(metadata.scalar(draft.read_text(), 'date'), '')
            self.assertEqual(metadata.prepare(content, ZoneInfo('Asia/Tokyo')), 0)

    def test_empty_metadata_crlf_and_invalid_dates(self):
        source = '---\r\ndate: ""\r\npublished:\r\n---\r\n本文\r\n'
        updated = metadata.set_scalar(metadata.set_scalar(source, 'date', '2026-10-06'), 'published', '2026-10-06T05:39:06+00:00')
        self.assertEqual(metadata.scalar(updated, 'date'), '2026-10-06')
        self.assertEqual(metadata.scalar(updated, 'published'), '2026-10-06T05:39:06+00:00')
        self.assertTrue(updated.endswith('本文\r\n'))
        self.assertFalse(metadata.valid_date('2026-02-31'))
        self.assertFalse(metadata.valid_published('2026-02-31T05:39:06+00:00'))

if __name__ == '__main__':
    unittest.main()
