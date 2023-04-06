from hashlib import sha1
from typing import Callable
import dill as pickle


class FunctionIdentifier(object):
    def __init__(self):
        super().__init__()
    
    def derive_name(self, fn: Callable) -> bytes:
        raise NotImplementedError()
    


class FunctionNameIdentifier(FunctionIdentifier):
    def __init__(self):
        super().__init__()
    
    def derive_name(self, fn: Callable) -> bytes:
        return fn.__name__




class FunctionContentIdentifier(FunctionIdentifier):
    def __init__(self):
        super().__init__()
    

    def _hash_function(self, f):
        h = sha1()

        if f.__closure__ is not None:
            freevars = [x.cell_contents for x in f.__closure__]
        else:
            freevars = None

        h.update(pickle.dumps(freevars))
        h.update(pickle.dumps(f.__code__.co_consts))
        h.update(f.__name__.encode())
        h.update(f.__code__.co_code)
        value = h.hexdigest()
        return value

    
    def derive_name(self, fn: Callable) -> bytes:
        return self._hash_function(fn)