import numpy as np
from unittest2 import TestCase
from conjure import tensor_movie


class TensorMovieTests(TestCase):
    
    def test_tensor_movie_smoke_test(self):
        data = np.random.binomial(n=1, p=0.1, size=(128, 128, 128))
        movie_bytes = tensor_movie(data)
        self.assertGreater(len(movie_bytes), 0)