from conjure import json_conjure, serve_conjure
from conjure.storage import LmdbCollection
from markdown import markdown

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



def example_func():
    """
    # Here is a doc string

    - this
    - is
    - a
    - list
    """
    pass

if __name__ == '__main__':
    make_bigger({'a': 10, 'b': 3})
    make_bigger({'z': 11, 'b': 3})

    p = serve_conjure(make_bigger, port=9999, n_workers=2)
    input('waiting...')
    p.kill()
