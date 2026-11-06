from unittest import TestCase
from urllib.parse import urlparse
from uuid import uuid4 as v4
from conjure.storage import LmdbCollection, LocalCollectionWithBackup, SqliteCollection
import logging
import multiprocessing
from conjure.contenttype import SupportedContentType

logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('nose').setLevel(logging.CRITICAL)
logging.getLogger('s3transfer').setLevel(logging.CRITICAL)


class TestExploratory(TestCase):
    collection_class = LmdbCollection

    @classmethod
    def setUpClass(cls) -> None:
        cls.content_type = 'text/plain'
        cls.path = v4().hex
        cls.bucket_name = 'conjure-test'
        cls.db = LocalCollectionWithBackup(
            f'tests/tmp/{cls.path}',
            remote_bucket=cls.bucket_name,
            is_public=True,
            cors_enabled=True,
            local_collection_class=cls.collection_class)
    
    def test_can_delete(self):
        key = v4().hex
        value = b'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        self.db.put(key, value, self.content_type)

        self.assertIn(key, self.db)
        self.assertIn(key, self.db._remote)
        
        del self.db[key]
        
        self.assertNotIn(key, self.db)
        self.assertNotIn(key, self.db._remote)
        

    def test_supports_public_uri(self):
        key = v4().hex
        value = b'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        self.db.put(key, value, self.content_type)

        self.assertEqual(
            urlparse(f'https://conjure-test.s3.amazonaws.com/{key}'),
            self.db.public_uri(key))

    def exists_after_write(self):
        key = v4().hex
        value = b'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        self.db.put(key, value, self.content_type)

        self.assertIn(key, self.db)
        self.assertIn(key, self.db._remote)

    def test_read_after_write(self):
        key = v4().hex
        value = b'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
        self.db.put(key, value, self.content_type)

        read = self.db[key]
        self.assertEqual(read, value)

        read = self.db._remote[key]
        self.assertEqual(read, value)

    def test_iter_keys(self):
        keys = [v4().hex.encode() for _ in range(10)]
        for key in keys:
            self.db.put(key, key, self.content_type)

        read_keys = list(filter(lambda x: x in keys, self.db.iter_prefix('')))

        self.assertEqual(set(keys), set(read_keys))

        backup_keys = list(
            filter(lambda x: x in keys, self.db._remote.iter_prefix('')))

        self.assertEqual(set(backup_keys), set(read_keys))


class TestStorage(TestCase):
    collection_class = LmdbCollection

    def setUp(self) -> None:
        self.content_type = 'application/text-plain'
        self.path = v4().hex
        self.backup_path = v4().hex
        self.backup = self.collection_class(f'tests/tmp/{self.backup_path}')
        self.db = LocalCollectionWithBackup(
            f'tests/tmp/{self.path}',
            remote_bucket=None,
            is_public=False,
            local_backup=self.backup,
            local_collection_class=self.collection_class)

    def tearDown(self) -> None:
        self.db.destroy()

    def test_does_not_support_public_uri(self):
        key = b'key'
        value = b'value'
        self.db.put(key, value, self.content_type)

        self.assertRaises(NotImplementedError, lambda: self.db.public_uri(key))

    def test_writes_go_to_both_databases(self):
        key = b'key'
        value = b'value'
        self.db.put(key, value, self.content_type)

        self.assertIn(key, self.db._local)
        self.assertIn(key, self.backup)

    def test_read_after_write(self):
        key = b'key'
        value = b'value'
        self.db.put(key, value, self.content_type)

        read = self.db[key]
        self.assertEqual(read, value)
    
    
    def test_can_delete(self):
        key = b'key'
        value = b'value'
        self.db.put(key, value, self.content_type)

        read = self.db[key]
        self.assertEqual(read, value)
        
        del self.db[key]
        
        self.assertNotIn(key, self.db)

    def test_reads_from_backup(self):
        key = b'key'
        value = b'value'
        self.db.put(key, value, self.content_type)

        del self.db._local[key]

        read = self.db[key]

        self.assertEqual(read, value)

    def test_writes_to_local_on_backup_read(self):
        key = b'key'
        value = b'value'
        self.db.put(key, value, self.content_type)

        del self.db._local[key]

        read = self.db[key]
        self.assertEqual(read, value)
        self.assertIn(key, self.db._local)

    def test_iter_keys(self):
        keys = [v4().hex.encode() for _ in range(10)]
        for key in keys:
            self.db.put(key, key, self.content_type)

        read_keys = list(filter(lambda x: x in keys, self.db.iter_prefix('')))

        self.assertEqual(set(keys), set(read_keys))

    def test_correct_number_of_keys(self):
        n_keys = 20

        read_keys = list(self.db.iter_prefix(''))
        self.assertEqual(0, len(read_keys))

        keys = [v4().hex.encode() for _ in range(n_keys)]
        for key in keys:
            self.db.put(key, key, self.content_type)

        read_keys = list(self.db.iter_prefix(''))
        self.assertEqual(n_keys, len(read_keys))

    def test_feed_has_correct_number_of_items(self):
        keys = [v4().hex.encode() for _ in range(10)]
        for key in keys:
            self.db.put(key, key, self.content_type)

        feed_items = list(self.db.feed(offset=''))
        self.assertEqual(10, len(feed_items))
    
    def test_feed_can_handle_offset_of_none(self):
        keys = [v4().hex.encode() for _ in range(10)]
        for key in keys:
            self.db.put(key, key, self.content_type)

        feed_items = list(self.db.feed())
        self.assertEqual(10, len(feed_items))
    

    def test_feed_respects_offset(self):
        base_key = v4().hex

        keys = [f'{base_key}_{v4().hex}' for _ in range(10)]
        for key in keys:
            self.db.put(key, key, self.content_type)

        feed_items = list(self.db.feed())
        self.assertEqual(10, len(feed_items))

        middle = feed_items[5]['timestamp']
        truncated_feed = list(self.db.feed(offset=middle))

        self.assertEqual(5, len(truncated_feed))


