import datetime
import json
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
from conjure.indexes import ConjureIndex, Indices
from conjure.index_store import IndexStore, SqliteIndexStore
from conjure.storage import SqliteCollection
import inspect
from urllib.parse import urlunparse


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
            'public_uri': urlunparse(self.public_uri) if self.public_uri else None,
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
        read_from_cache_hook=lambda x: None,
        indices: Iterable[ConjureIndex] = None,
        index_store: IndexStore = None
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
        
        # ensure that a read hook is always present
        self.read_from_cache_hook = read_from_cache_hook or (lambda x: None)

        self.listeners = []

        if '_' in ensure_str(self.identifier):
            raise ValueError('"_" is not currently supported in literal function identifiers.  TODO: Make this configurable globally')

        self.indices = Indices(indices or [])
        self.index_store = index_store
        if self.indices:
            if self.index_store is None:
                self.index_store = self._default_index_store(storage)
            for index in self.indices:
                index.attach(self.index_store, self.identifier)

    @staticmethod
    def _default_index_store(storage: Collection) -> IndexStore:
        if isinstance(storage, SqliteCollection):
            # keep indices in the same file as results
            return SqliteIndexStore(storage.path, timeout=storage.timeout)

        raise TypeError(
            f'Indices need an index store, and there is no default for '
            f'{type(storage).__name__}.  Pass e.g. '
            "index_store=SqliteIndexStore('indices.sqlite')")

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
        return self.func_identifier.derive_name(self.callable)

    @property
    def identifier(self):
        return self.func_identifier.derive_name(self.callable)

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
    

    def identify_params(self, *args, **kwargs):
        return self.param_identifier.derive_name(*args, **kwargs)

    def key(self, *args, **kwargs) -> bytes:
        return f'{self.identifier}{self.key_delimiter}{self.identify_params(*args, **kwargs)}'.encode()
    
    def delete(self, *args, **kwargs):
        key = self.key(*args, **kwargs)

        # remove index entries first:  if the second step fails, the result
        # is left unindexed, and will be indexed again on its next cache hit,
        # rather than leaving index entries that point to nothing
        if self.indices:
            self.index_store.delete(key, list(self.indices))
        del self.storage[key]

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
        # extract index values first, so that a failing extractor stores
        # nothing, and the problem surfaces immediately
        entries = [
            (index, index.values(obj, *args, **kwargs))
            for index in self.indices]

        self.storage.put(key, raw, self.content_type)

        # if this fails, the result is indexed on its next cache hit
        if entries:
            self.index_store.write(key, entries)

        # notify listeners
        for listener in self.listeners:
            listener(WriteNotification(key, obj, *args, **kwargs))

        return obj
    
    def result_and_meta(self, *args, **kwargs) -> Tuple[Any, MetaData]:
        result = self.__call__(*args, **kwargs)
        meta = self.meta(*args, **kwargs)
        return result, meta

    def __call__(self, *args, **kwargs):
        key = self.key(*args, **kwargs)

        if not self.prefer_cache:
            return self._compute_and_store(key, *args, **kwargs)

        try:
            raw = self.storage[key]
            obj = self.deserializer.from_bytes(raw)
            self.read_from_cache_hook(obj)
        except KeyError:
            return self._compute_and_store(key, *args, **kwargs)

        # kept outside of the try block above, so that a KeyError raised by
        # an extractor isn't mistaken for a cache miss
        self._index_if_missing(key, obj, *args, **kwargs)

        return obj

    def _index_if_missing(self, key, obj, *args, **kwargs):
        """
        Add index entries for a cached result that some index hasn't
        processed, e.g. because the result was cached before the index
        was defined.  Each index processes a given key only once.
        """
        if not self.indices:
            return

        missing = self.index_store.unprocessed(key, list(self.indices))
        if not missing:
            return

        entries = [
            (index, index.values(obj, *args, **kwargs)) for index in missing]
        self.index_store.write(key, entries)


def conjure(
        content_type: str,
        storage: Collection,
        func_identifier: FunctionIdentifier,
        param_identifier: ParamsIdentifier,
        serializer: Serializer,
        deserializer: Deserializer,
        key_delimiter='_',
        prefer_cache=True,
        read_from_cache_hook=lambda x: None,
        indices: Iterable[ConjureIndex] = None,
        index_store: IndexStore = None):

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
            read_from_cache_hook=read_from_cache_hook,
            indices=indices,
            index_store=index_store
        )
    return deco


def bytes_conjure(
        storage: Collection,
        content_type: Union[SupportedContentType, str],
        read_hook=None,
        indices: Iterable[ConjureIndex] = None,
        index_store: IndexStore = None):
    
    try:
        content_type = content_type.value
    except AttributeError:
        pass
    
    return conjure(
        content_type=content_type,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=IdentitySerializer(),
        deserializer=IdentityDeserializer(),
        read_from_cache_hook=read_hook,
        indices=indices,
        index_store=index_store
    )

def text_conjure(storage: Collection, indices: Iterable[ConjureIndex] = None,
        index_store: IndexStore = None):
    return conjure(
        content_type=SupportedContentType.Text.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=IdentitySerializer(),
        deserializer=IdentityDeserializer(),
        indices=indices,
        index_store=index_store
    )


def pickle_conjure(storage: Collection, read_hook = None, indices: Iterable[ConjureIndex] = None,
        index_store: IndexStore = None):
    return conjure(
        content_type='application/octet-stream',
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=PickleSerializer(),
        deserializer=PickleDeserializer(),
        read_from_cache_hook=read_hook,
        indices=indices,
        index_store=index_store)

def json_conjure(storage: Collection, tag_deserialized=False, indices: Iterable[ConjureIndex] = None,
        index_store: IndexStore = None):
    return conjure(
        content_type='application/json',
        storage=storage,
        func_identifier=FunctionContentIdentifier(),
        param_identifier=ParamsHash(),
        serializer=JSONSerializer(),
        deserializer=JSONDeserializer(tag_deserialized=tag_deserialized),
        indices=indices,
        index_store=index_store
    )


def numpy_conjure(
        storage: Collection, 
        content_type=SupportedContentType.Tensor.value,
        read_hook=lambda x: None,
        identifier: bytes = None,
        param_key: bytes = None,
        indices: Iterable[ConjureIndex] = None,
        index_store: IndexStore = None):

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
        read_from_cache_hook=read_hook,
        indices=indices,
        index_store=index_store
    )


def audio_conjure(
        storage: Collection, 
        identifier: bytes = None, 
        param_key: bytes = None,
        indices: Iterable[ConjureIndex] = None,
        index_store: IndexStore = None):

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
        indices=indices,
        index_store=index_store
    )


def time_series_conjure(storage: Collection, name: bytes, indices: Iterable[ConjureIndex] = None,
        index_store: IndexStore = None):
    return conjure(
        content_type=SupportedContentType.TimeSeries.value,
        storage=storage,
        func_identifier=FunctionContentIdentifier(include_closures=False),
        param_identifier=LiteralParamsIdentifier(name),
        serializer=NumpySerializer(),
        deserializer=NumpyDeserializer(),
        prefer_cache=False,
        indices=indices,
        index_store=index_store
    )
