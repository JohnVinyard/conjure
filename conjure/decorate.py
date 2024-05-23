import datetime
import json
from types import FunctionType
from typing import Any, Callable, Iterable, Tuple, Union
from urllib.parse import ParseResult

from markdown import markdown
from conjure.contenttype import SupportedContentType
from conjure.identifier import \
    FunctionContentIdentifier, FunctionIdentifier, LiteralFunctionIdentifier, LiteralParamsIdentifier, \
    ParamsHash, ParamsIdentifier
from conjure.serialize import \
    Deserializer, IdentityDeserializer, IdentitySerializer, JSONDeserializer, \
    JSONSerializer, NumpyDeserializer, NumpySerializer, Serializer, \
    PickleSerializer, PickleDeserializer
from conjure.storage import Collection, LocalCollectionWithBackup, ensure_bytes, ensure_str
import inspect
from urllib.parse import urlunparse
from collections import Counter


class MetaData(object):
    def __init__(
            self,
            key,
            public_uri: ParseResult,
            content_type,
            content_length,
            identifier,
            func_name: str,
            func_identifier: str):

        super().__init__()
        self.key = key
        self.public_uri = public_uri
        self.content_type = content_type
        self.content_length = content_length
        self.identifier = identifier
        self.func_name = func_name
        self.func_identifier = func_identifier

    def with_public_uri(self, public_uri: ParseResult):
        return MetaData(
            key=self.key,
            public_uri=public_uri,
            content_type=self.content_type,
            content_length=self.content_length,
            identifier=self.identifier,
            func_name=self.func_name,
            func_identifier=self.func_identifier
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

    @property
    def conjure_data(self):
        return {
            'key': ensure_str(self.key),
            'public_uri': urlunparse(self.public_uri),
            'content_type': self.content_type,
            'feed_uri': f'/feed/{ensure_str(self.identifier)}',
            'func_name': self.func_name,
            'func_identifier': self.func_identifier
        }

    def conjure_html(self):
        return f'<div id="conjure-id-{ensure_str(self.key)}" data-conjure=\'{json.dumps(self.conjure_data)}\'></div>'


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
    def __init__(self, key: bytes, value: Any, *args, **kwargs):
        self.key = key
        self.value = value
        self.timestamp = datetime.datetime.utcnow()
        self.args = args
        self.kwargs = kwargs


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
        read_from_cache_hook=lambda x: None
    ):

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
        self.read_from_cache_hook = read_from_cache_hook

        self.listeners = []

        if '_' in ensure_str(self.identifier):
            raise ValueError('"_" is not currently supported in literal function identifiers.  TODO: Make this configurable globally')

    @property
    def offset(self):
        return self.storage.offset

    def feed(self, offset: Union[bytes, str] = None):
        final_offset = offset or self.identifier

        search = ensure_bytes(self.identifier) if isinstance(
            final_offset, bytes) else ensure_str(self.identifier)
        if not final_offset.startswith(search):
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

    @property
    def description_html(self):
        formatted = '\n'.join(
            map(lambda x: x.strip(), (self.description or '').split('\n')))
        return markdown(formatted)

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
            identifier=self.identifier,
            func_name=self.name,
            func_identifier=self.identifier)

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

    def get(self, key):
        raw = self.storage[key]
        obj = self.deserializer.from_bytes(raw)
        return obj

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
                identifier=self.identifier,
                func_name=self.name,
                func_identifier=self.func_identifier
            )
        )

    def _compute_and_store(self, key, *args, **kwargs):
        obj = self.callable(*args, **kwargs)
        raw = self.serializer.to_bytes(obj)

        # TODO: Feed keys should be computed here, so they
        # can be passed along with the write notification
        self.storage.put(key, raw, self.content_type)

        # notify listeners
        for listener in self.listeners:
            listener(WriteNotification(key, obj, *args, **kwargs))

        return obj

    def __call__(self, *args, **kwargs):
        key = self.key(*args, **kwargs)

        if not self.prefer_cache:
            return self._compute_and_store(key, *args, **kwargs)

        try:
            raw = self.storage[key]
            obj = self.deserializer.from_bytes(raw)

            self.read_from_cache_hook(obj)
            
            return obj
        except KeyError:
            return self._compute_and_store(key, *args, **kwargs)


