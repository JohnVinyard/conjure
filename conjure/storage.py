from contextlib import contextmanager
from enum import Enum
import os
from os import PathLike
import sqlite3
import threading
from typing import Callable, Iterable, Iterator, Union
from urllib.parse import ParseResult, urlparse
import lmdb
import boto3
from shutil import rmtree
from conjure.timestamp import timestamp_id


def get_account_id():
    client = boto3.client("sts")
    return client.get_caller_identity()["Account"]


def ensure_bytes(value: Union[str, bytes, memoryview]) -> bytes:
    if isinstance(value, memoryview):
        return bytes(value)

    return value if isinstance(value, bytes) else value.encode()


def ensure_str(value: Union[str, bytes]) -> str:
    return value if isinstance(value, str) else value.decode()


def _content_type_str(content_type) -> Union[str, None]:
    # content types may be plain strings, or SupportedContentType members
    if content_type is None or isinstance(content_type, str):
        return content_type
    if isinstance(content_type, Enum):
        return content_type.value
    return str(content_type)


class Collection(object):
    def __init__(self):
        super().__init__()

    def content_length(self, key) -> int:
        raise NotImplementedError()

    def __contains__(self, key):
        raise NotImplementedError()

    def iter_prefix(self, start_key, prefix=None) -> Iterable[bytes]:
        raise NotImplementedError()

    def put(self, key: bytes, value: bytes, content_type: str):
        raise NotImplementedError()

    def __getitem__(self, key) -> bytes:
        raise NotImplementedError()

    def __delitem__(self, key):
        raise NotImplementedError()

    def public_uri(self, key) -> ParseResult:
        raise NotImplementedError()

    def feed(self, offset: Union[bytes, str] = None):
        raise NotImplementedError()
    
    @property
    def offset(self):
        raise NotImplementedError()
    
    def set_offset(self, offset):
        raise NotImplementedError()
    

class S3Collection(Collection):

    def __init__(self, bucket, is_public=False, cors_enabled=False):
        super().__init__()
        self.bucket = bucket
        self.client = boto3.client('s3')
        self.is_public = is_public
        self.cors_enabled = cors_enabled

        self._create_bucket()
    
    @property
    def offset(self):
        raise NotImplementedError()
    
    def set_offset(self, offset):
        raise NotImplementedError()

    def public_uri(self, key: Union[bytes, str]):
        if not self.is_public:
            raise NotImplementedError()

        uri = f'https://{self.bucket}.s3.amazonaws.com/{ensure_str(key)}'
        parsed = urlparse(uri)
        return parsed

    @property
    def acl(self):
        return 'public-read' if self.is_public else 'private'

    def content_length(self, key) -> int:
        try:
            resp = self.client.get_object_attributes(
                Bucket=self.bucket, 
                Key=ensure_str(key),
                ObjectAttributes=['ObjectSize'])
            return resp['ObjectSize']
        except self.client.exceptions.NoSuchKey:
            raise KeyError(key)
        except Exception:
            return 0

    def destroy(self, prefix: str = ''):
        # first, delete all keys with the provided prefix
        for key in self.iter_prefix(prefix):
            k = ensure_str(key)
            print(f'deleting key {k}')
            self.client.delete_object(Bucket=self.bucket, Key=k)

        if prefix == '':
            print(f'deleting bucket {self.bucket}')
            self.client.delete_bucket(Bucket=self.bucket)


    def _create_bucket(self):

        try:
            self.client.create_bucket(
                Bucket=self.bucket,
                ObjectOwnership='ObjectWriter')
            self.client.delete_public_access_block(
                Bucket=self.bucket,
                ExpectedBucketOwner=get_account_id())
            self.client.put_bucket_acl(
                Bucket=self.bucket,
                ACL=self.acl,
                ExpectedBucketOwner=get_account_id())
        except self.client.exceptions.BucketAlreadyExists:
            pass

        if self.cors_enabled:
            self.client.put_bucket_cors(
                Bucket=self.bucket,
                CORSConfiguration={
                    'CORSRules': [
                        {
                            'AllowedMethods': ['GET'],
                            'AllowedOrigins': ['*'],
                            'MaxAgeSeconds': 3000
                        }
                    ]
                }
            )

    def __contains__(self, key):
        try:
            # TODO: This could be a head request
            self[ensure_str(key)]
            return True
        except KeyError:
            return False

    def iter_prefix(self, start_key: Union[str, bytes], prefix: Union[None, bytes, str] = None) -> Iterable[bytes]:

        resp = self.client.list_objects_v2(
            Bucket=self.bucket,
            StartAfter=ensure_str(start_key),
            Prefix=ensure_str(prefix) if prefix is not None else '',
        )

        try:
            contents = resp['Contents']
        except KeyError:
            return

        while True:
            for content in contents:
                yield ensure_bytes(content['Key'])

            if resp['IsTruncated']:
                resp = self.client.list_objects_v2(
                    Bucket=self.bucket,
                    StartAfter=ensure_str(start_key),
                    Prefix=ensure_str(prefix) if prefix is not None else '',
                    ContinuationToken=resp['NextContinuationToken']
                )
                contents = resp['Contents']
            else:
                break
    
    def __delitem__(self, key):
        self.client.delete_object(
            Bucket=self.bucket,
            Key=ensure_str(key)
        )

    def put(self, key: Union[bytes, str], value: bytes, content_type: str):
        self.client.put_object(
            Bucket=self.bucket,
            Key=ensure_str(key),
            Body=value,
            ContentType=content_type,
            ACL=self.acl)

    def __getitem__(self, key: Union[str, bytes]) -> bytes:
        try:
            resp = self.client.get_object(
                Bucket=self.bucket, Key=ensure_str(key))
            return resp['Body'].read()
        except:
            raise KeyError(key)


