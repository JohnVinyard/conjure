from matplotlib import pyplot as plt
import numpy as np
from io import BytesIO
from typing import Union


def two_dim_matrix_display_bytes(x: np.ndarray, cmap: Union[str, None] = None) -> bytes:
    bio = BytesIO()
    plt.matshow(x, cmap=cmap)
    plt.savefig(bio, format='png')
    plt.clf()
    bio.seek(0)
    return bio.read()
