"""
Secondary indices over conjured function results.

An index is declared alongside a conjured function, and is given an `extract`
function with the signature `extract(result, *args, **kwargs)`, i.e. it
receives the function's result, followed by all of the arguments the function
was called with.  It returns zero or more values to index under the result's
key.

    @json_conjure(db, indices=[
        TextIndex('urls', extract=lambda result, url: url),
        VectorIndex('content', dim=64, extract=lambda result, url: embed(result)),
        ScalarIndex('length', extract=lambda result, url: sum(result.values())),
        TagIndex('domain', extract=lambda result, url: urlparse(url).netloc),
    ])
    def word_count(url: str) -> dict:
        ...

    word_count.indices.urls.search('example.com')
    word_count.indices.length.range(min=100, max=500)
    word_count.indices.content.search(
        query_vector, where=[word_count.indices.domain.has('example.com')])

Index definitions are independent of how indices are stored.  Entries live in
an `IndexStore` (see `conjure.index_store`), which is separate from the
`Collection` that stores results.  A conjured function backed by a
`SqliteCollection` stores its indices in the same file by default; any other
storage requires an explicit `index_store`.

Results and index entries are written separately, so they're eventually
consistent:  a result that's missing index entries (e.g. one cached before
an index existed, or after a crash between the two writes) is indexed on its
next cache hit, since that's when the function's arguments are available.

An index's identity, and therefore the entries it sees, is derived from:

  - the conjured function's identifier, so changing the function (with the
    default `FunctionContentIdentifier`) abandons its old indices, along with
    its old cached results
  - the index's name
  - the extractor's identifier, derived by the index's `identifier` strategy.
    By default, this is a hash of the extractor's code, so changing the
    extractor starts a fresh index.  Pass e.g.
    `identifier=FunctionNameIdentifier()` or
    `identifier=LiteralFunctionIdentifier('v2')` to control this instead.
  - the index's structural configuration (e.g. a vector index's dimension),
    which is always included, since entries with a different structure can't
    be stored together
"""

from dataclasses import dataclass
from hashlib import sha1
import json
import math
import numbers
import re
from typing import Any, Callable, Dict, Iterable, List, Sequence, Union

import numpy as np

from conjure.identifier import FunctionContentIdentifier, FunctionIdentifier
from conjure.storage import ensure_bytes


@dataclass(frozen=True)
class IndexHit:
    """
    A single search result.  Hits are always returned best first, and the
    meaning of `score` depends on the index:

      - TextIndex:  BM25 rank (smaller is more relevant)
      - VectorIndex:  distance (smaller is nearer)
      - ScalarIndex:  the indexed value itself
      - TagIndex:  the number of requested tags the key has
    """
    key: bytes
    score: float


Extractor = Callable[..., Any]

_NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _identifier_bytes(identifier: Any) -> bytes:
    if isinstance(identifier, (str, bytes)):
        return ensure_bytes(identifier)
    return str(identifier).encode()


def _ndim(value: Any) -> int:
    ndim = getattr(value, 'ndim', None)
    return np.ndim(value) if ndim is None else ndim


# Filters #####################################################################

class IndexFilter(object):
    """
    A condition on keys, created by an index (e.g. `length.between(1, 10)`),
    and passed to another index's query via `where=[...]`.  Filters are
    descriptions only; each index store decides how to evaluate them.
    """

    def __init__(self, index: 'ConjureIndex'):
        super().__init__()
        self.index = index


class TextMatch(IndexFilter):
    """
    Keys with an entry matching an FTS5 expression
    """

    def __init__(self, index: 'TextIndex', expression: str):
        super().__init__(index)
        self.expression = expression


class Range(IndexFilter):
    """
    Keys with at least one value in [min, max].  Either bound may be omitted.
    """

    def __init__(self, index: 'ScalarIndex', min=None, max=None):
        super().__init__(index)
        self.min = min
        self.max = max


class HasTags(IndexFilter):
    """
    Keys with any (match='any') or all (match='all') of the given tags
    """

    def __init__(self, index: 'TagIndex', tags: Sequence[str], match: str):
        super().__init__(index)
        self.tags = tags
        self.match = match


Where = Union[None, IndexFilter, Iterable[IndexFilter]]


def _filters(where: Where) -> List[IndexFilter]:
    if where is None:
        return []
    if isinstance(where, IndexFilter):
        return [where]
    filters = list(where)
    for f in filters:
        if not isinstance(f, IndexFilter):
            raise TypeError(
                f'where expects index filters (e.g. index.between(...)), but got {type(f).__name__}')
    return filters


# Indices #####################################################################

