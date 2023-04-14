from typing import Callable, Iterable, Union
from urllib.parse import ParseResult, urlparse
import lmdb
import boto3
from shutil import rmtree

from conjure.timestamp import timestamp_id


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


# TODO: Create the bucket if it doesn't already exist and enable CORS
class S3Collection(Collection):

    def __init__(self, bucket, is_public=False):
        super().__init__()
        self.bucket = bucket
        self.client = boto3.client('s3')
        self.is_public = is_public
        self._create_bucket()

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
            resp = self.client.get_object_attribute(
                Bucket=self.bucket, Key=self.key)
            return resp['ObjectSize']
        except self.client.NoSuchKey:
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
        # TODO: CORS settings for bucket
        try:
            self.client.create_bucket(
                ACL=self.acl,
                Bucket=self.bucket)
        except self.client.exceptions.BucketAlreadyExists:
            pass

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
    def __init__(self, path, extract_base_key: Callable[[bytes], bytes] = None):
        super().__init__()

        # KLUDGE: Delimiter is configurable elsewhere, so this might cause problems
        self.extract_base_key = extract_base_key or (
            lambda x: ensure_bytes(ensure_str(x).split('_')[0]))
        self.path = path
        self.env = lmdb.open(
            self.path,
            max_dbs=10,
            map_size=10e10,
            writemap=True,
            map_async=True,
            metasync=True,
            lock=False)
        self._data = self.env.open_db(b'data')
        self._feed = self.env.open_db(b'feed')

    def destroy(self):
        self.env.close()
        rmtree(self.path)

    def feed(self, offset: Union[bytes, str] = None):
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
            timestamp = timestamp_id()
            base_key = self.extract_base_key(key)
            feed_key = ensure_bytes(
                f'{base_key.decode()}_{timestamp.decode()}')
            txn.put(feed_key, key, db=self._feed)


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
            local_backup=False):

        super().__init__()
        self.local_backup = local_backup

        self._local = LmdbCollection(local_path)

        if isinstance(self.local_backup, Collection):
            self._remote = local_backup
        elif self.local_backup:
            self._remote = LmdbCollection(f'{local_path}_backup')
        else:
            self._remote = S3Collection(
                remote_bucket, is_public=is_public)

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

