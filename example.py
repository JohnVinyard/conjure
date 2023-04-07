from conjure import json_conjure, serve_conjure
from conjure.storage import LmdbCollection

collection = LmdbCollection('http_test')

@json_conjure(collection)
def make_bigger(d: dict) -> dict:
    d = dict(**d)
    keys = list(d.keys())
    for key in keys:
        d[f'{key}_bigger'] = d[key] * 10
    return d




if __name__ == '__main__':
    make_bigger({'a': 10, 'b': 3})
    make_bigger({'z': 11, 'b': 3})

    p = serve_conjure(make_bigger, port=9999, n_workers=2)
    input('waiting...')
    p.kill()