class LmdbCollection(Collection):
    def __init__(
            self,
            path: PathLike,
            extract_base_key: Callable[[bytes], bytes] = None,
            default_database_name: str = 'data',
            build_feed:bool = True,
            port=None):

        super().__init__()

        # KLUDGE: Delimiter is configurable elsewhere, so this might cause problems
        self.extract_base_key = extract_base_key or (
            lambda x: ensure_bytes(ensure_str(x).split('_')[0]))
        self.path = path
        self.build_feed = build_feed
        self.env = lmdb.open(
            self.path,
            max_dbs=10,
            # https://stackoverflow.com/a/37311228/1015178
            map_size=int(10e11), # one terabyte
            writemap=True,
            map_async=True,
            metasync=True,
            lock=False
        )
        self._default_database_name = ensure_bytes(default_database_name)
        self._data = self.env.open_db(self._default_database_name)
        self._offsets = self.env.open_db(b'offsets')

        self._port = port

        if self.build_feed:
            self._feed = self.env.open_db(b'feed')
    
    def public_uri(self, key: Union[bytes, str]):
        # TODO: This should be a subclass defined in serve.py
        if self._port is None:
            raise NotImplementedError()
        base = ensure_str(self.extract_base_key(key))
        k = ensure_str(key)

        uri = f'http://localhost:{self._port}/functions/{base}/{k}'
        parsed = urlparse(uri)
        return parsed

    @property
    def offset(self):
        with self.env.begin(write=False, db=self._offsets) as txn:
            offset = txn.get(self._default_database_name, db=self._offsets)
            return offset
    
    def set_offset(self, offset, txn=None):
        if txn:
            offset = txn.put(self._default_database_name, offset, db=self._offsets)
            return offset
        
        with self.env.begin(write=True, db=self._offsets) as txn:
            offset = txn.put(self._default_database_name, offset, db=self._offsets)
            return offset
    
    def index_storage(self, name):
        return LmdbCollection(
            self.path, 
            self.extract_base_key, 
            default_database_name=name, 
            build_feed=False)

    def destroy(self):
        self.env.close()
        rmtree(self.path)

    def feed(self, offset: Union[bytes, str] = None):
        if not self.build_feed:
            raise NotImplementedError('This storage instance has no feed')
        
        final_offset = offset or ''
        prefix = self.extract_base_key(ensure_bytes(final_offset))

        for i, key in enumerate(self.iter_prefix(final_offset, db=self._feed, prefix=prefix)):

            with self.env.begin(buffers=True, write=False, db=self._feed) as txn:
                memoryview_value = txn.get(key)
                value = bytes(memoryview_value)
                # a tuple of (time-based id, key)
                output = {'timestamp': key, 'key': value}
                yield output

    def content_length(self, key) -> int:
        with self.env.begin(buffers=True, write=False, db=self._data) as txn:
            value = txn.get(ensure_bytes(key))
            if value is None:
                raise KeyError(key)

            return len(value)

    def __contains__(self, key: Union[str, bytes]):
        try:
            self[ensure_bytes(key)]
            return True
        except KeyError:
            return False

    def iter_prefix(
            self,
            start_key: Union[str, bytes],
            prefix: Union[str, bytes, None] = None,
            db=None):

        if db is None:
            db = self._data

        start_key = ensure_bytes(start_key)
        if prefix is not None:
            prefix = ensure_bytes(prefix)

        with self.env.begin(write=True, buffers=True, db=db) as txn:
            cursor = txn.cursor()
            cursor.set_range(start_key)

            it = cursor.iternext(keys=True, values=False)
            for key in it:
                key = ensure_bytes(key)
                if prefix is not None and not key.startswith(prefix):
                    break
                yield key

    def __delitem__(self, key: Union[str, bytes]):
        with self.env.begin(write=True, db=self._data) as txn:
            txn.delete(ensure_bytes(key))

    def put(self, key: Union[str, bytes], value: Union[str, bytes], content_type: str):
        with self.env.begin(write=True, buffers=True, db=self._data) as txn:
            key = ensure_bytes(key)
            txn.put(key, ensure_bytes(value))

            if self.build_feed:
                timestamp = timestamp_id()
                base_key = self.extract_base_key(key)
                feed_key = ensure_bytes(
                    f'{base_key.decode()}_{timestamp.decode()}')
                txn.put(feed_key, key, db=self._feed)
                self.set_offset(feed_key, txn=txn)


    def __getitem__(self, key):
        with self.env.begin(buffers=True, write=False, db=self._data) as txn:
            value = txn.get(ensure_bytes(key))
            if value is None:
                raise KeyError(key)
            return bytes(value)


