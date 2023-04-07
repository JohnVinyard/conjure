from hashlib import sha1
import pickle
from typing import Callable
from conjure.identifier import FunctionContentIdentifier, FunctionIdentifier, ParamsHash, ParamsIdentifier
from conjure.serialize import Deserializer, JSONDeserializer, JSONSerializer, Serializer
from conjure.storage import Collection
import numpy as np
import lmdb
import struct


# class Wrapped(object):
#     def __init__(self, callable, func_hash):
#         super().__init__()
#         self.func_hash = func_hash
#         self.callable = callable

#     def __call__(self, *args, **kwargs):
#         return self.callable(*args, **kwargs)


class Conjure(object):

    def __init__(
            self,
            callable: Callable,
            content_type: str,
            storage: Collection,
            func_identifier: FunctionIdentifier,
            param_identifier: ParamsIdentifier,
            serializer: Serializer,
            deserializer: Deserializer,
            key_delimiter='_'):

        super().__init__()
        self.callable = callable
        self.key_delimiter = key_delimiter
        self.content_type = content_type
        self.storage = storage
        self.func_identifier = func_identifier
        self.param_identifier = param_identifier
        self.serializer = serializer
        self.deserializer = deserializer

    def serve(self, port='8888'):
        raise NotImplementedError()

    def exists(self, *args, **kwargs):
        key = self.key(*args, **kwargs)
        return key in self.storage

    @property
    def identifier(self):
        return self.func_identifier.derive_name(self.callable)

    def identify_params(self, *args, **kwargs):
        return self.param_identifier.derive_name(*args, **kwargs)

    def key(self, *args, **kwargs) -> bytes:
        return f'{self.identifier}{self.key_delimiter}{self.identify_params(*args, **kwargs)}'.encode()

    def __call__(self, *args, **kwargs):
        key = self.key(*args, **kwargs)
        try:
            raw = self.storage[key]
            obj = self.deserializer.from_bytes(raw)
            return obj
        except KeyError:
            obj = self.callable(*args, **kwargs)
            raw = self.serializer.to_bytes(obj)
            self.storage[key] = raw
            return obj

# def non_generator_func(f, h, collection, serialize, deserialize, arg_hasher):
#     def x(*args, **kwargs):
#         args_hash = arg_hasher(*args, **kwargs)
#         key = f'{h}:{args_hash}'.encode()
#         try:
#             cached = deserialize(*collection[key])
#             return cached
#         except KeyError:
#             pass

#         try:
#             result = f(*args, **kwargs)
#             collection[key] = serialize(result)
#         except NoCache as nc:
#             result = nc.value
#         return result

#     return x


# def dump_pickle(x):
#     s = pickle.dumps(x, pickle.HIGHEST_PROTOCOL)
#     return memoryview(s)


# def numpy_array_dumpb(arr):
#     arr = np.ascontiguousarray(arr, dtype=np.float32)
#     shape = pickle.dumps(arr.shape)
#     shape_bytes = struct.pack('i', len(shape))
#     return memoryview(shape_bytes + shape + arr.tobytes())


# def load_pickle(memview, txn):
#     return pickle.loads(memview)


# def numpy_array_loadb(memview, txn):
#     shape_len = struct.unpack('i', memview[:4])[0]
#     shape = pickle.loads(memview[4: 4 + shape_len])
#     raw = np.asarray(memview[4 + shape_len:], dtype=np.uint8)
#     arr = raw.view(dtype=np.float32).reshape(shape)
#     return NumpyWrapper(arr, txn)


# def cache(
#         collection,
#         serialize=numpy_array_dumpb,
#         deserialze=numpy_array_loadb,
#         arg_hasher=hash_args):

#     '''
#     TODO:
#         - Collection should support getitem, setitem and....
#         - encoder should implement dump, load and MIME/content type
#         - hasher should define how the function and its arguments are serialized into a key, ideally
#             in a human-readable way, e.g. stft_(1234, 512, 256)
#         - indices should be created for each argument whose type is supported, e.g., strings, numbers,
#             dates, so that it'd be possible to search for all stft invocations with window size 1024

#     '''

#     def deco(f):
#         h = hash_function(f)
#         return Wrapped(
#             non_generator_func(f, h, collection, serialize, deserialze, arg_hasher), h)

#     return deco


def conjure(
        content_type: str,
        storage: Collection,
        func_identifier: FunctionIdentifier,
        param_identifier: ParamsIdentifier,
        serializer: Serializer,
        deserializer: Deserializer,
        key_delimiter='_'):

    def deco(f: Callable):
        return Conjure(
            callable=f,
            content_type=content_type,
            storage=storage,
            func_identifier=func_identifier,
            param_identifier=param_identifier,
            serializer=serializer,
            deserializer=deserializer,
            key_delimiter=key_delimiter
        )

    return deco


def json_conjure(storage=Collection, tag_deserialized=False):

    return conjure(
        content_type='application/json',
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=JSONSerializer(),
        deserializer=JSONDeserializer(tag_deserialized=tag_deserialized)
    )
