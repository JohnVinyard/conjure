import json
from multiprocessing import Process
from time import sleep
from typing import Union
from unittest import TestCase, skip
import requests
from random import random

from traitlets import Callable

from conjure import IdentitySerializer, IdentityDeserializer, FunctionNameIdentifier
from conjure.decorate import Conjure, WriteNotification, json_conjure, text_conjure, bytes_conjure
from conjure.indexes import TextIndex, VectorIndex
from conjure.index_store import SqliteIndexStore
from conjure.identifier import FunctionContentIdentifier, LiteralFunctionIdentifier, LiteralParamsIdentifier, ParamsHash
from conjure.serialize import JSONDeserializer, JSONSerializer
from conjure.serve import serve_conjure
from conjure.storage import LmdbCollection, SqliteCollection, ensure_str
from conjure.contenttype import SupportedContentType
from uuid import uuid4 as v4
import numpy as np


def retry(func: Callable, max_tries: int = 10, wait_time_seconds=1):
    exc = None
    for i in range(max_tries):
        try:
            func()
            return
        except Exception as e:
            exc = e
            sleep(wait_time_seconds)
            continue

    raise exc


class DecorateTests(TestCase):
    collection_class = LmdbCollection
    serve_port = 9999

    def setUp(self) -> None:
        self.process: Union[Process, None] = None
        self.path = f'tests/tmp/{v4().hex}'
        self.db = self.collection_class(self.path)

        # SqliteCollection keeps indices in its own file by default, while
        # other storage needs a separate index store
        self.index_store = None if self.collection_class is SqliteCollection \
            else SqliteIndexStore(f'{self.path}.indices.sqlite')

    def tearDown(self) -> None:
        self.db.destroy()
        if self.index_store is not None:
            self.index_store.destroy()

        if self.process is not None and self.process.is_alive():
            self.process.join(5)
            self.process.terminate()
    
    def test_can_get_result_and_metadata_together(self):
        @json_conjure(self.db)
        def make_bigger(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d

        inp = {'a': 10, 'b': 3}
        
        key = make_bigger.key(inp)
        
        initial, meta = make_bigger.result_and_meta(inp)

        self.assertEqual(key, meta.key)
        self.assertEqual('application/json', meta.content_type)
        self.assertEqual(len(json.dumps(initial).encode()),
                         meta.content_length)
        self.assertEqual(None, meta.public_uri)
    
    def test_bytes_conjure_does_not_require_read_hook(self):
        
        @bytes_conjure(self.db, content_type=SupportedContentType.Tensor)
        def arr_to_bytes(data: np.ndarray):
            return bytes(data.data)
        
        arr = np.random.normal(0, 1, (16,))
        a = arr_to_bytes(arr)
        b = arr_to_bytes(arr)

    def test_honors_func_identifier(self):

        def arr_to_bytes(data: np.ndarray):
            return bytes(data.data)

        conj = Conjure(
            callable=arr_to_bytes,
            content_type='application/octet-stream',
            storage=self.db,
            func_identifier=LiteralFunctionIdentifier('funcname'),
            param_identifier=ParamsHash(),
            serializer=IdentitySerializer(),
            deserializer=IdentityDeserializer())

        self.assertEqual(conj.name, 'funcname')

    def test_honors_func_identifier_when_using_func_name(self):

        def arr2bytes(data: np.ndarray):
            return bytes(data.data)

        conj = Conjure(
            callable=arr2bytes,
            content_type='application/octet-stream',
            storage=self.db,
            func_identifier=FunctionNameIdentifier(),
            param_identifier=ParamsHash(),
            serializer=IdentitySerializer(),
            deserializer=IdentityDeserializer())

        self.assertEqual(conj.name, 'arr2bytes')

    def test_can_exercise_read_from_cache_hook(self):

        g = {'value': 0}

        def make_bigger(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d
        
        def read_hook(val):
            g['value'] += 1

        conj = Conjure(
            make_bigger,
            'application/json',
            self.db,
            FunctionContentIdentifier(),
            ParamsHash(),
            JSONSerializer(),
            JSONDeserializer(),
            key_delimiter='_',
            prefer_cache=True,
            read_from_cache_hook=read_hook
        )

        values = conj({'a': 10, 'b': 3})
        values = conj({'a': 10, 'b': 3})
        values = conj({'a': 10, 'b': 3})

        self.assertEqual(2, g['value'])

    def test_can_force_recompute(self):

        loss_values = []

        def func(new_value):
            loss_values.append(new_value)
            return loss_values

        conj = Conjure(
            func,
            'application/json',
            self.db,
            LiteralFunctionIdentifier('loss'),
            LiteralParamsIdentifier('loss_params'),
            JSONSerializer(),
            JSONDeserializer(),
            key_delimiter='_',
            prefer_cache=False)

        values = conj(1)
        values = conj(1)
        values = conj(1)

        self.assertEqual(3, len(values))
        self.assertListEqual([1, 1, 1], values)

    def test_can_serve(self):

        @json_conjure(self.db)
        def make_bigger(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d

        result = make_bigger({'a': 10, 'b': 3})
        make_bigger({'z': 11, 'b': 3})

        self.process = serve_conjure(
            [make_bigger], port=self.serve_port, n_workers=1, revive=False)

        def get_keys_over_http():
            resp = requests.get(
                f'http://localhost:{self.serve_port}/functions/{make_bigger.identifier}', verify=False)
            keys = resp.json()['keys']
            self.assertEqual(2, len(keys))

        retry(get_keys_over_http)

        meta = make_bigger.meta({'a': 10, 'b': 3})
        resp = requests.get(
            f'http://localhost:{self.serve_port}/functions/{make_bigger.identifier}/{meta.key.decode()}', verify=False)
        self.assertEqual(200, resp.status_code)
        self.assertEqual('application/json', resp.headers['content-type'])
        self.assertEqual(json.dumps(result), resp.content.decode())

    def test_can_iterate_keys_when_storage_is_shared(self):
        @json_conjure(self.db)
        def make_bigger(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d

        @json_conjure(self.db)
        def make_smaller(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] / 10
            return d

        make_bigger({'a': 10, 'b': 3})
        make_bigger({'z': 11, 'b': 3})

        make_smaller({'z': 11, 'b': 3})
        make_smaller({'a': 11, 'b': 3})
        make_smaller({'j': 11, 'q': 3})

        bigger_keys = list(make_bigger.iter_keys())
        smaller_keys = list(make_smaller.iter_keys())

        self.assertEqual(2, len(bigger_keys))

        self.assertEqual(3, len(smaller_keys))

    def test_feeds_are_segregated_when_storage_is_shared(self):
        @json_conjure(self.db)
        def make_bigger(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d

        @json_conjure(self.db)
        def make_smaller(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_smaller'] = d[key] / 10
            return d

        make_bigger({'a': 10, 'b': 3})
        make_bigger({'z': 11, 'b': 3})

        make_smaller({'z': 11, 'b': 3})
        make_smaller({'a': 11, 'b': 3})
        make_smaller({'j': 11, 'q': 3})

        bigger_feed = list(make_bigger.feed())
        smaller_feed = list(make_smaller.feed())

        self.assertEqual(2, len(bigger_feed))
        self.assertEqual(3, len(smaller_feed))

    def test_can_get_most_recent_key(self):
        @json_conjure(self.db)
        def make_bigger(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d

        @json_conjure(self.db)
        def make_smaller(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_smaller'] = d[key] / 10
            return d

        make_bigger({'a': 10, 'b': 3})
        make_bigger({'z': 11, 'b': 3})

        make_smaller({'z': 11, 'b': 3})
        make_smaller({'a': 11, 'b': 3})
        make_smaller({'j': 11, 'q': 3})

        smaller_feed = list(make_smaller.feed())

        self.assertEqual(make_smaller.most_recent_key(),
                         smaller_feed[-1]['key'])

    def test_can_register_listener(self):
        @json_conjure(self.db)
        def make_bigger(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d

        notifications = []

        def listen(notifiction: WriteNotification):
            notifications.append(notifiction)

        make_bigger.register_listener(listen)

        make_bigger({'a': 10, 'b': 3})
        make_bigger({'z': 11, 'b': 3})

        self.assertEqual(2, len(notifications))

        self.assertNotEqual(notifications[0].key, notifications[1].key)

    def can_access_description(self):

        @json_conjure(self.db)
        def make_bigger(d: dict) -> dict:
            """
            These are the docs!
            """
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d

        self.assertEqual('These are the docs!', make_bigger.description)

    def test_can_get_object_metadata(self):

        @json_conjure(self.db)
        def make_bigger(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d

        inp = {'a': 10, 'b': 3}
        key = make_bigger.key(inp)
        initial = make_bigger(inp)
        self.assertEqual(initial['a_bigger'], 100)

        meta = make_bigger.meta(inp)

        self.assertEqual(key, meta.key)
        self.assertEqual('application/json', meta.content_type)
        self.assertEqual(len(json.dumps(initial).encode()),
                         meta.content_length)
        self.assertEqual(None, meta.public_uri)

    def test_can_decorate_function(self):

        @json_conjure(self.db, tag_deserialized=True)
        def make_bigger(d: dict) -> dict:
            d = dict(**d)
            keys = list(d.keys())
            for key in keys:
                d[f'{key}_bigger'] = d[key] * 10
            return d

        initial = make_bigger({'a': 10, 'b': 3})
        self.assertEqual(initial['a_bigger'], 100)

        retrieved = make_bigger({'a': 10, 'b': 3})
        self.assertEqual(retrieved['a_bigger'], 100)
        self.assertIn('__deserialized', retrieved)
    

    # indices ###############################################################

    SKY_CONTENT = {
        'a': 'lights in the sky',
        'b': 'look to the sky',
        'c': 'I look at the sky and the sky looks at me'
    }

    def content_index(self, calls: list = None):
        def extract(result, key):
            """
            The full text of each document
            """
            if calls is not None:
                calls.append(key)
            return result

        return TextIndex('content', extract=extract)

    def test_indices_need_an_index_store_when_there_is_no_default(self):
        if self.index_store is None:
            self.skipTest(f'{self.collection_class.__name__} has a default index store')

        def define():
            @text_conjure(self.db, indices=[self.content_index()])
            def fetch_content(key):
                return self.SKY_CONTENT[key]

        self.assertRaises(TypeError, define)

    def test_can_create_index_after_initial_function_creation(self):
        content = self.SKY_CONTENT

        def fetch_content(key):
            return content[key]

        unindexed = text_conjure(self.db)(fetch_content)
        unindexed('a')
        unindexed('b')
        unindexed('c')

        indexed = text_conjure(self.db, index_store=self.index_store, indices=[self.content_index()])(fetch_content)
        self.assertEqual([], indexed.indices.content.search('sky'))

        # cache hits index results that were computed before the index existed
        indexed('a')
        indexed('b')
        indexed('c')

        hits = indexed.indices.content.search('sky')
        self.assertEqual(3, len(hits))
        self.assertEqual(
            {indexed.key(k) for k in content}, {hit.key for hit in hits})

    def test_can_index_and_search(self):
        content = {
            'a': 'lights in the sky',
            'b': 'look to the sky'
        }

        @text_conjure(self.db, index_store=self.index_store, indices=[self.content_index()])
        def fetch_content(key):
            return content[key]

        fetch_content('a')
        fetch_content('b')

        self.assertEqual(2, len(fetch_content.indices.content.search('sky')))
        self.assertEqual(
            [fetch_content.key('a')],
            [hit.key for hit in fetch_content.indices.content.search('lights')])

    def test_can_index_incrementally(self):
        content = self.SKY_CONTENT
        calls = []

        @text_conjure(self.db, index_store=self.index_store, indices=[self.content_index(calls)])
        def fetch_content(key):
            return content[key]

        fetch_content('a')
        fetch_content('b')
        self.assertEqual(['a', 'b'], calls)
        self.assertEqual(2, len(fetch_content.indices.content))

        fetch_content('c')
        self.assertEqual(['a', 'b', 'c'], calls)
        self.assertEqual(3, len(fetch_content.indices.content))

        # each result is indexed only once
        fetch_content('a')
        fetch_content('c')
        self.assertEqual(['a', 'b', 'c'], calls)

    def test_can_index_and_rank_by_relevance(self):
        content = {
            'a': 'the sky over the hills and the valleys and the rivers',
            'b': 'sky sky sky',
            'c': 'a clear sky tonight',
        }

        @text_conjure(self.db, index_store=self.index_store, indices=[self.content_index()])
        def fetch_content(key):
            return content[key]

        for key in content:
            fetch_content(key)

        hits = fetch_content.indices.content.search('sky')
        self.assertEqual(3, len(hits))

        # BM25 favors documents where the term is frequent, relative to length
        self.assertEqual(
            [fetch_content.key(k) for k in ['b', 'c', 'a']],
            [hit.key for hit in hits])
        scores = [hit.score for hit in hits]
        self.assertEqual(sorted(scores), scores)

    def test_can_search_text_index_over_http(self):
        content = self.SKY_CONTENT
        port = self.serve_port + 100

        @text_conjure(self.db, index_store=self.index_store, indices=[
            self.content_index(),
            VectorIndex('lengths', dim=1, extract=lambda result, key: [len(result)]),
        ])
        def fetch_content(key):
            return content[key]

        for key in content:
            fetch_content(key)

        self.process = serve_conjure([fetch_content], port=port, n_workers=2, revive=False)
        base = f'http://localhost:{port}/functions/{fetch_content.identifier}'

        def search():
            resp = requests.get(f'{base}/indexes/content', params={'q': 'look'})
            self.assertEqual(200, resp.status_code)
            hits = resp.json()
            self.assertEqual(
                {ensure_str(fetch_content.key(k)) for k in ['b', 'c']},
                {hit['key'] for hit in hits})
            for hit in hits:
                self.assertIsInstance(hit['score'], float)

            result = requests.get(f'http://localhost:{port}{hits[0]["url"]}')
            self.assertEqual(200, result.status_code)
            self.assertIn(result.content.decode(), content.values())

        retry(search)

        resp = requests.get(f'{base}/indexes/content', params={'q': 'sky', 'limit': 2})
        self.assertEqual(2, len(resp.json()))

        resp = requests.get(f'{base}/indexes/content', params={'q': ''})
        self.assertEqual([], resp.json())

        # vector indices can't be searched with a query string
        resp = requests.get(f'{base}/indexes/lengths', params={'q': 'sky'})
        self.assertEqual(400, resp.status_code)

        resp = requests.get(f'{base}/indexes/missing', params={'q': 'sky'})
        self.assertEqual(404, resp.status_code)

        listing = requests.get(base).json()
        self.assertEqual([], listing['indexes'])
        self.assertEqual(
            {'content': 'text', 'lengths': 'vector'},
            {i['name']: i['type'] for i in listing['indices']})
        content_summary = [i for i in listing['indices'] if i['name'] == 'content'][0]
        self.assertIn('full text', content_summary['description'])
        self.assertIsNotNone(content_summary['search'])


class SqliteDecorateTests(DecorateTests):
    collection_class = SqliteCollection
    serve_port = 9998
