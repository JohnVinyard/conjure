from typing import Iterable, Union
import lmdb
import boto3
from shutil import rmtree


def ensure_bytes(value: Union[str, bytes, memoryview]) -> bytes:
    if isinstance(value, memoryview):
        return bytes(value)

    return value if isinstance(value, bytes) else value.encode()


def ensure_str(value: Union[str, bytes]) -> str:
    return value if isinstance(value, str) else value.decode()

class Collection(object):
    def __init__(self):
        super().__init__()
    
    def __contains__(self, key):
        raise NotImplementedError()
    
    def iter_prefix(self, start_key, prefix=None) -> Iterable[bytes]:
        raise NotImplementedError()

    def __setitem__(self, key: bytes, value: bytes):
        raise NotImplementedError()
    
    def __getitem__(self, key) -> bytes:
        raise NotImplementedError()
    
    def __delitem__(self, key):
        raise NotImplementedError()


# TODO: Create the bucket if it doesn't already exist and enable CORS
class S3Collection(Collection):

    def __init__(self, bucket, content_type, is_public=False):
        super().__init__()
        self.bucket = bucket
        self.client = boto3.client('s3')
        self.content_type = content_type
        self.is_public = is_public
        self._create_bucket()
    
    @property
    def acl(self):
        return 'public-read' if self.is_public else 'private'
    
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

    
    
    def iter_prefix(self, start_key: Union[str, bytes], prefix: Union[None, bytes, str]=None) -> Iterable[bytes]:

        

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
    
    def __setitem__(self, key: Union[bytes, str], value: bytes):
        self.client.put_object(
            Bucket=self.bucket, 
            Key=ensure_str(key), 
            Body=value, 
            ContentType=self.content_type,
            ACL=self.acl)

    def __getitem__(self, key: Union[str, bytes]) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=ensure_str(key))
            return resp['Body'].read()
        except:
            raise KeyError(key)


class LmdbCollection(Collection):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.env = lmdb.open(
            self.path,
            max_dbs=10,
            map_size=10e10,
            writemap=True,
            map_async=True,
            metasync=True)
    
    def destroy(self):
        self.env.close()
        rmtree(self.path)
    
    def __contains__(self, key: Union[str, bytes]):
        try:
            self[ensure_bytes(key)]
            return True
        except KeyError:
            return False

    def iter_prefix(self, start_key: Union[str, bytes], prefix: Union[str, bytes, None]=None):


        with self.env.begin(write=True, buffers=True) as txn:
            cursor = txn.cursor()
            cursor.set_range(ensure_bytes(start_key))

            it = cursor.iternext(keys=True, values=False)
            for key in it:
                key = ensure_bytes(key)
                if prefix is not None and not key.startswith(prefix):
                    break
                yield key
    
    def __delitem__(self, key: Union[str, bytes]):
        with self.env.begin(write=True) as txn:
            txn.delete(ensure_bytes(key))

    def __setitem__(self, key: Union[str, bytes], value: Union[str, bytes]):

        with self.env.begin(write=True, buffers=True) as txn:
            txn.put(ensure_bytes(key), ensure_bytes(value))

    def __getitem__(self, key):
        with self.env.begin(buffers=True, write=False) as txn:
            value = txn.get(ensure_bytes(key))
            if value is None:
                raise KeyError(key)
            return value




class LocalCollectionWithBackup(Collection):
    def __init__(
            self, 
            local_path, 
            remote_bucket, 
            content_type, 
            is_public=False, 
            local_backup=False):
        
        super().__init__()
        self.content_type = content_type
        self.local_backup = local_backup

        self._local = LmdbCollection(local_path)

        if isinstance(self.local_backup, Collection):
            self._remote = local_backup
        elif self.local_backup:
            self._remote = LmdbCollection(f'{local_path}_backup')
        else:
            self._remote = S3Collection(
                remote_bucket, content_type, is_public=is_public)
    
    def destroy(self):
        self._local.destroy()
        if self.local_backup:
            self._remote.destroy()
    
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
        self._local[key] = resp
        return resp
    
    def __setitem__(self, key: bytes, value: bytes):
        # first set the key locally
        self._local[key] = value
        # then set it remotely
        self._remote[key] = value