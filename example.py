import numpy as np
from conjure.decorate import numpy_conjure, time_series_conjure
from conjure.serve import serve_conjure
from conjure.storage import LmdbCollection, LocalCollectionWithBackup
from time import sleep
from threading import Thread
from random import random


# collection = LmdbCollection('conjure-test')
collection = LocalCollectionWithBackup(
    local_path='conjure-test',
    remote_bucket='conjure-test',
    is_public=True,
    local_backup=False,
    cors_enabled=True
)


@numpy_conjure(collection)
def spectral_magnitude(arr: np.ndarray):
    """
    Compute the spectral magnitude along the last dimension of 
    an arbitrarily-sized tensor
    """
    spec = np.fft.rfft(arr, axis=-1, norm='ortho')
    spec = np.abs(spec).astype(np.float32)
    return spec


d = {
    'values': np.random.uniform(0, 1, (2, 100)).astype(np.float32)
}


@time_series_conjure(collection, 'loss')
def time_series():
    """
    Append values to a time series
    """
    d['values'] = np.concatenate(
        [d['values'], np.random.uniform(0, 1, (2, 2)).astype(np.float32)], axis=-1)
    return d['values']


def add_values():
    while True:
        print('add_values')
        try:
            time_series()
            sleep(random() * 10)
        except KeyboardInterrupt:
            return


def compute_new_spectral_magnitude():
    while True:
        print('compute_new_spectral_magnitude')
        try:
            inp = np.random.normal(0, 1, (10, 10, 10))
            spectral_magnitude(inp)
            sleep(random() * 10)
        except KeyboardInterrupt:
            return


if __name__ == '__main__':

    t = Thread(target=add_values)
    t.start()

    t2 = Thread(target=compute_new_spectral_magnitude)
    t2.start()

    try:

        p = serve_conjure(
            [
                time_series,
                spectral_magnitude
            ],
            port=9999,
            n_workers=2)

        input('waiting...')
        p.kill()
    finally:
        time_series.storage.destroy()
        pass
