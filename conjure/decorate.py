import datetime
import json
from typing import Callable, Union
from urllib.parse import ParseResult
from conjure.contenttype import SupportedContentType
from conjure.identifier import \
    FunctionContentIdentifier, FunctionIdentifier, LiteralFunctionIdentifier, \
    LiteralParamsIdentifier, ParamsHash, ParamsIdentifier
from conjure.serialize import \
    Deserializer, IdentityDeserializer, IdentitySerializer, JSONDeserializer, \
    JSONSerializer, NumpyDeserializer, NumpySerializer, Serializer
from conjure.storage import Collection, LocalCollectionWithBackup, ensure_str
import inspect
from urllib.parse import urlunparse


class MetaData(object):
    def __init__(self, key, public_uri: ParseResult, content_type, content_length, identifier):
        super().__init__()
        self.key = key
        self.public_uri = public_uri
        self.content_type = content_type
        self.content_length = content_length
        self.identifier = identifier

    def with_public_uri(self, public_uri: ParseResult):
        return MetaData(
            key=self.key,
            public_uri=public_uri,
            content_type=self.content_type,
            content_length=self.content_length,
            identifier=self.identifier
        )

    def __str__(self):
        return f'MetaData(key={self.key}, public_uri={self.public_uri}, content_type={self.content_type}, content_length={self.content_length})'

    def __repr__(self):
        return self.__str__()

    def conjure_collection(self, local_path, remote_bucket, public=False):
        return LocalCollectionWithBackup(
            local_path=local_path,
            remote_bucket=remote_bucket,
            content_type=self.content_type,
            is_public=public)

    def conjure_html(self):
        conjure_data = {
            'key': ensure_str(self.key),
            'public_uri': urlunparse(self.public_uri),
            'content_type': self.content_type,
            'feed_uri': f'/feed/{ensure_str(self.identifier)}'
        }
        return f'<div id="conjure-id-{ensure_str(self.key)}" data-conjure=\'{json.dumps(conjure_data)}\'></div>'


class ResultWithMetadata(object):
    def __init__(self, raw: bytes, meta: MetaData):
        self.raw = raw
        self.meta = meta

    @property
    def public_uri(self):
        return self.meta.public_uri

    @property
    def content_type(self):
        return self.meta.content_type

    @property
    def content_length(self):
        return self.meta.content_length


class WriteNotification(object):
    def __init__(self, key: bytes):
        self.key = key
        self.timestamp = datetime.datetime.utcnow()


WriteListener = Callable[[WriteNotification], None]


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
            key_delimiter='_',
            prefer_cache=True):

        super().__init__()
        self.callable = callable
        self.key_delimiter = key_delimiter
        self.content_type = content_type
        self.storage = storage
        self.func_identifier = func_identifier
        self.param_identifier = param_identifier
        self.serializer = serializer
        self.deserializer = deserializer
        self.prefer_cache = prefer_cache

        self.listeners = []

    def feed(self, offset: Union[bytes, str] = None):
        final_offset = offset or self.identifier
        if not final_offset.startswith(self.identifier):
            raise ValueError(
                f'offset must start with {self.identifier} but was {offset}')
        return self.storage.feed(offset=final_offset)

    def most_recent_key(self) -> str:
        all_keys = list(self.feed())
        return all_keys[-1]['key']

    def most_recent_meta(self) -> MetaData:
        key = self.most_recent_key()
        return self.meta_from_key(key)

    @property
    def code(self):
        return inspect.getsource(self.callable)

    @property
    def name(self):
        return self.callable.__name__

    @property
    def description(self):
        return self.callable.__doc__

    def iter_keys(self):
        offset = f'{self.identifier}'.encode()
        for key in self.storage.iter_prefix(offset, prefix=offset):
            yield key

    def register_listener(self, listener: WriteListener) -> None:
        self.listeners.append(listener)

    def remove_listener(self, listener: WriteListener) -> None:
        self.listeners.remove(listener)

    def exists(self, *args, **kwargs):
        key = self.key(*args, **kwargs)
        return key in self.storage

    def meta_from_key(self, key) -> MetaData:
        # KLUDGE: Implement "head" requests to get object
        # size without reading into memory/pulling from s3
        uri = None
        try:
            uri = self.storage.public_uri(key)
        except NotImplementedError:
            pass

        return MetaData(
            key=key,
            public_uri=uri,
            content_type=self.content_type,
            content_length=self.storage.content_length(key),
            identifier=self.identifier)

    def meta(self, *args, **kwargs) -> MetaData:
        key = self.key(*args, **kwargs)
        return self.meta_from_key(key)

    @property
    def identifier(self):
        return self.func_identifier.derive_name(self.callable)

    def identify_params(self, *args, **kwargs):
        return self.param_identifier.derive_name(*args, **kwargs)

    def key(self, *args, **kwargs) -> bytes:
        return f'{self.identifier}{self.key_delimiter}{self.identify_params(*args, **kwargs)}'.encode()

    def get_raw(self, key):
        raw = self.storage[key]

        public_uri = None
        try:
            public_uri = self.storage.public_uri(key)
        except NotImplementedError:
            pass

        return ResultWithMetadata(
            raw,
            MetaData(
                key=key,
                public_uri=public_uri,
                content_type=self.content_type,
                content_length=self.storage.content_length(key),
                identifier=self.identifier
            )
        )

    def _compute_and_store(self, key, *args, **kwargs):
        obj = self.callable(*args, **kwargs)
        raw = self.serializer.to_bytes(obj)
        self.storage.put(key, raw, self.content_type)
        for listener in self.listeners:
            listener(WriteNotification(key))
        return obj

    def __call__(self, *args, **kwargs):
        key = self.key(*args, **kwargs)

        if not self.prefer_cache:
            return self._compute_and_store(key, *args, **kwargs)

        try:
            raw = self.storage[key]
            obj = self.deserializer.from_bytes(raw)
            return obj
        except KeyError:
            return self._compute_and_store(key, *args, **kwargs)


def conjure(
        content_type: str,
        storage: Collection,
        func_identifier: FunctionIdentifier,
        param_identifier: ParamsIdentifier,
        serializer: Serializer,
        deserializer: Deserializer,
        key_delimiter='_',
        prefer_cache=True):

    def deco(f: Callable):
        return Conjure(
            callable=f,
            content_type=content_type,
            storage=storage,
            func_identifier=func_identifier,
            param_identifier=param_identifier,
            serializer=serializer,
            deserializer=deserializer,
            key_delimiter=key_delimiter,
            prefer_cache=prefer_cache
        )

    return deco


def json_conjure(storage: Collection, tag_deserialized=False):

    return conjure(
        content_type='application/json',
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=JSONSerializer(),
        deserializer=JSONDeserializer(tag_deserialized=tag_deserialized)
    )


def numpy_conjure(storage: Collection, content_type=SupportedContentType.Tensor.value):

    return conjure(
        content_type=content_type,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=NumpySerializer(),
        deserializer=NumpyDeserializer()
    )


def audio_conjure(storage: Collection):

    return conjure(
        content_type=SupportedContentType.Audio.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=IdentitySerializer(),
        deserializer=IdentityDeserializer()
    )


def time_series_conjure(storage: Collection, name: bytes):

    return conjure(
        content_type=SupportedContentType.TimeSeries.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=LiteralParamsIdentifier(name),
        serializer=NumpySerializer(),
        deserializer=NumpyDeserializer(),
        prefer_cache=False
    )
