from os import PathLike
from typing import Callable, Iterable, Union
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

    def destroy(self):
        # first, delete all keys
        for key in self.iter_prefix(''):
            print(f'deleting key {key}')
            self.client.delete_object(Bucket=self.bucket, Key=key)

        print(f'deleting bucket {self.bucket}')
        self.client.delete_bucket(Bucket=self.bucket)

    def __delitem__(self, key):
        raise NotImplementedError()

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
        contents = resp['Contents']

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
            map_size=10e10,
            writemap=True,
            map_async=True,
            metasync=True,
            lock=False)
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


class LocalCollectionWithBackup(Collection):
    def __init__(
            self,
            local_path,
            remote_bucket,
            is_public=False,
            local_backup=False,
            cors_enabled=False):

        super().__init__()
        self.local_backup = local_backup

        self._local = LmdbCollection(local_path)

        if isinstance(self.local_backup, Collection):
            self._remote = local_backup
        elif self.local_backup:
            self._remote = LmdbCollection(f'{local_path}_backup')
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
