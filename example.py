from conjure import json_conjure, serve_conjure
from conjure.storage import LmdbCollection
from time import sleep
import random
import threading
import shutil

from conjure.timestamp import timestamp_id

collection = LmdbCollection('http_test')

@json_conjure(collection)
def make_bigger(d: dict) -> dict:
    """
    # Make Bigger

    This function takes a dictionary and makes everything in it bigger!

    
    """
    d = dict(**d)
    keys = list(d.keys())
    for key in keys:
        d[f'{key}_bigger'] = d[key] * 10
    return d



if __name__ == '__main__':
    try:
        make_bigger({'a': 10, 'b': 3})
        make_bigger({'z': 11, 'b': 3})

        p = serve_conjure(make_bigger, port=9999, n_workers=2)

        def write():
            for i in range(100):
                make_bigger({ 'g': i })
                sleep(1)

        t = threading.Thread(target=write, args=())
        t.start()
        t.join()

        input('waiting...')
        p.kill()
    finally:
        make_bigger.storage.destroy()

