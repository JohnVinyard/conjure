import dill
from typing import Any, BinaryIO

class Serializer(object):
    def __init__(self):
        super().__init__()
    
    def to_bytes(self, content: Any) -> bytes:
        raise NotImplementedError()
    
    def write(self, content: Any, sink: BinaryIO) -> None:
        raise NotImplementedError()


class Deserializer(object):
    def __init__(self):
        super().__init__()
    
    def from_bytes(self, encoded: bytes) -> Any:
        raise NotImplementedError()

    def read(self, sink: BinaryIO) -> Any:
        raise NotImplementedError()