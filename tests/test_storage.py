from unittest import TestCase
from uuid import uuid4 as v4

from conjure.storage import LmdbCollection, LocalCollectionWithBackup


class TestStorage(TestCase):

    def setUp(self) -> None:
        self.path = v4().hex
        self.backup_path = v4().hex
        self.backup = LmdbCollection(f'/temp/{self.path}')
        self.db = LocalCollectionWithBackup(
            f'/temp/{self.path}', 
            remote_bucket=None, 
            content_type='text/plain',
            is_public=False,
            local_backup=self.backup)

    def tearDown(self) -> None:
        self.backup.destroy()
        self.db.destroy()

    def test_writes_go_to_both_databases(self):
        self.fail()
    
    def test_read_after_write(self):
        self.fail()
    
    def test_reads_from_backup(self):
        self.fail()
    
    def test_writes_to_local_on_backup_read(self):
        self.fail()