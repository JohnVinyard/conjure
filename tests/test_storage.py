from typing import Callable
from unittest import TestCase
import unittest
from uuid import uuid4 as v4
import os
from conjure.storage import LmdbCollection, LocalCollectionWithBackup
import logging
from time import sleep

logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('nose').setLevel(logging.CRITICAL)
logging.getLogger('s3transfer').setLevel(logging.CRITICAL)



def retry(func: Callable, max_tries: int = 10, wait_time_seconds=1):
    exc = None
    for i in range(max_tries):
        try:
            func()
        except Exception as e:
            exc = e
            sleep(wait_time_seconds)
            continue
        
        return

    raise exc

class TestExploratory(TestCase):


    @classmethod
    def setUpClass(cls) -> None:
        cls.path = v4().hex
        cls.db = LocalCollectionWithBackup(
            f'/tmp/{cls.path}', 
            remote_bucket='conjure-test', 
            content_type='text/plain',
            is_public=True)
    
    @classmethod
    def tearDownClass(cls) -> None:
        pass

    def exists_after_write(self):
        key = v4().hex
        value = b'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        self.db[key] = value

        self.assertIn(key, self.db)
        self.assertIn(key, self.db._remote)
    
    def test_read_after_write(self):
        key = v4().hex
        value = b'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        self.db[key] = value

        read = self.db[key]
        self.assertEqual(read, value)

        read = self.db._remote[key]
        self.assertEqual(read, value)
    
    def test_iter_keys(self):
        keys = [v4().hex.encode() for _ in range(10)]
        for key in keys:
            self.db[key] = key
        
        read_keys = list(filter(lambda x: x in keys, self.db.iter_prefix('')))


        self.assertEqual(set(keys), set(read_keys))

        # sleep(10)

        backup_keys = list(filter(lambda x: x in keys, self.db._remote.iter_prefix('')))
        print(backup_keys)

        self.assertEqual(set(backup_keys), set(read_keys))
        
        # retry(check_backup_keys, max_tries=20, wait_time_seconds=2)


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
    

    def test_iter_keys(self):
        keys = [v4().hex.encode() for _ in range(10)]
        for key in keys:
            self.db[key] = key
        
        read_keys = list(filter(lambda x: x in keys, self.db.iter_prefix('')))

        print(read_keys)

        self.assertEqual(set(keys), set(read_keys))