class SqliteCollection(Collection):
    """
    A local collection backed by a single SQLite file, opened in WAL mode.

    Unlike LMDB, this is safe to share between multiple processes (e.g.
    gunicorn workers) without any special care:  each process (and thread)
    lazily opens its own connection, so a collection created before a fork
    keeps working in the child processes.  Readers never block, and writers
    are serialized by SQLite, waiting up to `timeout` seconds for the lock.

    Several logical collections can share one file (see `index_storage`);
    each is identified by its `namespace`.

    Note that WAL mode does not work on network filesystems.
    """

    SCHEMA_VERSION = 1

    # number of rows fetched per query when iterating, so that no read
    # transaction is held open while the caller consumes a generator
    _PAGE_SIZE = 256

    def __init__(
            self,
            path: PathLike,
            extract_base_key: Callable[[bytes], bytes] = None,
            default_database_name: str = 'data',
            build_feed: bool = True,
            port=None,
            timeout: float = 30):

        super().__init__()

        # KLUDGE: Delimiter is configurable elsewhere, so this might cause problems
        self.extract_base_key = extract_base_key or (
            lambda x: ensure_bytes(ensure_str(x).split('_')[0]))
        self.path = os.fspath(path)
        self.namespace = ensure_str(default_database_name)
        self.build_feed = build_feed
        self.timeout = timeout
        self._port = port

        self._thread_local = threading.local()
        self._connections_lock = threading.Lock()
        self._connections = []

        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        # create the schema eagerly, so configuration problems surface early
        self._connection

    @property
    def _connection(self) -> sqlite3.Connection:
        # connections must never cross a fork, and sqlite3 connections should
        # not be shared between threads, so there's one per (process, thread)
        pid = os.getpid()
        conn = getattr(self._thread_local, 'conn', None)
        if conn is not None and self._thread_local.pid == pid:
            return conn

        conn = self._connect()
        self._thread_local.conn = conn
        self._thread_local.pid = pid
        with self._connections_lock:
            self._connections.append((pid, conn))
        return conn

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None means that transactions are managed explicitly
        conn = sqlite3.connect(
            self.path,
            timeout=self.timeout,
            isolation_level=None,
            check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        self._create_schema(conn)
        return conn

    def _create_schema(self, conn: sqlite3.Connection):
        with self._transaction(conn) as c:
            version = c.execute('PRAGMA user_version').fetchone()[0]
            if version == self.SCHEMA_VERSION:
                return
            if version > self.SCHEMA_VERSION:
                raise RuntimeError(
                    f'{self.path} has schema version {version}, but this '
                    f'version of conjure only understands up to {self.SCHEMA_VERSION}')

            c.execute('''
                CREATE TABLE IF NOT EXISTS data (
                    namespace TEXT NOT NULL,
                    key BLOB NOT NULL,
                    value BLOB NOT NULL,
                    content_type TEXT,
                    PRIMARY KEY (namespace, key)
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS feed (
                    namespace TEXT NOT NULL,
                    feed_key BLOB NOT NULL,
                    key BLOB NOT NULL,
                    PRIMARY KEY (namespace, feed_key)
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS offsets (
                    namespace TEXT PRIMARY KEY,
                    offset BLOB NOT NULL
                )
            ''')
            c.execute(f'PRAGMA user_version = {self.SCHEMA_VERSION}')

    @staticmethod
    @contextmanager
    def _transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        # IMMEDIATE takes the write lock up front, so the busy timeout applies,
        # rather than failing when a read lock is later upgraded to a write lock
        conn.execute('BEGIN IMMEDIATE')
        try:
            yield conn
        except BaseException:
            conn.execute('ROLLBACK')
            raise
        else:
            conn.execute('COMMIT')

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        A write transaction on this process's connection.  Everything
        executed within it is committed atomically, or not at all.
        """
        with self._transaction(self._connection) as conn:
            yield conn

    def public_uri(self, key: Union[bytes, str]):
        # TODO: This should be a subclass defined in serve.py
        if self._port is None:
            raise NotImplementedError()
        base = ensure_str(self.extract_base_key(key))
        k = ensure_str(key)

        uri = f'http://localhost:{self._port}/functions/{base}/{k}'
        parsed = urlparse(uri)
        return parsed

    @property
    def offset(self):
        row = self._connection.execute(
            'SELECT offset FROM offsets WHERE namespace = ?',
            (self.namespace,)).fetchone()
        return None if row is None else bytes(row[0])

    def set_offset(self, offset, txn: sqlite3.Connection = None):
        conn = txn or self._connection
        conn.execute(
            'INSERT OR REPLACE INTO offsets (namespace, offset) VALUES (?, ?)',
            (self.namespace, ensure_bytes(offset)))

    def index_storage(self, name):
        return SqliteCollection(
            self.path,
            self.extract_base_key,
            default_database_name=name,
            build_feed=False,
            timeout=self.timeout)

    def close(self):
        """
        Close every connection this instance opened in the current process
        """
        pid = os.getpid()
        with self._connections_lock:
            remaining = []
            for conn_pid, conn in self._connections:
                if conn_pid == pid:
                    conn.close()
                else:
                    remaining.append((conn_pid, conn))
            self._connections = remaining
        self._thread_local = threading.local()

    def destroy(self):
        self.close()
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(f'{self.path}{suffix}')
            except FileNotFoundError:
                pass

    def _iter_range(
            self,
            table: str,
            key_column: str,
            columns: str,
            start_key: bytes,
            prefix: Union[bytes, None]) -> Iterable[tuple]:
        """
        Yield rows with key >= start_key, in key order, stopping at the first
        key that doesn't begin with prefix, if one is provided.
        """
        conn = self._connection
        query = f'''
            SELECT {key_column}, {columns} FROM {table}
            WHERE namespace = ? AND {key_column} {{op}} ?
            ORDER BY {key_column}
            LIMIT {self._PAGE_SIZE}
        '''

        op = '>='
        last = start_key
        while True:
            rows = conn.execute(
                query.format(op=op), (self.namespace, last)).fetchall()
            for row in rows:
                key = bytes(row[0])
                if prefix is not None and not key.startswith(prefix):
                    return
                yield (key, *row[1:])

            if len(rows) < self._PAGE_SIZE:
                return

            op = '>'
            last = bytes(rows[-1][0])

    def feed(self, offset: Union[bytes, str] = None):
        if not self.build_feed:
            raise NotImplementedError('This storage instance has no feed')

        final_offset = ensure_bytes(offset or '')
        prefix = self.extract_base_key(final_offset)

        rows = self._iter_range('feed', 'feed_key', 'key', final_offset, prefix)
        for feed_key, key in rows:
            yield {'timestamp': feed_key, 'key': bytes(key)}

    def content_length(self, key) -> int:
        row = self._connection.execute(
            'SELECT length(value) FROM data WHERE namespace = ? AND key = ?',
            (self.namespace, ensure_bytes(key))).fetchone()
        if row is None:
            raise KeyError(key)
        return row[0]

    def __contains__(self, key: Union[str, bytes]):
        row = self._connection.execute(
            'SELECT 1 FROM data WHERE namespace = ? AND key = ?',
            (self.namespace, ensure_bytes(key))).fetchone()
        return row is not None

    def iter_prefix(
            self,
            start_key: Union[str, bytes],
            prefix: Union[str, bytes, None] = None) -> Iterable[bytes]:

        prefix = None if prefix is None else ensure_bytes(prefix)
        rows = self._iter_range(
            'data', 'key', '1', ensure_bytes(start_key), prefix)
        for key, _ in rows:
            yield key

    def __delitem__(self, key: Union[str, bytes]):
        with self.transaction() as txn:
            txn.execute(
                'DELETE FROM data WHERE namespace = ? AND key = ?',
                (self.namespace, ensure_bytes(key)))

    def put(self, key: Union[str, bytes], value: Union[str, bytes], content_type: str):
        key = ensure_bytes(key)

        with self.transaction() as txn:
            txn.execute(
                '''
                INSERT OR REPLACE INTO data (namespace, key, value, content_type)
                VALUES (?, ?, ?, ?)
                ''',
                (self.namespace, key, ensure_bytes(value), _content_type_str(content_type)))

            if self.build_feed:
                timestamp = timestamp_id()
                base_key = self.extract_base_key(key)
                feed_key = ensure_bytes(
                    f'{base_key.decode()}_{timestamp.decode()}')
                txn.execute(
                    'INSERT INTO feed (namespace, feed_key, key) VALUES (?, ?, ?)',
                    (self.namespace, feed_key, key))
                self.set_offset(feed_key, txn=txn)

    def __getitem__(self, key) -> bytes:
        row = self._connection.execute(
            'SELECT value FROM data WHERE namespace = ? AND key = ?',
            (self.namespace, ensure_bytes(key))).fetchone()
        if row is None:
            raise KeyError(key)
        return bytes(row[0])


class LocalCollectionWithBackup(Collection):
    def __init__(
            self,
            local_path,
            remote_bucket,
            is_public=False,
            local_backup=False,
            cors_enabled=False,
            local_collection_class=LmdbCollection):

        super().__init__()
        self.local_backup = local_backup

        self._local = local_collection_class(local_path)

        if isinstance(self.local_backup, Collection):
            self._remote = local_backup
        elif self.local_backup:
            self._remote = local_collection_class(f'{local_path}_backup')
        else:
            self._remote = S3Collection(
                remote_bucket, is_public=is_public, cors_enabled=cors_enabled)
    
    @property
    def offset(self):
        return self._local.offset
    
    def index_storage(self, name):
        return self._local.index_storage(name)
    
    def set_offset(self, offset):
        self._local.set_offset(offset)
    
    def feed(self, offset: Union[bytes, str] = None):
        return self._local.feed(offset)

    def content_length(self, key) -> int:
        try:
            return self._local.content_length(key)
        except KeyError:
            return self._remote.content_length(key)

    def public_uri(self, key) -> ParseResult:
        return self._remote.public_uri(key)

    def destroy(self):
        self._local.destroy()
        if self.local_backup:
            self._remote.destroy()

    def __delitem__(self, key):
        del self._local[key]
        del self._remote[key]

    def iter_prefix(self, start_key, prefix=None) -> Iterable[bytes]:
        # KLUDGE: What if we're starting from scratch on a new local machine
        # and the remote has everything?
        return self._local.iter_prefix(start_key, prefix)

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __getitem__(self, key) -> bytes:
        # first, try local
        try:
            return self._local[key]
        except KeyError:
            pass

        # then, try remote.  write to local
        # if the key is in the remote collection
        resp = self._remote[key]

        # KLUDGE: This works, for now, but there should be
        # another database mapping key -> content_type and
        # a method for reading the value + metadata on the
        # local storage instance
        self._local.put(key, resp, content_type=None)
        return resp

    def put(self, key: Union[str, bytes], value: Union[str, bytes], content_type: str):
        self._local.put(key, value, content_type)
        self._remote.put(key, value, content_type)
