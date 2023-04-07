import json
from unittest import TestCase

from conjure.decorate import json_conjure
from conjure.storage import LmdbCollection
from uuid import uuid4 as v4


class DecorateTests(TestCase):

    def setUp(self) -> None:
        self.path = f'/tmp/{v4().hex}'
        self.db = LmdbCollection(self.path)

    def tearDown(self) -> None:
        self.db.destroy()

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
        self.assertEqual(len(json.dumps(initial).encode()), meta.content_length)
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