class Index(object):
    def __init__(
            self,
            name: str,
            collection: Collection,
            conjure: Conjure,
            func: FunctionType,
            serializer: Serializer = JSONSerializer(),
            deserializer: Deserializer = JSONDeserializer(),
            register_listener=True):

        super().__init__()
        self.func = func
        self.name = name
        self.serializer = serializer
        self.deserializer = deserializer
        self.conjure = conjure
        self.collection = collection

        if register_listener:
            self.conjure.register_listener(
                lambda x: self.extract_and_store(x.key, x.value, *x.args, **x.kwargs))

        self.keys_processed_in_current_session = 0

    @property
    def description(self):
        return self.func.__doc__

    @property
    def description_html(self):
        formatted = '\n'.join(
            map(lambda x: x.strip(), (self.description or '').split('\n')))
        return markdown(formatted)

    @property
    def conjure_identifier(self):
        return self.conjure.identifier

    @property
    def offset(self):
        if self.collection.offset is None:
            return None
        return ensure_bytes(self.collection.offset)

    def index(self):

        for item in self.conjure.feed(offset=self.offset):
            if self.offset == item['timestamp']:
                continue

            key = item['key']
            obj = self.conjure.get(key)
            # TODO: What if I need to partially/fuly reconstruct the
            # original arguments?
            self.extract_and_store(key, obj, feed_offset=item['timestamp'])

    def extract_key(self, data):
        return data['key']

    @property
    def content_type(self):
        return 'application/json'

    def extract_and_store(self, key, result, feed_offset=None, *args, **kwargs):
        document_key = key

        for i, pair in enumerate(self.extract(key, result, *args, **kwargs)):
            try:
                key, value = pair

                k = ensure_str(key)

                # NOTE: The assumption here is that index keys are extracted
                # from the document in an ordered, deterministic way
                full_key = f'{k}_{ensure_str(document_key)}_{hex(i)}'

                self.collection.put(
                    ensure_bytes(full_key), self.serializer.to_bytes(value), self.content_type)
            except Exception as e:
                print(f'Error processing document {document_key}, {key}')
                pass

        if feed_offset:
            self.collection.set_offset(ensure_bytes(feed_offset))
            self.keys_processed_in_current_session += 1

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


def conjure_index(conjure: Conjure, collection: Collection = None, name: str = None):

    def deco(f: Callable):

        n = name or f.__name__

        return Index(
            name=n,
            conjure=conjure,
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
        read_from_cache_hook=lambda x: None):

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
            read_from_cache_hook=read_from_cache_hook
        )
    return deco


def bytes_conjure(storage: Collection, content_type: SupportedContentType, read_hook=None):
    return conjure(
        content_type=content_type.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=IdentitySerializer(),
        deserializer=IdentityDeserializer(),
        read_from_cache_hook=read_hook
    )

def text_conjure(storage: Collection):
    return conjure(
        content_type=SupportedContentType.Text.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=IdentitySerializer(),
        deserializer=IdentityDeserializer(),
    )


def pickle_conjure(storage: Collection, read_hook = None):
    return conjure(
        content_type='application/octet-stream',
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=PickleSerializer(),
        deserializer=PickleDeserializer(),
        read_from_cache_hook=read_hook)

def json_conjure(storage: Collection, tag_deserialized=False):
    return conjure(
        content_type='application/json',
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=JSONSerializer(),
        deserializer=JSONDeserializer(tag_deserialized=tag_deserialized),
    )


def numpy_conjure(
        storage: Collection, 
        content_type=SupportedContentType.Tensor.value,
        read_hook=lambda x: None,
        identifier: bytes = None,
        param_key: bytes = None):

    return conjure(
        content_type=content_type,
        storage=storage,
        func_identifier=FunctionContentIdentifier() 
            if identifier is None 
            else LiteralFunctionIdentifier(identifier),
        param_identifier=ParamsHash() 
            if param_key is None 
            else LiteralParamsIdentifier(param_key),
        serializer=NumpySerializer(),
        deserializer=NumpyDeserializer(),
        read_from_cache_hook=read_hook
    )


def audio_conjure(
        storage: Collection, 
        identifier: bytes = None, 
        param_key: bytes = None):

    return conjure(
        content_type=SupportedContentType.Audio.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier() 
            if identifier is None 
            else LiteralFunctionIdentifier(identifier),
        param_identifier=ParamsHash()
            if param_key is None
            else LiteralParamsIdentifier(param_key),
        serializer=IdentitySerializer(),
        deserializer=IdentityDeserializer(),
    )


def time_series_conjure(storage: Collection, name: bytes):
    return conjure(
        content_type=SupportedContentType.TimeSeries.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(include_closures=False),
        param_identifier=LiteralParamsIdentifier(name),
        serializer=NumpySerializer(),
        deserializer=NumpyDeserializer(),
        prefer_cache=False,
    )
