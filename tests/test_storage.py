from unittest import TestCase
from uuid import uuid4 as v4
import os
from conjure.storage import LmdbCollection, LocalCollectionWithBackup


class TestStorage(TestCase):

    def setUp(self) -> None:
        self.path = v4().hex
        self.backup_path = v4().hex
        self.backup = LmdbCollection(f'/tmp/{self.backup_path}')
        self.db = LocalCollectionWithBackup(
            f'/tmp/{self.path}', 
            remote_bucket=None, 
            content_type='text/plain',
            is_public=False,
            local_backup=self.backup)

    def tearDown(self) -> None:
        self.db.destroy()

    def test_writes_go_to_both_databases(self):
        key = b'key'
        value = b'value'
        self.db[key] = value

        self.assertIn(key, self.db._local)
        self.assertIn(key, self.backup)
    
    def test_read_after_write(self):
        key = b'key'
        value = b'value'
        self.db[key] = value

        read = self.db[key]
        self.assertEqual(read, value)
    
    def test_reads_from_backup(self):
        key = b'key'
        value = b'value'
        self.db[key] = value

        del self.db._local[key]

        read = self.db[key]

        self.assertEqual(read, value)
    
    def test_writes_to_local_on_backup_read(self):
        key = b'key'
        value = b'value'
        self.db[key] = value

        del self.db._local[key]

        read = self.db[key]
        self.assertEqual(read, value)
        self.assertIn(key, self.db._local)