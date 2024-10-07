from typing import Union, Callable, List, Tuple, Any, Dict

from conjure import LiteralFunctionIdentifier, ParamsHash, Conjure, MetaData, movie, tensor_movie
from conjure.storage import Collection, ensure_bytes
from conjure.serialize import \
    Serializer, Deserializer, IdentityDeserializer, IdentitySerializer
import torch
import numpy as np
from matplotlib import pyplot as plt
from io import BytesIO
from soundfile import SoundFile


def display_matrix(
        arr: Union[torch.Tensor, np.ndarray],
        cmap: str = 'gray',
        invert: bool = False) -> bytes:
    if arr.ndim > 2:
        raise ValueError('Only two-dimensional arrays are supported')

    if isinstance(arr, torch.Tensor):
        arr = arr.data.cpu().numpy()

    if invert:
        arr = arr * -1

    bio = BytesIO()
    plt.matshow(arr, cmap=cmap)
    plt.axis('off')
    plt.margins(0, 0)
    plt.savefig(bio, pad_inches=0, bbox_inches='tight')
    plt.clf()
    bio.seek(0)
    return bio.read()


def create_matrix_displayer_with_cmap(cmap: str) -> Callable:
    def display_matrix_with_cmap(arr):
        return display_matrix(arr, cmap=cmap)
    return display_matrix_with_cmap


def encode_audio(
        x: Union[torch.Tensor, np.ndarray],
        samplerate: int = 22050,
        format='WAV',
        subtype='PCM_16'):
    if isinstance(x, torch.Tensor):
        x = x.data.cpu().numpy()

    if x.ndim > 1:
        x = x[0]

    x = x.reshape((-1,))
    io = BytesIO()

    with SoundFile(
            file=io,
            mode='w',
            samplerate=samplerate,
            channels=1,
            format=format,
            subtype=subtype) as sf:
        sf.write(x)

    io.seek(0)
    return io.read()


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


class Logger(object):
    def __init__(self, collection: Collection):
        self.collection = collection
        self.loggers: Dict[str, Conjure] = dict()

    def _get_or_create_logger(
            self, key: str,
            content_type: str,
            func: Callable) -> Conjure:
        try:
            l = self.loggers[key]
        except KeyError:
            l = logger(key, content_type, func, self.collection)
            self.loggers[key] = l
        return l

    def log_matrix_with_cmap(
            self,
            key: str,
            matrix: Union[np.ndarray, torch.Tensor],
            cmap: str):
        l = self._get_or_create_logger(
            key,
            'image/png',
            create_matrix_displayer_with_cmap(cmap))
        rm = l.result_and_meta(matrix)
        return rm

    def log_matrix(
            self,
            key: str,
            matrix: Union[np.ndarray, torch.Tensor]) -> Tuple[Any, MetaData]:
        l = self._get_or_create_logger(key, 'image/png', display_matrix)
        rm = l.result_and_meta(matrix)
        return rm

    def log_sound(
            self, key: str,
            audio: Union[np.ndarray, torch.Tensor]) -> Tuple[Any, MetaData]:
        l = self._get_or_create_logger(key, 'audio/wav', encode_audio)
        rm = l.result_and_meta(audio)
        return rm

    def log_movie(
            self,
            key: str,
            arr: np.ndarray) -> Tuple[Any, MetaData]:
        l = self._get_or_create_logger(key, 'image/gif', tensor_movie)
        rm = l.result_and_meta(arr)
        return rm
