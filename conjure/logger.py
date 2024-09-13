from typing import Union, Callable, List
from conjure import LiteralFunctionIdentifier, ParamsHash, Conjure
from conjure.storage import Collection, ensure_bytes
from conjure.serialize import \
    Serializer, Deserializer, IdentityDeserializer, IdentitySerializer


def logger(
        name: str,
        content_type: str,
        func: Callable,
        collection: Collection,
        serializer: Union[Serializer, None] = IdentitySerializer(),
        deserializer: Union[Deserializer, None] = IdentityDeserializer()) -> Conjure:
    """
    A convenience function for cases where we aren't concerned with caching the
    results of computations when repeated calls are likely, but instead for
    cases where we primarily care about the storage side effect.
    """
    return Conjure(
        callable=func,
        content_type=content_type,
        storage=collection,
        func_identifier=LiteralFunctionIdentifier(name),
        param_identifier=ParamsHash(),
        serializer=serializer,
        deserializer=deserializer)


def loggers(
        names: List[str],
        content_type: str,
        func: Callable,
        collection: Collection,
        serializer: Union[Serializer, None] = IdentitySerializer(),
        deserializer: Union[Deserializer, None] = IdentityDeserializer()) -> List[Conjure]:
    return [
        logger(name, content_type, func, collection, serializer, deserializer)
        for name in names
    ]