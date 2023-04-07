from typing import Callable
from conjure.identifier import FunctionContentIdentifier, FunctionIdentifier, ParamsHash, ParamsIdentifier
from conjure.serialize import Deserializer, JSONDeserializer, JSONSerializer, Serializer
from conjure.storage import Collection


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
