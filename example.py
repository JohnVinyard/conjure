import numpy as np
from conjure import numpy_conjure, serve_conjure
from conjure.storage import LmdbCollection


collection = LmdbCollection('http_test')


@numpy_conjure(collection)
def spectral_magnitude(arr: np.ndarray):
    spec = np.fft.rfft(arr, axis=-1, norm='ortho')
    spec = np.abs(spec)
    return spec


if __name__ == '__main__':
    a = np.random.normal(0, 1, 10)
    b = np.random.normal(0, 1, (10, 10))
    c = np.random.normal(0, 1, (10, 10, 10))

    try:
        spectral_magnitude(a)
        spectral_magnitude(b)
        spectral_magnitude(c)

        p = serve_conjure(spectral_magnitude, port=9999, n_workers=2)


        input('waiting...')
        p.kill()
    finally:
        spectral_magnitude.storage.destroy()
