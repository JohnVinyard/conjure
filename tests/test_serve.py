"""
HTTP behavior the dashboard depends on, exercised in-process with falcon's
test client, rather than by running a gunicorn server
"""

from unittest import TestCase
from uuid import uuid4 as v4
import warnings

import falcon.testing

from conjure.decorate import json_conjure
from conjure.serve import MutliFunctionApplication
from conjure.storage import LmdbCollection, SqliteCollection, ensure_str


class ServeTests(TestCase):
    collection_class = LmdbCollection

    def setUp(self) -> None:
        self.db = self.collection_class(f'tests/tmp/{v4().hex}')

        @json_conjure(self.db)
        def double(x):
            return x * 2

        @json_conjure(self.db)
        def triple(x):
            return x * 3

        self.double = double
        self.triple = triple

        with warnings.catch_warnings():
            # falcon.API is deprecated in favor of falcon.App
            warnings.simplefilter('ignore')
            app = MutliFunctionApplication([double, triple], port=8888)
        self.client = falcon.testing.TestClient(app)

    def tearDown(self) -> None:
        self.db.destroy()

    def get(self, path, **params):
        return self.client.simulate_get(path, params=params or None)

    # feed ####################################################################

    def test_feed_is_empty_before_function_is_called(self):
        resp = self.get(f'/feed/{self.double.identifier}')
        self.assertEqual(200, resp.status_code)
        self.assertEqual([], resp.json)

    def test_feed_with_empty_offset_is_empty_before_function_is_called(self):
        # the dashboard may send an empty offset, meaning "from the start"
        resp = self.client.simulate_get(
            f'/feed/{self.double.identifier}', query_string='offset=')
        self.assertEqual(200, resp.status_code)
        self.assertEqual([], resp.json)

    def test_feed_lists_results_after_function_is_called(self):
        self.double(1)
        self.double(2)

        resp = self.get(f'/feed/{self.double.identifier}')
        self.assertEqual(200, resp.status_code)
        self.assertEqual(
            [ensure_str(self.double.key(1)), ensure_str(self.double.key(2))],
            [item['key'] for item in resp.json])

    def test_feed_with_empty_offset_lists_all_results(self):
        self.double(1)
        resp = self.client.simulate_get(
            f'/feed/{self.double.identifier}', query_string='offset=')
        self.assertEqual(1, len(resp.json))

    def test_feed_respects_offset(self):
        for x in range(3):
            self.double(x)
        items = self.get(f'/feed/{self.double.identifier}').json

        resp = self.get(f'/feed/{self.double.identifier}', offset=items[1]['timestamp'])
        self.assertEqual(200, resp.status_code)
        # the offset itself is included, and the dashboard filters it out
        self.assertEqual(items[1:], resp.json)

    def test_feeds_are_separate_per_function(self):
        self.triple(1)
        self.assertEqual([], self.get(f'/feed/{self.double.identifier}').json)
        self.assertEqual(1, len(self.get(f'/feed/{self.triple.identifier}').json))

    def test_feed_for_unknown_function_is_not_found(self):
        self.assertEqual(404, self.get('/feed/not-a-function').status_code)

    def test_feed_with_malformed_offset_is_a_bad_request(self):
        resp = self.get(f'/feed/{self.double.identifier}', offset='undefined')
        self.assertEqual(400, resp.status_code)

    def test_feed_with_another_functions_offset_is_a_bad_request(self):
        self.triple(1)
        offset = self.get(f'/feed/{self.triple.identifier}').json[0]['timestamp']
        resp = self.get(f'/feed/{self.double.identifier}', offset=offset)
        self.assertEqual(400, resp.status_code)

    # results #################################################################

    def test_missing_key_is_not_found(self):
        resp = self.get(f'/functions/{self.double.identifier}/{ensure_str(self.double.key(1))}')
        self.assertEqual(404, resp.status_code)

    def test_undefined_key_is_not_found(self):
        # what the dashboard would request after reading an empty feed
        resp = self.get(f'/functions/{self.double.identifier}/undefined')
        self.assertEqual(404, resp.status_code)

    def test_key_for_unknown_function_is_not_found(self):
        self.double(1)
        resp = self.get(f'/functions/not-a-function/{ensure_str(self.double.key(1))}')
        self.assertEqual(404, resp.status_code)

    def test_existing_key_is_found(self):
        self.double(21)
        resp = self.get(f'/functions/{self.double.identifier}/{ensure_str(self.double.key(21))}')
        self.assertEqual(200, resp.status_code)
        self.assertEqual('application/json', resp.headers['content-type'])
        self.assertEqual(42, resp.json)

    def test_deleted_key_is_not_found(self):
        self.double(1)
        self.double.delete(1)
        resp = self.get(f'/functions/{self.double.identifier}/{ensure_str(self.double.key(1))}')
        self.assertEqual(404, resp.status_code)

    # listings ################################################################

    def test_function_list_includes_functions_without_results(self):
        self.triple(1)

        resp = self.get('/functions')
        self.assertEqual(200, resp.status_code)
        by_id = {f['id']: f for f in resp.json}

        empty = by_id[self.double.identifier]['meta']
        self.assertIsNone(empty['key'])
        self.assertIsNone(empty['public_uri'])
        # the dashboard needs these to watch for the first result
        self.assertEqual(f'/feed/{self.double.identifier}', empty['feed_uri'])
        self.assertEqual(self.double.identifier, empty['func_identifier'])

        populated = by_id[self.triple.identifier]['meta']
        self.assertEqual(ensure_str(self.triple.key(1)), populated['key'])
        self.assertTrue(populated['public_uri'].endswith(populated['key']))

    def test_function_list_shows_most_recent_result(self):
        self.double(1)
        self.double(2)
        by_id = {f['id']: f for f in self.get('/functions').json}
        self.assertEqual(
            ensure_str(self.double.key(2)), by_id[self.double.identifier]['meta']['key'])

    def test_function_detail_before_function_is_called(self):
        resp = self.get(f'/functions/{self.double.identifier}')
        self.assertEqual(200, resp.status_code)
        self.assertEqual([], resp.json['keys'])

    def test_unknown_function_detail_is_not_found(self):
        self.assertEqual(404, self.get('/functions/not-a-function').status_code)

    # most recent result ######################################################

    def test_most_recent_key_and_meta_are_none_before_function_is_called(self):
        self.assertIsNone(self.double.most_recent_key())
        self.assertIsNone(self.double.most_recent_meta())

    def test_most_recent_key_and_meta(self):
        self.double(1)
        self.double(2)
        self.assertEqual(self.double.key(2), self.double.most_recent_key())
        self.assertEqual(self.double.key(2), self.double.most_recent_meta().key)