class ConjureIndex(object):
    """
    Base class for index definitions.
    """

    # a short, human-readable name for this type of index
    kind = None

    def __init__(
            self,
            name: str,
            extract: Extractor,
            identifier: FunctionIdentifier = None):

        super().__init__()
        if not _NAME_PATTERN.match(name):
            raise ValueError(
                'Index names must be valid Python identifiers (letters, digits and '
                f'underscores, not starting with a digit), but got {name!r}')
        self.name = name
        self.extract = extract
        self.identifier = identifier or FunctionContentIdentifier()
        self.id = None
        self._store = None

    @property
    def extractor_identifier(self) -> bytes:
        """
        The extractor's identity, as derived by this index's identifier strategy
        """
        try:
            return _identifier_bytes(self.identifier.derive_name(self.extract))
        except AttributeError as e:
            raise TypeError(
                f'Could not derive an identifier for the extractor of index {self.name!r} '
                f'using {type(self.identifier).__name__}.  Extractors that are not plain '
                'functions (e.g. callable objects or functools.partial) need another '
                "strategy, e.g. identifier=LiteralFunctionIdentifier('v1')") from e

    def _config(self) -> dict:
        """
        Structural configuration that's always part of this index's identity
        """
        return {}

    def _derive_id(self, function_identifier: Any) -> str:
        identity = json.dumps({
            'type': type(self).__name__,
            'config': self._config(),
        }, sort_keys=True).encode()

        h = sha1()
        for part in (
                _identifier_bytes(function_identifier),
                self.name.encode(),
                self.extractor_identifier,
                identity):
            # length-prefixed, so that parts can't run into each other
            h.update(len(part).to_bytes(8, 'big'))
            h.update(part)

        # usable as a name in most stores, e.g. as a SQL table name
        return f'ix_{self.name}_{h.hexdigest()[:16]}'

    def attach(self, store, function_identifier: Any):
        """
        Bind this index to a conjured function and an index store.  Called by
        `Conjure`, not by client code.
        """
        if self._store is not None:
            raise ValueError(
                f'Index {self.name!r} is already attached to a function.  '
                'Create a separate index instance for each function.')

        self.id = self._derive_id(function_identifier)
        store.attach(self)
        self._store = store

    @property
    def store(self):
        if self._store is None:
            raise ValueError(f'Index {self.name!r} is not attached to a function')
        return self._store

    def values(self, result: Any, *args, **kwargs) -> List[Any]:
        """
        Run the extractor and normalize its output into a list of values
        """
        return self._normalize(self.extract(result, *args, **kwargs))

    def _normalize(self, extracted: Any) -> List[Any]:
        raise NotImplementedError()

    def _check_filters(self, where: Where) -> List[IndexFilter]:
        filters = _filters(where)
        for f in filters:
            if f.index._store is not self.store:
                raise ValueError(
                    f'Filter on index {f.index.name!r} belongs to a different index store '
                    f'than index {self.name!r}')
        return filters

    def keys(self) -> List[bytes]:
        """
        All distinct keys with at least one entry in this index
        """
        return self.store.keys(self)

    def __len__(self):
        return len(self.keys())

    def __contains__(self, key) -> bool:
        """
        Whether this index has processed key, even if the extractor produced
        no values for it
        """
        return self.store.is_processed(self, ensure_bytes(key))


def _strings(index: ConjureIndex, extracted: Any) -> List[str]:
    if extracted is None:
        return []
    if isinstance(extracted, (str, bytes)):
        extracted = [extracted]

    values = []
    for value in extracted:
        if isinstance(value, bytes):
            value = value.decode()
        if not isinstance(value, str):
            raise TypeError(
                f'{type(index).__name__} {index.name!r} expects strings, '
                f'but got {type(value).__name__}')
        values.append(value)
    return values


