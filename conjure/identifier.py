from hashlib import sha1
import json
from typing import Callable
import dill as pickle
import torch

class FunctionIdentifier(object):
    def __init__(self):
        super().__init__()

    def derive_name(self, fn: Callable) -> bytes:
        raise NotImplementedError()


class LiteralFunctionIdentifier(FunctionIdentifier):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def derive_name(self, fn: Callable) -> bytes:
        return self.name


class FunctionNameIdentifier(FunctionIdentifier):
    def __init__(self):
        super().__init__()

    def derive_name(self, fn: Callable) -> bytes:
        return fn.__name__


class FunctionContentIdentifier(FunctionIdentifier):
    def __init__(self, include_closures=False):
        super().__init__()
        self.include_closures = include_closures

    def _hash_function(self, f):
        h = sha1()

        if f.__closure__ is not None:
            freevars = [x.cell_contents for x in f.__closure__]
        else:
            freevars = None

        if self.include_closures:
            h.update(pickle.dumps(freevars))

        h.update(pickle.dumps(f.__code__.co_consts))
        h.update(f.__name__.encode())
        h.update(f.__code__.co_code)
        value = h.hexdigest()
        return value

    def derive_name(self, fn: Callable) -> bytes:
        return self._hash_function(fn)


class ParamsIdentifier(object):
    def __init__(self):
        super().__init__()

    def derive_name(self, *args, **kwargs) -> bytes:
        pass


class LiteralParamsIdentifier(object):

    def __init__(self, name: bytes):
        super().__init__()
        self.name = name

    def derive_name(self, *args, **kwargs) -> bytes:
        return self.name


class ParamsHash(ParamsIdentifier):
    def __init__(self):
        super().__init__()

    def _get_underlying_data(self, value):
        """
        Wraps a special case for torch.Tensor values, which, unlike numpy arrays, do not have
        a consistent hash value for identical/equal arrays or tensors of values
        """

        if isinstance(value, torch.Tensor):
            return value.data.cpu().numpy()
        return value


    def _hash_args(self, *args, **kwargs):
        args_hash = sha1()

        transformed_args = list(map(self._get_underlying_data, args))
        transformed_kwargs = {k: self._get_underlying_data(v) for k, v in kwargs.items()}

        args_hash.update(pickle.dumps(transformed_args))
        args_hash.update(pickle.dumps(transformed_kwargs))

        args_hash = args_hash.hexdigest()
        return args_hash

    def derive_name(self, *args, **kwargs) -> bytes:
        return self._hash_args(*args, **kwargs)


class ParamsJSON(ParamsIdentifier):
    def __init__(self):
        super().__init__()

    def derive_name(self, *args, **kwargs) -> bytes:
        if len(args):
            raise ValueError(
                'ParamsJSONSerializer does not support non-keyword arguments')

        return json.dumps(kwargs)
