import datetime
from typing import Callable
from conjure.identifier import FunctionContentIdentifier, FunctionIdentifier, ParamsHash, ParamsIdentifier
from conjure.serialize import Deserializer, JSONDeserializer, JSONSerializer, Serializer
from conjure.storage import Collection


class MetaData(object):
    def __init__(self, key, public_uri, content_type, content_length):
        super().__init__()
        self.key = key
        self.public_uri = public_uri
        self.content_type =content_type
        self.content_length = content_length


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

        self.listeners = []

    
    def iter_keys(self):
        for key in self.storage.iter_prefix(f'{self.identifier}'.encode()):
            yield key
    
    def register_listener(self, listener: WriteListener) -> None:
        self.listeners.append(listener)
    
    def remove_listener(self, listener: WriteListener) -> None:
        self.listeners.remove(listener)

    def exists(self, *args, **kwargs):
        key = self.key(*args, **kwargs)
        return key in self.storage
    
    def meta(self, *args, **kwargs):
        key = self.key(*args, **kwargs)

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
            content_length=self.storage.content_length(key))

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
            for listener in self.listeners:
                listener(WriteNotification(key))
            return obj


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
