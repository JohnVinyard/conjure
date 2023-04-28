import datetime
import json
from types import FunctionType
from typing import Any, Callable, Iterable, List, Set, Tuple, Union
from urllib.parse import ParseResult
from conjure.contenttype import SupportedContentType
from conjure.identifier import \
    FunctionContentIdentifier, FunctionIdentifier, LiteralParamsIdentifier, \
    ParamsHash, ParamsIdentifier
from conjure.serialize import \
    Deserializer, IdentityDeserializer, IdentitySerializer, JSONDeserializer, \
    JSONSerializer, NumpyDeserializer, NumpySerializer, Serializer
from conjure.storage import Collection, LocalCollectionWithBackup, ensure_bytes, ensure_str
import inspect
from urllib.parse import urlunparse
from collections import Counter
from uuid import uuid4

class Index(object):
    def __init__(
            self,
            name: str,
            collection: Collection,
            func: FunctionType,
            serializer: Serializer = JSONSerializer(),
            deserializer: Deserializer = JSONDeserializer()):

        super().__init__()
        self.func = func
        self.name = name
        self.serializer = serializer
        self.deserializer = deserializer
        self.collection = collection

    def extract_key(self, data):
        return data['key']

    @property
    def content_type(self):
        return 'application/json'

    def extract_and_store(self, key, result, *args, **kwargs):
        document_key = key

        for i, pair in enumerate(self.extract(key, result, *args, **kwargs)):
            key, value = pair

            k = ensure_str(key)
            # TODO: If this were deterministic, then it would be safe to fully
            # re-index and I wouldn't need to worry about storing a feed offset
            # for each index (yet). If it doesn't have the additional segment at
            # the end, then duplicate keys are overwritten (i.e., can't store the
            # same word pointing to different documents)
            #
            # Maybe this should just be sequential?
            # params = uuid4().hex

            # NOTE: The assumption here is that index keys are extracted 
            # from the document in an ordered, deterministic way
            full_key = f'{k}_{ensure_str(document_key)}_{hex(i)}'

            # TODO: Here I need to make sure that the feed key is written to the 
            # offset value for this database
            self.collection.put(
                ensure_bytes(full_key), self.serializer.to_bytes(value), self.content_type)

    def extract(self, key, result, *args, **kwargs) -> Iterable[Tuple[Union[str, bytes], Any]]:
        results = self.func(key, result, *args, **kwargs)
        for key, value in results:
            if not self.extract_key(value):
                raise ValueError('Could not extract key')
            yield key, value

    def search(self, query: Union[str, bytes]):
        values = []

        for key in self.collection.iter_prefix(query, query):
            raw_value = self.collection[key]
            value = self.deserializer.from_bytes(raw_value)
            values.append(value)

        return self.compact(values)

    def compact(self, results):
        """
        Since the key may appear multiple times, rank by "relevance"
        """

        indexed = {r['key']: r for r in results}

        counter = Counter()
        for result in results:
            key = result['key']
            counter[key] += 1

        srt = sorted(counter.items(), key=lambda x: x[1], reverse=True)
        return [indexed[k[0]] for k in srt]


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
            prefer_cache=True,
            indexes: List[Index] = None):

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
        self.indexes = {index.name: index for index in (indexes or [])}

        self.listeners = []

    def feed(self, offset: Union[bytes, str] = None):
        final_offset = offset or self.identifier
        if not final_offset.startswith(self.identifier):
            raise ValueError(
                f'offset must start with {self.identifier} but was {offset}')
        return self.storage.feed(offset=final_offset)

    def search(self, index_name: str, query: Union[str, bytes]):
        index = self.indexes[index_name]
        return index.search(query)

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

        # index the results
        for _, index in self.indexes.items():
            index.extract_and_store(key, obj, *args, **kwargs)

        # notify listeners
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


def conjure_index(collection: Collection, name: str = None):

    def deco(f: Callable):

        n = name or f.__name__

        return Index(
            name=n,
            collection=collection,
            func=f,
            serializer=JSONSerializer(),
            deserializer=JSONDeserializer())

    return deco


def conjure(
        content_type: str,
        storage: Collection,
        func_identifier: FunctionIdentifier,
        param_identifier: ParamsIdentifier,
        serializer: Serializer,
        deserializer: Deserializer,
        key_delimiter='_',
        prefer_cache=True,
        indexes=None):

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
            prefer_cache=prefer_cache,
            indexes=indexes
        )

    return deco


def text_conjure(storage: Collection, indexes=None):

    return conjure(
        content_type=SupportedContentType.Text.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=IdentitySerializer(),
        deserializer=IdentityDeserializer(),
        indexes=indexes
    )


def json_conjure(storage: Collection, tag_deserialized=False, indexes=None):

    return conjure(
        content_type='application/json',
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=JSONSerializer(),
        deserializer=JSONDeserializer(tag_deserialized=tag_deserialized),
        indexes=indexes
    )


def numpy_conjure(storage: Collection, content_type=SupportedContentType.Tensor.value, indexes=None):

    return conjure(
        content_type=content_type,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=NumpySerializer(),
        deserializer=NumpyDeserializer(),
        indexes=indexes
    )


def audio_conjure(storage: Collection, indexes=None):

    return conjure(
        content_type=SupportedContentType.Audio.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=IdentitySerializer(),
        deserializer=IdentityDeserializer(),
        indexes=indexes
    )


def time_series_conjure(storage: Collection, name: bytes, indexes=None):

    return conjure(
        content_type=SupportedContentType.TimeSeries.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=LiteralParamsIdentifier(name),
        serializer=NumpySerializer(),
        deserializer=NumpyDeserializer(),
        prefer_cache=False,
        indexes=indexes
    )