class SqliteTestExploratory(TestExploratory):
    collection_class = SqliteCollection


class SqliteTestStorage(TestStorage):
    collection_class = SqliteCollection


def _write_keys(path: str, worker: int, n_keys: int):
    db = SqliteCollection(path)
    for i in range(n_keys):
        key = f'worker{worker}_{i}'.encode()
        db.put(key, key * 100, 'application/octet-stream')
    db.close()


def _write_and_read_keys(db: SqliteCollection, worker: int, n_keys: int, failures):
    # note that db was opened in the parent process, before the fork
    for i in range(n_keys):
        key = f'worker{worker}_{i}'.encode()
        db.put(key, key, 'application/octet-stream')
        if db[key] != key:
            failures.put((worker, i))


class SqliteCollectionTests(TestCase):

    def setUp(self) -> None:
        self.path = f'tests/tmp/{v4().hex}.sqlite'
        self.db = SqliteCollection(self.path)
        self.content_type = 'text/plain'

    def tearDown(self) -> None:
        self.db.destroy()

    def test_missing_key_raises_key_error(self):
        self.assertRaises(KeyError, lambda: self.db[b'missing'])
        self.assertRaises(KeyError, lambda: self.db.content_length(b'missing'))
        self.assertNotIn(b'missing', self.db)

    def test_accepts_str_and_bytes_keys(self):
        self.db.put('key', 'value', self.content_type)
        self.assertEqual(b'value', self.db[b'key'])
        self.assertIn('key', self.db)
        self.assertIn(b'key', self.db)

    def test_content_length(self):
        self.db.put(b'key', b'x' * 1234, self.content_type)
        self.assertEqual(1234, self.db.content_length(b'key'))

    def test_overwrite_replaces_value(self):
        self.db.put(b'key', b'first', self.content_type)
        self.db.put(b'key', b'second', self.content_type)
        self.assertEqual(b'second', self.db[b'key'])
        self.assertEqual(1, len(list(self.db.iter_prefix(''))))

    def test_deleting_missing_key_does_not_raise(self):
        del self.db[b'missing']

    def test_iter_prefix_is_ordered_and_respects_prefix(self):
        for key in [b'b_2', b'a_1', b'b_1', b'c_1', b'b_3']:
            self.db.put(key, key, self.content_type)

        self.assertEqual(
            [b'b_1', b'b_2', b'b_3'],
            list(self.db.iter_prefix(b'b', prefix=b'b')))
        self.assertEqual(
            [b'b_2', b'b_3'],
            list(self.db.iter_prefix(b'b_2', prefix=b'b')))
        self.assertEqual(
            [b'a_1', b'b_1', b'b_2', b'b_3', b'c_1'],
            list(self.db.iter_prefix('')))

    def test_iter_prefix_pages_through_many_keys(self):
        n_keys = SqliteCollection._PAGE_SIZE * 3 + 7
        keys = sorted(f'{i:05d}'.encode() for i in range(n_keys))
        for key in keys:
            self.db.put(key, key, self.content_type)

        self.assertEqual(keys, list(self.db.iter_prefix('')))

    def test_can_write_while_iterating(self):
        n_keys = SqliteCollection._PAGE_SIZE * 2
        for i in range(n_keys):
            self.db.put(f'a_{i:05d}', b'value', self.content_type)

        count = 0
        for key in self.db.iter_prefix('a', prefix='a'):
            # this would deadlock if iteration held the write lock
            self.db.put(b'b_' + key, b'value', self.content_type)
            count += 1

        self.assertEqual(n_keys, count)
        self.assertEqual(n_keys, len(list(self.db.iter_prefix('b', 'b'))))

    def test_feed_records_writes_in_order(self):
        keys = [f'func_{i}'.encode() for i in range(5)]
        for key in keys:
            self.db.put(key, key, self.content_type)

        feed = list(self.db.feed())
        self.assertEqual(keys, [item['key'] for item in feed])
        self.assertEqual(feed[-1]['timestamp'], self.db.offset)

    def test_offset_is_none_initially(self):
        self.assertIsNone(self.db.offset)

    def test_index_storage_is_isolated_from_data(self):
        index = self.db.index_storage('my_index')

        self.db.put(b'key', b'data value', self.content_type)
        index.put(b'key', b'index value', self.content_type)
        index.set_offset(b'some_offset')

        self.assertEqual(b'data value', self.db[b'key'])
        self.assertEqual(b'index value', index[b'key'])
        self.assertEqual(b'some_offset', index.offset)
        self.assertNotEqual(b'some_offset', self.db.offset)
        self.assertRaises(NotImplementedError, lambda: list(index.feed()))

        del index[b'key']
        self.assertIn(b'key', self.db)
        self.assertNotIn(b'key', index)

    def test_data_persists_after_reopening(self):
        self.db.put(b'key', b'value', self.content_type)
        self.db.close()

        reopened = SqliteCollection(self.path)
        self.assertEqual(b'value', reopened[b'key'])
        self.assertEqual(1, len(list(reopened.feed())))
        reopened.close()

    def test_failed_transaction_writes_nothing(self):
        def fail():
            with self.db.transaction() as txn:
                txn.execute(
                    "INSERT INTO data (namespace, key, value) VALUES (?, ?, ?)",
                    (self.db.namespace, b'key', b'value'))
                raise ValueError()

        self.assertRaises(ValueError, fail)
        self.assertNotIn(b'key', self.db)

    def test_rejects_newer_schema_version(self):
        with self.db.transaction() as txn:
            txn.execute(f'PRAGMA user_version = {SqliteCollection.SCHEMA_VERSION + 1}')
        self.db.close()

        self.assertRaises(RuntimeError, lambda: SqliteCollection(self.path))

    def test_supports_public_uri_when_port_is_provided(self):
        db = SqliteCollection(self.path, port=8888)
        self.assertEqual(
            urlparse('http://localhost:8888/functions/func/func_key'),
            db.public_uri(b'func_key'))
        db.close()

    def test_does_not_support_public_uri_without_port(self):
        self.assertRaises(NotImplementedError, lambda: self.db.public_uri(b'key'))

    def test_concurrent_writers_in_separate_processes(self):
        n_workers = 8
        n_keys = 50

        ctx = multiprocessing.get_context('spawn')
        processes = [
            ctx.Process(target=_write_keys, args=(self.path, i, n_keys))
            for i in range(n_workers)]
        for p in processes:
            p.start()
        for p in processes:
            p.join(60)
            self.assertEqual(0, p.exitcode)

        keys = list(self.db.iter_prefix(''))
        self.assertEqual(n_workers * n_keys, len(keys))
        for key in keys:
            self.assertEqual(key * 100, self.db[key])
        self.assertEqual(n_workers * n_keys, len(list(self.db.feed())))

    def test_collection_opened_before_fork_works_in_child_processes(self):
        # this mirrors gunicorn, which forks workers after the application,
        # and therefore its storage, has been created
        if 'fork' not in multiprocessing.get_all_start_methods():
            self.skipTest('fork is not available on this platform')

        self.db.put(b'before_fork', b'value', self.content_type)

        n_workers = 4
        n_keys = 50
        ctx = multiprocessing.get_context('fork')
        failures = ctx.Queue()
        processes = [
            ctx.Process(
                target=_write_and_read_keys,
                args=(self.db, i, n_keys, failures))
            for i in range(n_workers)]
        for p in processes:
            p.start()
        for p in processes:
            p.join(60)
            self.assertEqual(0, p.exitcode)

        self.assertTrue(failures.empty())
        self.assertEqual(
            n_workers * n_keys + 1, len(list(self.db.iter_prefix(''))))
        # the parent's connection is still usable after the children exit
        self.assertEqual(b'value', self.db[b'before_fork'])

    def test_stores_content_type(self):
        self.db.put(b'text', b'value', 'text/plain')
        self.db.put(b'audio', b'value', SupportedContentType.Audio)
        self.db.put(b'none', b'value', None)

        rows = dict(self.db._connection.execute(
            'SELECT key, content_type FROM data').fetchall())
        self.assertEqual('text/plain', rows[b'text'])
        self.assertEqual('audio/wav', rows[b'audio'])
        self.assertIsNone(rows[b'none'])
