import re
import numpy as np
import requests
from conjure.decorate import conjure_index, numpy_conjure, text_conjure, time_series_conjure
from conjure.serve import serve_conjure
from conjure.storage import LmdbCollection, LocalCollectionWithBackup, ensure_str
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


def get_all_links():
    hostname = 'http://textfiles.com'
    resp = requests.get(f'{hostname}/games/')
    pattern = re.compile(r'HREF="(?P<path>[^"]+\.txt)"')
    for match in pattern.finditer(resp.content.decode()):
        yield f'{hostname}/games/{match.groupdict()["path"]}'

all_links = list(get_all_links())


@text_conjure(collection)
def textfile(url):
    resp = requests.get(url)
    return resp.content

@conjure_index(textfile, collection.index_storage('content_index'))
def content_index(key: bytes, result: str, *args, **kwargs):
    words = result.split()
    for word in words:
        yield word.lower(), dict(key=ensure_str(key))


def fetch_data():
    while True:
        n = all_links.pop()
        print(f'fetching {n}')
        textfile(n)
        sleep(random() * 10)

if __name__ == '__main__':

    t = Thread(target=fetch_data)
    t.start()

    try:

        p = serve_conjure(
            [
                textfile
            ],
            indexes=[
                content_index
            ],
            port=9999,
            n_workers=2)

        input('waiting...')
        p.kill()
    finally:
        time_series.storage.destroy()
        pass