class SqliteServeTests(ServeTests):
    collection_class = SqliteCollection


class LatestResultTests(TestCase):
    """
    /functions/{identifier}/latest is a shortcut for reading a function's
    feed, and then requesting the result for its last key
    """
    collection_class = LmdbCollection

    def setUp(self) -> None:
        self.db = self.collection_class(f'tests/tmp/{v4().hex}')

        @json_conjure(self.db)
        def double(x):
            return x * 2

        self.double = double
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            app = MutliFunctionApplication([double], port=8888)
        self.client = falcon.testing.TestClient(app)
        self.latest = f'/functions/{double.identifier}/latest'

    def tearDown(self) -> None:
        self.db.destroy()

    def result_for(self, x):
        return self.client.simulate_get(
            f'/functions/{self.double.identifier}/{ensure_str(self.double.key(x))}')

    def test_not_found_before_function_is_called(self):
        self.assertEqual(404, self.client.simulate_get(self.latest).status_code)
        self.assertEqual(404, self.client.simulate_head(self.latest).status_code)

    def test_not_found_for_unknown_function(self):
        resp = self.client.simulate_get('/functions/not-a-function/latest')
        self.assertEqual(404, resp.status_code)

    def test_returns_same_response_as_requesting_latest_key(self):
        self.double(1)
        self.double(2)

        latest = self.client.simulate_get(self.latest)
        direct = self.result_for(2)

        self.assertEqual(200, latest.status_code)
        self.assertEqual(direct.content, latest.content)
        self.assertEqual(direct.headers['content-type'], latest.headers['content-type'])
        self.assertEqual(direct.headers['content-length'], latest.headers['content-length'])
        self.assertEqual(4, latest.json)

    def test_reports_key_that_was_served(self):
        self.double(1)
        resp = self.client.simulate_get(self.latest)
        self.assertEqual(ensure_str(self.double.key(1)), resp.headers['x-conjure-key'])
        self.assertEqual(f'"{ensure_str(self.double.key(1))}"', resp.headers['etag'])
        self.assertEqual('no-cache', resp.headers['cache-control'])

    def test_follows_newer_results(self):
        self.double(1)
        self.assertEqual(2, self.client.simulate_get(self.latest).json)

        self.double(5)
        resp = self.client.simulate_get(self.latest)
        self.assertEqual(10, resp.json)
        self.assertEqual(ensure_str(self.double.key(5)), resp.headers['x-conjure-key'])

    def test_recomputed_result_becomes_latest(self):
        self.double(1)
        self.double(2)
        self.double.prefer_cache = False
        self.double(1)
        self.assertEqual(2, self.client.simulate_get(self.latest).json)

    def test_head_returns_key_without_body(self):
        self.double(3)
        resp = self.client.simulate_head(self.latest)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(ensure_str(self.double.key(3)), resp.headers['x-conjure-key'])
        self.assertEqual(b'', resp.content)

    def test_conditional_get_is_not_modified_until_a_newer_result(self):
        self.double(1)
        etag = self.client.simulate_get(self.latest).headers['etag']

        unchanged = self.client.simulate_get(self.latest, headers={'If-None-Match': etag})
        self.assertEqual(304, unchanged.status_code)
        self.assertEqual(b'', unchanged.content)

        self.double(2)
        changed = self.client.simulate_get(self.latest, headers={'If-None-Match': etag})
        self.assertEqual(200, changed.status_code)
        self.assertEqual(4, changed.json)

    def test_falls_back_to_previous_result_when_latest_is_deleted(self):
        self.double(1)
        self.double(2)
        self.double.delete(2)

        resp = self.client.simulate_get(self.latest)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(2, resp.json)
        self.assertEqual(self.double.key(1), self.double.most_recent_key())

        # the listing also uses the most recent result that still exists
        listing = self.client.simulate_get('/functions')
        self.assertEqual(200, listing.status_code)
        self.assertEqual(ensure_str(self.double.key(1)), listing.json[0]['meta']['key'])

    def test_not_found_when_every_result_is_deleted(self):
        self.double(1)
        self.double.delete(1)
        self.assertEqual(404, self.client.simulate_get(self.latest).status_code)

    def test_literal_latest_does_not_shadow_other_keys(self):
        self.double(1)
        self.assertEqual(200, self.result_for(1).status_code)
        missing = self.client.simulate_get(f'/functions/{self.double.identifier}/latest-ish')
        self.assertEqual(404, missing.status_code)

    def test_function_list_includes_latest_uri(self):
        listing = self.client.simulate_get('/functions').json
        self.assertEqual(self.latest, listing[0]['meta']['latest_uri'])

        self.double(1)
        listing = self.client.simulate_get('/functions').json
        self.assertEqual(self.latest, listing[0]['meta']['latest_uri'])


