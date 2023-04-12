from unittest import TestCase
from urllib.parse import urlparse
from uuid import uuid4 as v4
from conjure.storage import LmdbCollection, LocalCollectionWithBackup
import logging

logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('nose').setLevel(logging.CRITICAL)
logging.getLogger('s3transfer').setLevel(logging.CRITICAL)


class TestExploratory(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = v4().hex
        cls.bucket_name = 'conjure-test'
        cls.db = LocalCollectionWithBackup(
            f'/tmp/{cls.path}',
            remote_bucket=cls.bucket_name,
            content_type='text/plain',
            is_public=True)

    # @classmethod
    # def tearDownClass(cls) -> None:
    #     for key in cls.db.iter_prefix(start_key=''):
    #         del cls.db[key]

    def test_supports_public_uri(self):
        key = v4().hex
        value = b'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        self.db[key] = value

        self.assertEqual(
            urlparse(f'https://conjure-test.s3.amazonaws.com/{key}'),
            self.db.public_uri(key))

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

        backup_keys = list(
            filter(lambda x: x in keys, self.db._remote.iter_prefix('')))

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

    def test_does_not_support_public_uri(self):
        key = b'key'
        value = b'value'
        self.db[key] = value

        self.assertRaises(NotImplementedError, lambda: self.db.public_uri(key))

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

        self.assertEqual(set(keys), set(read_keys))

    def test_correct_number_of_keys(self):
        n_keys = 20

        read_keys = list(self.db.iter_prefix(''))
        self.assertEqual(0, len(read_keys))

        keys = [v4().hex.encode() for _ in range(n_keys)]
        for key in keys:
            self.db[key] = key

        read_keys = list(self.db.iter_prefix(''))
        self.assertEqual(n_keys, len(read_keys))

    def test_feed_has_correct_number_of_items(self):
        keys = [v4().hex.encode() for _ in range(10)]
        for key in keys:
            self.db[key] = key

        feed_items = list(self.db.feed(offset=''))
        self.assertEqual(10, len(feed_items))
    
    def test_feed_can_handle_offset_of_none(self):
        keys = [v4().hex.encode() for _ in range(10)]
        for key in keys:
            self.db[key] = key

        feed_items = list(self.db.feed())
        self.assertEqual(10, len(feed_items))
    

    def test_feed_respects_offset(self):
        base_key = v4().hex

        keys = [f'{base_key}_{v4().hex}' for _ in range(10)]
        for key in keys:
            self.db[key] = key

        feed_items = list(self.db.feed())
        self.assertEqual(10, len(feed_items))

        middle = feed_items[5]['timestamp']
        truncated_feed = list(self.db.feed(offset=middle))

        self.assertEqual(5, len(truncated_feed))
