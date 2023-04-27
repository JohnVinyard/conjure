from conjure import text_conjure, json_conjure, LmdbCollection, conjure, JSONSerializer, JSONDeserializer
from conjure.identifier import FunctionContentIdentifier, ParamsHash

collection = LmdbCollection('textfiles')


custom = conjure(
    content_type='text/plain',
    storage=collection,
    func_identifier=FunctionContentIdentifier(),
    param_identifier=ParamsHash(),
    serializer=JSONSerializer(),
    deserializer=JSONDeserializer()
)


def textfile_index(path: str, content: bytes):
    """
    TODOs:

    - this key should be func_INDEXVALUE_paramshash, to allow for prefix = func_INDEXVALUE queries
      and to ensure that identical values are not overwritten.  for a single call to the index function
      func and paramshash would remain constant, while INDEXVALUE would vary
    
    - index conjure functions should be able to return multiple values, i.e., they are iterators

    - 


    What if, instead of trying to re-use conjure, indexes are truly something different?

    they are expected to return an iterator of (key, value) pairs where keys are bytes
    and values are json, required to have a special key property that points to the main collection?

    
    The big difference that's keeping me from using conure as-is is the fact that I need _results_
    to compute a key for indexes

    For conjure, if I need the result to compute the key, that defeats the whole purpose!
    """

    words = set(map(lambda x: x.strip().lower(), content.decode().split()))

    for word in words:
        yield word, { 'title': path }
    

# @text_conjure(collection)
def get_textfile(path):
    import requests
    resp = requests.get(f'http://textfiles.com/{path}')
    return resp.content

