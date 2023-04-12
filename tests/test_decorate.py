import json
from multiprocessing import Process
from time import sleep
from typing import Union
from unittest import TestCase, skip
import requests
from random import random

from traitlets import Callable

from conjure.decorate import Conjure, WriteNotification, json_conjure
from conjure.identifier import LiteralFunctionIdentifier, LiteralParamsIdentifier, ParamsHash
from conjure.serialize import JSONDeserializer, JSONSerializer
from conjure.serve import serve_conjure
from conjure.storage import LmdbCollection
from uuid import uuid4 as v4


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

    def setUp(self) -> None:
        self.process: Union[Process, None] = None
        self.path = f'/tmp/{v4().hex}'
        self.db = LmdbCollection(self.path)

    def tearDown(self) -> None:
        self.db.destroy()

        if self.process is not None and self.process.is_alive():
            self.process.join(5)
            self.process.terminate()

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
            [make_bigger], port=9999, n_workers=1, revive=False)

        def get_keys_over_http():
            resp = requests.get(f'http://localhost:9999/functions/{make_bigger.identifier}', verify=False)
            keys = resp.json()['keys']
            self.assertEqual(2, len(keys))

        retry(get_keys_over_http)

        meta = make_bigger.meta({'a': 10, 'b': 3})
        resp = requests.get(
            f'http://localhost:9999/functions/{make_bigger.identifier}/{meta.key.decode()}', verify=False)
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
