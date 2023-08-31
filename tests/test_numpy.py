from unittest import TestCase
from uuid import uuid4 as v4
import numpy as np
from conjure.contenttype import SupportedContentType

from conjure.decorate import Conjure, numpy_conjure, time_series_conjure, conjure
from conjure.identifier import FunctionContentIdentifier, LiteralFunctionIdentifier, LiteralParamsIdentifier, ParamsHash
from conjure.serialize import NumpyDeserializer, NumpySerializer
from conjure.storage import LmdbCollection
from typing import BinaryIO


class AllOnesDeserializer(NumpyDeserializer):

    def read(self, sink: BinaryIO) -> np.ndarray:
        arr = super().read(sink)
        arr[:] = 1
        return arr

    def from_bytes(self, encoded: bytes) -> np.ndarray:
        arr = super().from_bytes(encoded)
        arr[:] = 1
        return arr


class TestNumpyStorage(TestCase):

    def setUp(self) -> None:
        self.path = f'/tmp/{v4().hex}'
        self.db = LmdbCollection(self.path)

    def tearDown(self) -> None:
        self.db.destroy()
    

    def test_can_get_metadata(self):
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

        meta = conj.meta(arr)

        self.assertEqual(meta.public_uri, None)
        self.assertEqual('application/octet-stream', meta.content_type)
    

    def test_can_access_feed_when_using_literal_func_identifier(self):

        @numpy_conjure(
                self.db, 
                content_type=SupportedContentType.Tensor, 
                identifier='static')
        def get_spec_mag(x: np.ndarray) -> np.ndarray:
            spec = np.fft.rfft(x, axis=-1, norm='ortho')
            return np.abs(spec).astype(np.float32)
        

        arr = np.random.normal(0, 1, (3, 7, 8))
        get_spec_mag(arr)

        items = list(get_spec_mag.feed())
        self.assertEqual(len(items), 1)


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

    def test_can_store_growing_series_under_single_key(self):

        values = {
            'values': np.zeros((1,))
        }

        def loss(value):
            values['values'] = np.concatenate([values['values'], value])
            return values['values']

        loss = Conjure(
            loss,
            content_type=SupportedContentType.TimeSeries.value,
            storage=self.db,
            func_identifier=FunctionContentIdentifier(include_closures=False),
            param_identifier=LiteralParamsIdentifier(b'loss'),
            serializer=NumpySerializer(),
            deserializer=NumpyDeserializer(),
            prefer_cache=False
        )

        loss(np.random.normal(0, 1, (1,)))
        loss(np.random.normal(0, 1, (1,)))
        final = loss(np.random.normal(0, 1, (1,)))

        self.assertEqual((4,), final.shape)

        total_db_keys = len(list(self.db.iter_prefix('')))
        self.assertEqual(1, total_db_keys)

        total_keys = len(list(loss.iter_keys()))
        self.assertEqual(1, total_keys)

        feed_items = list(loss.feed())
        self.assertEqual(3, len(feed_items))