class TextIndex(ConjureIndex):
    """
    A full-text index, ranked by BM25.

    `extract` returns a string, an iterable of strings, or None.

    `tokenizer` is any SQLite FTS5 tokenizer specification.  The default,
    'unicode61', splits on whitespace and punctuation, so 'example.com/a-b'
    is indexed as the tokens 'example', 'com', 'a' and 'b'.  'trigram'
    supports arbitrary substring matching instead.
    """

    kind = 'text'

    def __init__(
            self,
            name: str,
            extract: Extractor,
            tokenizer: str = 'unicode61',
            identifier: FunctionIdentifier = None):

        super().__init__(name, extract, identifier=identifier)
        self.tokenizer = tokenizer

    def _config(self) -> dict:
        return {'tokenizer': self.tokenizer}

    def _normalize(self, extracted: Any) -> List[str]:
        return _strings(self, extracted)

    @staticmethod
    def _expression(query: str) -> Union[str, None]:
        terms = query.split()
        if not terms:
            return None
        return ' '.join('"' + term.replace('"', '""') + '"' for term in terms)

    def search(
            self,
            query: str,
            limit: Union[int, None] = 10,
            offset: int = 0,
            where: Where = None) -> List[IndexHit]:
        """
        Find keys whose entries contain every term in query.  Terms are
        whitespace-separated, and are matched literally, so punctuation
        (e.g. 'example.com') is safe to include.
        """
        expression = self._expression(query)
        if expression is None:
            return []
        return self.match(expression, limit=limit, offset=offset, where=where)

    def match(
            self,
            expression: str,
            limit: Union[int, None] = 10,
            offset: int = 0,
            where: Where = None) -> List[IndexHit]:
        """
        Search using a raw FTS5 query expression, which supports prefix
        queries ('exam*'), boolean operators, phrases and more.  See
        https://www.sqlite.org/fts5.html#full_text_query_syntax
        """
        return self.store.text_search(
            self, expression, limit, offset, self._check_filters(where))

    def matches(self, query: str, raw: bool = False) -> TextMatch:
        """
        A filter for keys whose entries contain every term in query, or, if
        raw is True, that match the FTS5 expression query
        """
        expression = query if raw else self._expression(query)
        if not expression:
            raise ValueError('A text filter needs a non-empty query')
        return TextMatch(self, expression)


