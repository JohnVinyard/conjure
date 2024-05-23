from typing import Union
from unittest import TestCase
from matplotlib import pyplot as plt
import numpy as np
from io import BytesIO
from uuid import uuid4 as v4
from conjure.contenttype import SupportedContentType
from conjure.decorate import bytes_conjure
from conjure.storage import LmdbCollection

class BytesConjureTests(TestCase):
    
    def setUp(self) -> None:
        self.path = f'/tmp/{v4().hex}'
        self.db = LmdbCollection(self.path)

    def tearDown(self) -> None:
        self.db.destroy()
        
    def test_can_serialize_and_deserialize_image_bytes(self):
        
        counter = { 'c': 0 }
        
        def read_hook(*args, **kwargs):
            counter['c'] += 1
        
        
        @bytes_conjure(self.db, content_type=SupportedContentType.Image, read_hook=read_hook)
        def image(arr: np.ndarray):
            io = BytesIO()
            plt.matshow(arr)
            plt.savefig(io)
            io.seek(0)
            return io.read()
        
        
        data = np.random.normal(0, 1, (128, 128))
        
        image_bytes = image(data)
        self.assertIsInstance(image_bytes, bytes)
        self.assertEqual(counter['c'], 0)
        image_bytes = image(data)
        self.assertIsInstance(image_bytes, bytes)
        self.assertEqual(counter['c'], 1)