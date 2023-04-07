import json
import dill
from typing import Any, BinaryIO
from io import BytesIO
import numpy as np
import datetime

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
    


class JSONSerializer(Serializer):
    def __init__(self):
        super().__init__()
    
    def to_bytes(self, content: Any) -> bytes:
        return json.dumps(content).encode()

    def write(self, content: Any, sink: BinaryIO) -> None:
        json.dump(content, sink)

class JSONDeserializer(Deserializer):
    def __init__(self, tag_deserialized=False):
        super().__init__()
        self.tag_deserialized = tag_deserialized
    
    def _tag(self, content):
        if self.tag_deserialized:
            content['__deserialized'] = datetime.datetime.utcnow()
        
        return content
    
    def from_bytes(self, encoded: bytes) -> Any:
        data = json.loads(encoded)
        return self._tag(data)
    
    def read(self, sink: BinaryIO) -> Any:
        data = json.load(sink)
        return self._tag(data)

class NumpySerializer(Serializer):
    def __init__(self):
        super().__init__()
    
    def to_bytes(self, content: np.ndarray) -> bytes:
        bio = BytesIO()
        np.save(bio, content)
        bio.seek(0)
        return bio.read()
    
    def write(self, content: np.ndarray, sink: BinaryIO) -> None:
        np.save(sink, content)


class NumpyDeserializer(Deserializer):
    def __init__(self):
        super().__init__()
    
    def from_bytes(self, encoded: bytes) -> np.ndarray:
        bio = BytesIO()
        bio.write(encoded)
        bio.seek(0)
        output = self.read(bio)
        return output
    
    def read(self, sink: BinaryIO) -> np.ndarray:
        output = np.load(sink)
        return output