class VectorIndex(ConjureIndex):
    """
    A nearest-neighbor index over fixed-size float vectors.  Search is exact
    (brute force), which is fast enough for up to roughly hundreds of
    thousands of vectors.

    `extract` returns a vector of shape (dim,), several vectors as an array of
    shape (n, dim) or a list of vectors, or None.

    `metric` is one of 'cosine', 'l2' or 'l1'.
    """

    kind = 'vector'

    METRICS = ('cosine', 'l2', 'l1')

    def __init__(
            self,
            name: str,
            dim: int,
            extract: Extractor,
            metric: str = 'cosine',
            identifier: FunctionIdentifier = None):

        super().__init__(name, extract, identifier=identifier)
        if int(dim) != dim or dim < 1:
            raise ValueError(f'dim must be a positive integer, but got {dim!r}')
        if metric not in self.METRICS:
            raise ValueError(f'metric must be one of {self.METRICS}, but got {metric!r}')
        self.dim = int(dim)
        self.metric = metric

    def _config(self) -> dict:
        return {'dim': self.dim, 'metric': self.metric}

    def _as_vectors(self, value: Any) -> np.ndarray:
        try:
            # torch tensors, which may require grad or live on the GPU
            value = value.detach().cpu().numpy()
        except AttributeError:
            pass

        arr = np.asarray(value, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr[None, :]
        if arr.ndim != 2 or arr.shape[1] != self.dim:
            raise ValueError(
                f'VectorIndex {self.name!r} expects vectors of shape ({self.dim},), '
                f'but got an array of shape {np.shape(value)}')
        if not np.all(np.isfinite(arr)):
            raise ValueError(f'VectorIndex {self.name!r} received a vector with NaN or inf values')
        return arr

    def _normalize(self, extracted: Any) -> List[np.ndarray]:
        if extracted is None:
            return []
        if isinstance(extracted, (list, tuple)):
            if len(extracted) == 0:
                return []
            # a list of numbers is a single vector, while a list of
            # array-likes is several vectors
            if all(_ndim(item) == 0 for item in extracted):
                return list(self._as_vectors([float(x) for x in extracted]))
            return [v for item in extracted for v in self._as_vectors(item)]
        return list(self._as_vectors(extracted))

    def search(self, vector: Any, limit: int = 10, where: Where = None) -> List[IndexHit]:
        """
        Find the keys with entries nearest to vector, nearest first.  When a
        key has several entries, its nearest entry determines its score.
        With `where`, only keys passing every filter are considered.
        """
        query = self._as_vectors(vector)
        if len(query) != 1:
            raise ValueError('search expects a single vector')
        return self.store.vector_search(
            self, query[0], limit, self._check_filters(where))


class ScalarIndex(ConjureIndex):
    """
    An index over numbers, for range queries and sorting.

    `extract` returns a number, an iterable of numbers, or None.  When a key
    has several values, it matches a range if any of its values do, and it's
    sorted by its best value:  the smallest when ascending, and the largest
    when descending.
    """

    kind = 'scalar'

    def _normalize(self, extracted: Any) -> List[Union[int, float]]:
        if extracted is None:
            return []
        if isinstance(extracted, np.ndarray):
            items = extracted.ravel().tolist()
        elif isinstance(extracted, (str, bytes)) or _ndim(extracted) == 0:
            items = [extracted]
        else:
            items = list(extracted)

        values = []
        for value in items:
            # numpy and torch scalars
            if hasattr(value, 'item') and _ndim(value) == 0:
                value = value.item()
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                raise TypeError(
                    f'ScalarIndex {self.name!r} expects numbers, but got {type(value).__name__}')
            if isinstance(value, float) and math.isnan(value):
                raise ValueError(f'ScalarIndex {self.name!r} received NaN')
            values.append(value if isinstance(value, int) else float(value))
        return values

    def range(
            self,
            min=None,
            max=None,
            descending: bool = False,
            limit: Union[int, None] = 10,
            offset: int = 0,
            where: Where = None) -> List[IndexHit]:
        """
        Keys with a value in [min, max], sorted by value.  Either bound may be
        omitted.  Each hit's score is the key's best value within the range.
        """
        return self.store.scalar_range(
            self, min, max, descending, limit, offset, self._check_filters(where))

    def sorted(
            self,
            descending: bool = False,
            limit: Union[int, None] = 10,
            offset: int = 0,
            where: Where = None) -> List[IndexHit]:
        """
        All keys, sorted by value
        """
        return self.range(
            descending=descending, limit=limit, offset=offset, where=where)

    def between(self, min=None, max=None) -> Range:
        """
        A filter for keys with a value in [min, max]
        """
        return Range(self, min, max)


class TagIndex(ConjureIndex):
    """
    An index over exact string values, e.g. categories, labels or
    identifiers.  Tags are case-sensitive.

    `extract` returns a string, an iterable of strings, or None.
    """

    kind = 'tag'

    MATCH = ('any', 'all')

    def _normalize(self, extracted: Any) -> List[str]:
        # a key either has a tag or it doesn't
        return list(dict.fromkeys(_strings(self, extracted)))

    def _tags(self, tags: Sequence[str], match: str) -> List[str]:
        if match not in self.MATCH:
            raise ValueError(f'match must be one of {self.MATCH}, but got {match!r}')
        return list(dict.fromkeys(_strings(self, list(tags))))

    def search(
            self,
            *tags: str,
            match: str = 'any',
            limit: Union[int, None] = 10,
            offset: int = 0,
            where: Where = None) -> List[IndexHit]:
        """
        Keys with any (match='any') or all (match='all') of tags.  Keys with
        more of the requested tags come first.
        """
        tags = self._tags(tags, match)
        if not tags:
            return []
        return self.store.tag_search(
            self, tags, match, limit, offset, self._check_filters(where))

    def has(self, *tags: str, match: str = 'any') -> HasTags:
        """
        A filter for keys with any (match='any') or all (match='all') of tags
        """
        tags = self._tags(tags, match)
        if not tags:
            raise ValueError('A tag filter needs at least one tag')
        return HasTags(self, tags, match)

    def counts(self, where: Where = None) -> Dict[str, int]:
        """
        The number of keys with each tag, most common first
        """
        return self.store.tag_counts(self, self._check_filters(where))


class Indices(object):
    """
    The indices attached to a conjured function, accessible by name as
    attributes (`func.indices.urls`) or items (`func.indices['urls']`)
    """

    def __init__(self, indices: Iterable[ConjureIndex] = ()):
        super().__init__()
        by_name = {}
        for index in indices:
            if index.name in by_name:
                raise ValueError(f'Duplicate index name {index.name!r}')
            by_name[index.name] = index
        # stored under a mangled name so it can't collide with index names
        self.__dict__['_Indices__by_name'] = by_name

    def __getattr__(self, name: str) -> ConjureIndex:
        try:
            return self.__by_name[name]
        except KeyError:
            raise AttributeError(
                f'No index named {name!r}.  Available indices: {sorted(self.__by_name)}')

    def __setattr__(self, name, value):
        raise AttributeError('Indices are read-only')

    def __getitem__(self, name: str) -> ConjureIndex:
        return self.__by_name[name]

    def __contains__(self, name: str) -> bool:
        return name in self.__by_name

    def __iter__(self):
        return iter(self.__by_name.values())

    def __len__(self):
        return len(self.__by_name)

    def __bool__(self):
        return bool(self.__by_name)

    def __dir__(self):
        return sorted(self.__by_name)

    def __repr__(self):
        return f'Indices({", ".join(sorted(self.__by_name))})'
