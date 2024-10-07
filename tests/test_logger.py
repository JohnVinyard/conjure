from unittest import TestCase
import numpy as np

from conjure.logger import display_matrix


class TestLogger(TestCase):

    def test_display_matrix_2d(self):
        x = np.random.normal(0, 1, (128, 128))
        b = display_matrix(x)
        self.assertIsInstance(b, bytes)

    def test_display_matrix_3d(self):
        x = np.random.normal(0, 1, (128, 128, 3))
        b = display_matrix(x)
        self.assertIsInstance(b, bytes)