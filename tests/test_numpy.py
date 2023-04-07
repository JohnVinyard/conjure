from unittest import TestCase
from uuid import uuid4 as v4
import numpy as np

from conjure.decorate import Conjure
from conjure.identifier import LiteralFunctionIdentifier, ParamsHash
from conjure.serialize import NumpyDeserializer, NumpySerializer
from conjure.storage import LmdbCollection
from typing import BinaryIO

class AllOnesDeserializer(NumpyDeserializer):

    def read(self, sink: BinaryIO) -> np.ndarray:
        arr = super().read(sink)
        arr[:] = 1
        return arr
    
    def from_bytes(self, encoded: bytes) -> np.ndarray:
        arr  = super().from_bytes(encoded)
        arr[:] = 1
        return arr

class TestNumpyStorage(TestCase):

    def setUp(self) -> None:
        self.path =f'/tmp/{v4().hex}'
        self.db = LmdbCollection(self.path)
    
    def tearDown(self) -> None:
        self.db.destroy()

    def test_can_store_and_retrieve_array(self):

        def get_spec_mag(x: np.ndarray) -> np.ndarray:
            spec = np.fft.rfft(x, axis=-1, norm='ortho')
            return np.abs(spec).astype(np.float32)
        
        conj = Conjure(
            callable=get_spec_mag, 
            content_type='application/octet-stream',
            storage=self.db,
            func_identifier=LiteralFunctionIdentifier('numpy_test'),
            param_identifier=ParamsHash(),
            serializer=NumpySerializer(),
            deserializer=AllOnesDeserializer())
        
        arr = np.random.normal(0, 1, (3, 7, 8))

        computed_result = conj.__call__(arr)
        self.assertFalse(np.allclose(computed_result, 1))
        
        retrieved = conj.__call__(arr)

        self.assertEqual(np.float32, retrieved.dtype)
        self.assertEqual((3, 7, 5), retrieved.shape)
        self.assertTrue(np.allclose(1, retrieved))