class SqliteLatestResultTests(LatestResultTests):
    collection_class = SqliteCollection


class RecentKeysTests(TestCase):
    """
    The function detail page lists a function's most recent keys, newest first
    """
    collection_class = LmdbCollection

    def setUp(self) -> None:
        self.db = self.collection_class(f'tests/tmp/{v4().hex}')

        @json_conjure(self.db)
        def double(x):
            return x * 2

        self.double = double
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            app = MutliFunctionApplication([double], port=8888)
        self.client = falcon.testing.TestClient(app)

    def tearDown(self) -> None:
        self.db.destroy()

    def keys_for(self, *xs):
        return [self.double.key(x) for x in xs]

    def detail_keys(self):
        resp = self.client.simulate_get(f'/functions/{self.double.identifier}')
        self.assertEqual(200, resp.status_code)
        return resp.json['keys']

    def test_empty_before_function_is_called(self):
        self.assertEqual([], self.double.recent_keys())
        self.assertEqual([], self.detail_keys())

    def test_newest_first(self):
        # call in an order unrelated to the keys' hash order
        for x in [3, 1, 4, 5, 9, 2, 6]:
            self.double(x)

        expected = self.keys_for(6, 2, 9, 5, 4, 1, 3)
        self.assertEqual(expected, self.double.recent_keys())
        self.assertEqual([ensure_str(k) for k in expected], self.detail_keys())

    def test_detail_page_shows_ten_most_recent(self):
        for x in range(15):
            self.double(x)

        expected = [ensure_str(k) for k in self.keys_for(*range(14, 4, -1))]
        self.assertEqual(expected, self.detail_keys())

    def test_limit(self):
        for x in range(5):
            self.double(x)
        self.assertEqual(self.keys_for(4, 3), self.double.recent_keys(limit=2))
        self.assertEqual(self.keys_for(4, 3, 2, 1, 0), self.double.recent_keys(limit=100))

    def test_recomputed_result_appears_once_at_its_newest_position(self):
        self.double(1)
        self.double(2)
        self.double(3)
        self.double.prefer_cache = False
        self.double(1)

        self.assertEqual(self.keys_for(1, 3, 2), self.double.recent_keys())

    def test_cache_hits_do_not_change_recency(self):
        self.double(1)
        self.double(2)
        self.double(1)
        self.assertEqual(self.keys_for(2, 1), self.double.recent_keys())

    def test_deleted_results_are_skipped(self):
        for x in range(4):
            self.double(x)
        self.double.delete(3)
        self.double.delete(1)

        self.assertEqual(self.keys_for(2, 0), self.double.recent_keys())

    def test_limit_counts_only_existing_results(self):
        for x in range(4):
            self.double(x)
        self.double.delete(3)
        self.assertEqual(self.keys_for(2, 1), self.double.recent_keys(limit=2))

    def test_most_recent_key_is_first_recent_key(self):
        for x in range(3):
            self.double(x)
        self.assertEqual(self.double.recent_keys()[0], self.double.most_recent_key())


class SqliteRecentKeysTests(RecentKeysTests):
    collection_class = SqliteCollection
