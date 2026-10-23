"""Changed bytes are new Rex versions; renames remain the same local media."""
import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scud.db import Database
from scud.scanner import Scanner


class FileVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.media = root / 'media'
        self.file = self.media / 'Show' / 'Show.S01E01.mkv'
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b'old media')
        self.db = Database(root / 'state.db')
        app = SimpleNamespace(db=self.db, log=logging.getLogger('version-tests'), config={
            'libraries': [{'id': 'tv', 'type': 'show', 'path': str(self.media), 'rex_library_key': '4'}]})
        self.scanner = Scanner(app)
        self.scanner.sync = Mock()
        self.matcher = patch('scud.scanner.Matcher').start()
        self.addCleanup(patch.stopall)
        self.matcher.return_value.match_file.return_value = {
            'status': 'matched', 'ids': {'tmdb': '2430'}, 'method': 'tmdb-title-search'}
        self.probe = patch('scud.scanner.ffprobe', return_value=(
            {'streams': [{'codec_type': 'video', 'codec_name': 'h264'}]}, None)).start()
        self.scanner.scan_once()
        self.original = self.row()

    def row(self):
        return self.db.list_media()[0]

    def replace(self, data):
        before = self.file.stat()
        self.file.write_bytes(data)
        # Make size-preserving replacements deterministic on coarse clocks.
        os.utime(self.file, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        self.assertEqual(before.st_ino, self.file.stat().st_ino)
        self.scanner.scan_once()
        return self.row()

    def test_changed_bytes_rotate_feed_and_file_but_keep_manual_match_and_numbers(self):
        with self.db.connect() as conn:
            conn.execute("UPDATE media SET match_method='manual',tmdb_id='9760',season=9,episode=2,numbering_manual=1")
        self.probe.return_value = ({'streams': [{'codec_type': 'video', 'codec_name': 'hevc'}]}, None)
        updated = self.replace(b'new and larger media')
        self.assertEqual(updated['id'], self.original['id'])
        self.assertEqual((updated['tmdb_id'], updated['season'], updated['episode']), ('9760', 9, 2))
        self.assertNotEqual(self.scanner.feed_id(updated), self.scanner.feed_id(self.original))
        payload = self.scanner.feed_item(updated)
        self.assertNotEqual(payload['file'], '/scud/' + payload['path'])
        self.assertEqual(payload['path'], 'tv/Show/Show.S01E01.mkv')
        self.assertEqual(payload['media_info']['streams'][0]['codec_name'], 'hevc')
        self.scanner.sync.assert_called_with([updated['id']], [self.scanner.feed_id(self.original)])
        # The ID survives a process/database reopen and an unchanged scan.
        version = updated['rex_feed_id']
        self.scanner.scan_once()
        self.assertEqual(self.row()['rex_feed_id'], version)
        self.assertEqual(Database(self.db.path).get_media(updated['id'])['rex_feed_id'], version)

    def test_equal_size_replacement_and_repeated_replacement_have_distinct_labels(self):
        first = self.replace(b'new media')
        second = self.replace(b'NEW MEDIA')
        self.assertEqual(first['size'], self.original['size'])
        self.assertEqual(second['size'], first['size'])
        self.assertNotEqual(self.scanner.feed_id(first), self.scanner.feed_id(second))
        self.assertNotEqual(self.scanner.feed_item(first)['file'], self.scanner.feed_item(second)['file'])
        self.scanner.sync.assert_called_with([second['id']], [self.scanner.feed_id(first)])

    def test_rename_preserves_original_and_versioned_feed_ids_without_reprobing(self):
        for replacement in (False, True):
            if replacement:
                self.replace(b'replacement')
            before = self.row()
            calls = self.probe.call_count
            target = self.file.with_name('Renamed.S01E01.mkv' if not replacement else 'Again.S01E01.mkv')
            self.file.rename(target)
            self.file = target
            self.scanner.scan_once()
            after = self.row()
            self.assertEqual(self.scanner.feed_id(before), self.scanner.feed_id(after))
            self.assertEqual(self.probe.call_count, calls)
            self.scanner.sync.assert_called_with([after['id']], [])

    def test_replaced_bonus_gets_distinct_id_and_label_in_parent_folder(self):
        parent = self.row()
        extra = {**parent, 'id': 'bonus', 'relpath': 'Show/Extras/Behind the Scenes.mkv',
                 'season': None, 'episode': None}
        old = self.scanner.feed_item(extra, self.scanner.feed_parents([parent]))
        new = self.scanner.feed_item({**extra, 'rex_feed_id': 'bonus-v-123'}, self.scanner.feed_parents([parent]))
        self.assertNotEqual(old['id'], new['id'])
        self.assertNotEqual(old['file'], new['file'])
        self.assertEqual(Path(old['file']).parent, Path(new['file']).parent)
        self.assertEqual(old['path'], new['path'])

    def test_atomic_replacement_keeps_matches_and_can_then_be_renamed(self):
        with self.db.connect() as conn:
            conn.execute("UPDATE media SET match_method='manual',tmdb_id='9760'")
        before = self.file.stat()
        replacement = self.file.with_suffix('.new')
        replacement.write_bytes(b'new media')
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertNotEqual(before.st_ino, replacement.stat().st_ino)
        replacement.replace(self.file)
        self.scanner.scan_once()
        after = self.row()
        self.assertEqual(after['id'], self.original['id'])
        self.assertEqual(after['tmdb_id'], '9760')
        self.assertNotEqual(self.scanner.feed_id(after), self.scanner.feed_id(self.original))
        self.assertEqual(self.probe.call_count, 2)
        target = self.file.with_name('Moved.S01E01.mkv')
        self.file.rename(target)
        self.scanner.scan_once()
        self.assertEqual(self.row()['rex_feed_id'], after['rex_feed_id'])
        self.assertEqual(self.probe.call_count, 2)

    def test_failed_reprobe_does_not_reuse_old_stream_metadata(self):
        self.probe.return_value = (None, 'probe failed')
        updated = self.replace(b'incomplete replacement')
        self.assertNotEqual(self.scanner.feed_id(updated), self.scanner.feed_id(self.original))
        self.assertIsNone(self.scanner.feed_item(updated)['media_info'])
        self.assertEqual(updated['probe_error'], 'probe failed')
        self.scanner.sync.assert_called_with([updated['id']], [self.scanner.feed_id(self.original)])
