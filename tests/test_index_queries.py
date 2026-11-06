"""
Scalar and tag indices, and combining indices with `where` filters, using the
URL -> word count example, extended with an index over document length
"""

from collections import Counter
from unittest import TestCase
from urllib.parse import urlparse
from uuid import uuid4 as v4
import zlib

import numpy as np

from conjure import json_conjure
from conjure.index_store import SqliteIndexStore
from conjure.indexes import (
    HasTags, IndexFilter, Range, ScalarIndex, TagIndex, TextIndex, TextMatch, VectorIndex)
from conjure.storage import LmdbCollection, SqliteCollection


EMBEDDING_DIM = 16

PAGES = {
    'https://example.com/cats': 'cats purr and cats nap',                               # 5 words
    'https://example.com/dogs': 'dogs bark and dogs fetch and dogs chase cats',         # 9 words
    'https://example.org/birds': 'birds sing',                                          # 2 words
    'https://music.example.org/synths':
        'synths hum and oscillators drone and filters sweep all night',                 # 10 words
    'https://music.example.org/drums': 'drums thump and cymbals crash',                 # 5 words
}

LENGTHS = {url: len(text.split()) for url, text in PAGES.items()}


def download(url: str) -> str:
    return PAGES[url]


def word_vector(word: str) -> np.ndarray:
    rng = np.random.default_rng(zlib.crc32(word.encode()))
    return rng.normal(0, 1, EMBEDDING_DIM)


def embed(counts: dict) -> np.ndarray:
    vec = np.zeros(EMBEDDING_DIM)
    for word, count in counts.items():
        vec += count * word_vector(word)
    return vec


def make_word_count(db, index_store=None):

    @json_conjure(db, index_store=index_store, indices=[
        TextIndex('urls', extract=lambda result, url: url),
        VectorIndex('content', dim=EMBEDDING_DIM, extract=lambda result, url: embed(result)),
        ScalarIndex('length', extract=lambda result, url: sum(result.values())),
        # several values per key:  the length of each distinct word
        ScalarIndex('word_lengths', extract=lambda result, url: [len(w) for w in result]),
        TagIndex('domain', extract=lambda result, url: urlparse(url).netloc),
        TagIndex('words', extract=lambda result, url: list(result)),
    ])
    def word_count(url: str) -> dict:
        return dict(Counter(download(url).split()))

    return word_count


class QueryTestBase(TestCase):

    def setUp(self) -> None:
        self.path = f'tests/tmp/{v4().hex}.sqlite'
        self.db = SqliteCollection(self.path)
        self.word_count = make_word_count(self.db)
        for url in PAGES:
            self.word_count(url)

    def tearDown(self) -> None:
        self.db.destroy()

    def urls(self, hits):
        by_key = {self.word_count.key(url): url for url in PAGES}
        return [by_key[hit.key] for hit in hits]

    def sorted_urls(self, urls, by=LENGTHS, descending=False):
        # ties are broken by key, ascending
        keyed = sorted(urls, key=lambda u: self.word_count.key(u))
        return sorted(keyed, key=lambda u: by[u], reverse=descending)


class ScalarIndexTests(QueryTestBase):

    def test_range_is_inclusive(self):
        hits = self.word_count.indices.length.range(min=5, max=9)
        self.assertEqual(
            {'https://example.com/cats', 'https://example.com/dogs',
             'https://music.example.org/drums'},
            set(self.urls(hits)))

    def test_range_bounds_are_optional(self):
        at_least_9 = self.word_count.indices.length.range(min=9)
        self.assertEqual(
            {'https://example.com/dogs', 'https://music.example.org/synths'},
            set(self.urls(at_least_9)))

        at_most_2 = self.word_count.indices.length.range(max=2)
        self.assertEqual(['https://example.org/birds'], self.urls(at_most_2))

    def test_empty_range_returns_no_hits(self):
        self.assertEqual([], self.word_count.indices.length.range(min=100))
        self.assertEqual([], self.word_count.indices.length.range(min=9, max=5))

    def test_sorted_ascending_and_descending(self):
        ascending = self.word_count.indices.length.sorted(limit=None)
        self.assertEqual(self.sorted_urls(PAGES), self.urls(ascending))
        self.assertEqual(sorted(LENGTHS.values()), [hit.score for hit in ascending])

        descending = self.word_count.indices.length.sorted(descending=True, limit=None)
        self.assertEqual(
            sorted(LENGTHS.values(), reverse=True), [hit.score for hit in descending])
        self.assertEqual('https://music.example.org/synths', self.urls(descending)[0])

    def test_range_results_are_sorted(self):
        hits = self.word_count.indices.length.range(min=5, descending=True, limit=None)
        self.assertEqual([10, 9, 5, 5], [hit.score for hit in hits])

    def test_ties_are_broken_by_key(self):
        hits = self.word_count.indices.length.range(min=5, max=5)
        keys = [hit.key for hit in hits]
        self.assertEqual(sorted(keys), keys)
        self.assertEqual(2, len(keys))

    def test_limit_and_offset_page_through_results(self):
        everything = self.word_count.indices.length.sorted(limit=None)
        pages = [
            self.word_count.indices.length.sorted(limit=2, offset=offset)
            for offset in range(0, len(PAGES), 2)]
        self.assertEqual(everything, [hit for page in pages for hit in page])
        self.assertEqual([2, 2, 1], [len(page) for page in pages])

    def test_key_with_several_values_matches_if_any_value_is_in_range(self):
        # 'oscillators' (11 characters) is the only word longer than 7
        hits = self.word_count.indices.word_lengths.range(min=8)
        self.assertEqual(['https://music.example.org/synths'], self.urls(hits))
        self.assertEqual(11, hits[0].score)

    def test_key_with_several_values_sorts_by_its_best_value(self):
        ascending = self.word_count.indices.word_lengths.sorted(limit=None)
        descending = self.word_count.indices.word_lengths.sorted(descending=True, limit=None)

        shortest_words = {
            url: min(len(w) for w in text.split()) for url, text in PAGES.items()}
        longest_words = {
            url: max(len(w) for w in text.split()) for url, text in PAGES.items()}

        self.assertEqual(
            [shortest_words[url] for url in self.urls(ascending)],
            [hit.score for hit in ascending])
        self.assertEqual(
            [longest_words[url] for url in self.urls(descending)],
            [hit.score for hit in descending])
        self.assertEqual(sorted(shortest_words.values()), [h.score for h in ascending])
        self.assertEqual(
            sorted(longest_words.values(), reverse=True), [h.score for h in descending])

    def test_score_within_range_is_best_value_in_range(self):
        # synths' word lengths are 3, 5, 6, 7 and 11; its smallest within
        # [4, 6] is 5, and its largest is 6
        ascending = self.word_count.indices.word_lengths.range(min=4, max=6, limit=None)
        by_url = dict(zip(self.urls(ascending), [hit.score for hit in ascending]))
        self.assertEqual(5, by_url['https://music.example.org/synths'])

        descending = self.word_count.indices.word_lengths.range(
            min=4, max=6, descending=True, limit=None)
        by_url = dict(zip(self.urls(descending), [hit.score for hit in descending]))
        self.assertEqual(6, by_url['https://music.example.org/synths'])

    def test_keys_appear_once_per_query(self):
        hits = self.word_count.indices.word_lengths.sorted(limit=None)
        self.assertEqual(len(PAGES), len(hits))


class ScalarValueTests(TestCase):

    def setUp(self) -> None:
        self.db = SqliteCollection(f'tests/tmp/{v4().hex}.sqlite')

    def tearDown(self) -> None:
        self.db.destroy()

    def define(self, extract):
        @json_conjure(self.db, indices=[ScalarIndex('value', extract=extract)])
        def identity(x):
            return x
        return identity

    def test_accepts_python_numpy_and_torch_numbers(self):
        import torch

        values = [3, 2.5, np.float32(1.5), np.int64(7), torch.tensor(4.0), -1]

        # the argument is an index into values, since numpy and torch values
        # don't make useful cache keys
        f = self.define(lambda result, i: values[i])
        for i in range(len(values)):
            f(i)

        self.assertEqual(
            [-1, 1.5, 2.5, 3, 4.0, 7],
            [hit.score for hit in f.indices.value.sorted(limit=None)])

    def test_integers_keep_full_precision(self):
        big = 2 ** 60 + 1
        f = self.define(lambda result, x: x)
        f(big)
        f(big - 1)

        hits = f.indices.value.sorted(descending=True)
        self.assertEqual(big, hits[0].score)
        self.assertIsInstance(hits[0].score, int)
        self.assertEqual([f.key(big)], [h.key for h in f.indices.value.range(min=big)])

    def test_ints_and_floats_sort_together(self):
        f = self.define(lambda result, x: x)
        for x in [2, 1.5, 3, 2.25]:
            f(x)
        self.assertEqual([1.5, 2, 2.25, 3], [h.score for h in f.indices.value.sorted()])

    def test_numpy_arrays_are_several_values(self):
        f = self.define(lambda result, x: np.array([[x, x + 10], [x + 20, x + 30]]))
        f(1)
        self.assertEqual(31, f.indices.value.sorted(descending=True)[0].score)
        self.assertEqual(1, f.indices.value.sorted()[0].score)

    def test_none_produces_no_entries_but_is_processed(self):
        f = self.define(lambda result, x: None)
        f(1)
        self.assertEqual([], f.indices.value.sorted())
        self.assertIn(f.key(1), f.indices.value)

    def test_rejects_non_numbers(self):
        for bad in ['3', b'3', True, {'a': 1}]:
            f = self.define(lambda result, x, bad=bad: bad)
            self.assertRaises(TypeError, lambda: f(1))
            self.assertFalse(f.exists(1))

    def test_rejects_nan(self):
        f = self.define(lambda result, x: float('nan'))
        self.assertRaises(ValueError, lambda: f(1))

    def test_accepts_infinity(self):
        f = self.define(lambda result, x: float('inf'))
        f(1)
        self.assertEqual(float('inf'), f.indices.value.sorted()[0].score)


class TagIndexTests(QueryTestBase):

    def test_search_any(self):
        hits = self.word_count.indices.domain.search('example.com', 'example.org')
        self.assertEqual(
            {'https://example.com/cats', 'https://example.com/dogs',
             'https://example.org/birds'},
            set(self.urls(hits)))
        self.assertTrue(all(hit.score == 1 for hit in hits))

    def test_search_all(self):
        hits = self.word_count.indices.words.search('cats', 'and', match='all')
        self.assertEqual(
            {'https://example.com/cats', 'https://example.com/dogs'}, set(self.urls(hits)))

        self.assertEqual([], self.word_count.indices.words.search('cats', 'birds', match='all'))

    def test_keys_with_more_matching_tags_come_first(self):
        hits = self.word_count.indices.words.search('dogs', 'cats', 'and', limit=None)
        self.assertEqual('https://example.com/dogs', self.urls(hits)[0])
        self.assertEqual(3, hits[0].score)
        scores = [hit.score for hit in hits]
        self.assertEqual(sorted(scores, reverse=True), scores)

    def test_tags_are_exact_and_case_sensitive(self):
        self.assertEqual([], self.word_count.indices.words.search('Cats'))
        self.assertEqual([], self.word_count.indices.words.search('cat'))
        self.assertEqual([], self.word_count.indices.domain.search('example'))

    def test_repeated_tags_count_once(self):
        # 'cats' appears three times on the cats page, but is one tag
        hits = self.word_count.indices.words.search('cats', 'cats')
        self.assertTrue(all(hit.score == 1 for hit in hits))
        self.assertEqual(2, len(hits))

    def test_counts(self):
        counts = self.word_count.indices.domain.counts()
        self.assertEqual(
            {'example.com': 2, 'music.example.org': 2, 'example.org': 1}, counts)
        # most common first
        self.assertEqual(sorted(counts.values(), reverse=True), list(counts.values()))

        word_counts = self.word_count.indices.words.counts()
        self.assertEqual(4, word_counts['and'])
        self.assertEqual(2, word_counts['cats'])

    def test_limit_and_offset(self):
        everything = self.word_count.indices.words.search('and', limit=None)
        self.assertEqual(4, len(everything))
        self.assertEqual(
            everything,
            self.word_count.indices.words.search('and', limit=2)
            + self.word_count.indices.words.search('and', limit=2, offset=2))

    def test_empty_search_returns_no_hits(self):
        self.assertEqual([], self.word_count.indices.words.search())

    def test_invalid_arguments(self):
        self.assertRaises(
            ValueError, lambda: self.word_count.indices.words.search('a', match='some'))
        self.assertRaises(ValueError, lambda: self.word_count.indices.words.has())
        self.assertRaises(TypeError, lambda: self.word_count.indices.words.search(1))


class FilterTests(QueryTestBase):

    def test_text_search_filtered_by_range(self):
        hits = self.word_count.indices.urls.search(
            'example', limit=None, where=[self.word_count.indices.length.between(max=5)])
        self.assertEqual(
            {'https://example.com/cats', 'https://example.org/birds',
             'https://music.example.org/drums'},
            set(self.urls(hits)))

    def test_vector_search_filtered_by_tag(self):
        query = embed(Counter(['cats', 'purr']))

        unfiltered = self.word_count.indices.content.search(query, limit=1)
        self.assertEqual(['https://example.com/cats'], self.urls(unfiltered))

        hits = self.word_count.indices.content.search(
            query, limit=10,
            where=[self.word_count.indices.domain.has('music.example.org')])
        self.assertEqual(
            {'https://music.example.org/synths', 'https://music.example.org/drums'},
            set(self.urls(hits)))
        distances = [hit.score for hit in hits]
        self.assertEqual(sorted(distances), distances)

    def test_filtered_vector_distances_match_unfiltered(self):
        query = embed(Counter(['drums']))
        unfiltered = {
            hit.key: hit.score
            for hit in self.word_count.indices.content.search(query, limit=len(PAGES))}
        filtered = self.word_count.indices.content.search(
            query, where=[self.word_count.indices.length.between(min=5)])

        self.assertEqual(4, len(filtered))
        for hit in filtered:
            self.assertAlmostEqual(unfiltered[hit.key], hit.score, places=5)

    def test_filtered_vector_search_respects_limit(self):
        hits = self.word_count.indices.content.search(
            np.ones(EMBEDDING_DIM), limit=2,
            where=[self.word_count.indices.length.between(min=1)])
        self.assertEqual(2, len(hits))

    def test_scalar_range_filtered_by_text_and_tags(self):
        hits = self.word_count.indices.length.sorted(
            descending=True,
            where=[
                self.word_count.indices.urls.matches('example'),
                self.word_count.indices.words.has('and'),
            ])
        self.assertEqual(
            ['https://music.example.org/synths', 'https://example.com/dogs'],
            self.urls(hits)[:2])
        self.assertEqual(4, len(hits))

    def test_tag_search_filtered_by_range(self):
        hits = self.word_count.indices.words.search(
            'and', where=self.word_count.indices.length.between(min=9))
        self.assertEqual(
            {'https://example.com/dogs', 'https://music.example.org/synths'},
            set(self.urls(hits)))

    def test_tag_counts_filtered(self):
        counts = self.word_count.indices.domain.counts(
            where=[self.word_count.indices.length.between(max=5)])
        self.assertEqual(
            {'example.com': 1, 'example.org': 1, 'music.example.org': 1}, counts)

    def test_multiple_filters_must_all_pass(self):
        hits = self.word_count.indices.urls.search('example', limit=None, where=[
            self.word_count.indices.domain.has('example.com', 'music.example.org'),
            self.word_count.indices.length.between(min=5, max=5),
            self.word_count.indices.words.has('cats'),
        ])
        self.assertEqual(['https://example.com/cats'], self.urls(hits))

    def test_tag_filter_with_match_all(self):
        hits = self.word_count.indices.length.sorted(
            limit=None,
            where=[self.word_count.indices.words.has('dogs', 'cats', match='all')])
        self.assertEqual(['https://example.com/dogs'], self.urls(hits))

    def test_raw_text_filter(self):
        hits = self.word_count.indices.length.sorted(
            limit=None,
            where=[self.word_count.indices.urls.matches('synth* OR bird*', raw=True)])
        self.assertEqual(
            ['https://example.org/birds', 'https://music.example.org/synths'],
            self.urls(hits))

    def test_unbounded_range_filter_matches_every_indexed_key(self):
        hits = self.word_count.indices.urls.search(
            'https', limit=None, where=[self.word_count.indices.length.between()])
        self.assertEqual(len(PAGES), len(hits))

    def test_filter_that_matches_nothing(self):
        where = [self.word_count.indices.length.between(min=1000)]
        self.assertEqual([], self.word_count.indices.urls.search('example', where=where))
        self.assertEqual([], self.word_count.indices.content.search(np.ones(EMBEDDING_DIM), where=where))
        self.assertEqual({}, self.word_count.indices.domain.counts(where=where))

    def test_filters_are_descriptions(self):
        between = self.word_count.indices.length.between(1, 2)
        self.assertIsInstance(between, Range)
        self.assertIsInstance(between, IndexFilter)
        self.assertEqual((1, 2), (between.min, between.max))
        self.assertIsInstance(self.word_count.indices.domain.has('a'), HasTags)
        self.assertIsInstance(self.word_count.indices.urls.matches('a'), TextMatch)

    def test_invalid_filters_are_rejected(self):
        self.assertRaises(
            TypeError,
            lambda: self.word_count.indices.urls.search('example', where=['not a filter']))
        self.assertRaises(ValueError, lambda: self.word_count.indices.urls.matches('   '))

    def test_filter_from_another_store_is_rejected(self):
        other_db = SqliteCollection(f'tests/tmp/{v4().hex}.sqlite')
        try:
            other = make_word_count(other_db)
            self.assertRaises(
                ValueError,
                lambda: self.word_count.indices.urls.search(
                    'example', where=[other.indices.length.between(min=1)]))
        finally:
            other_db.destroy()


class SeparateStoresTests(TestCase):
    """
    Results and index entries live in separate stores, e.g. LMDB for results
    and SQLite for indices
    """

    def setUp(self) -> None:
        self.db = LmdbCollection(f'tests/tmp/{v4().hex}')
        self.index_store = SqliteIndexStore(f'tests/tmp/{v4().hex}.sqlite')
        self.word_count = make_word_count(self.db, index_store=self.index_store)

    def tearDown(self) -> None:
        self.db.destroy()
        self.index_store.destroy()

    def test_lmdb_results_with_sqlite_indices(self):
        for url in PAGES:
            self.word_count(url)

        hits = self.word_count.indices.length.sorted(
            descending=True, where=[self.word_count.indices.domain.has('example.com')])
        self.assertEqual(
            [self.word_count.key('https://example.com/dogs'),
             self.word_count.key('https://example.com/cats')],
            [hit.key for hit in hits])
        self.assertEqual(
            self.word_count('https://example.com/dogs'),
            self.word_count.get(hits[0].key))

    def test_lmdb_requires_an_explicit_index_store(self):
        def define():
            @json_conjure(self.db, indices=[ScalarIndex('n', extract=lambda result, x: x)])
            def identity(x):
                return x

        self.assertRaises(TypeError, define)

    def test_failed_index_write_leaves_result_to_be_indexed_on_next_hit(self):
        url = 'https://example.com/cats'
        original_write = self.index_store.write
        calls = Counter()

        def failing_write(key, entries):
            calls['write'] += 1
            if calls['write'] == 1:
                raise RuntimeError('index store unavailable')
            return original_write(key, entries)

        self.index_store.write = failing_write

        self.assertRaises(RuntimeError, lambda: self.word_count(url))
        self.assertTrue(self.word_count.exists(url))
        self.assertEqual([], self.word_count.indices.length.sorted())

        self.word_count(url)
        self.assertEqual(
            [self.word_count.key(url)],
            [hit.key for hit in self.word_count.indices.length.sorted()])

    def test_delete_removes_index_entries_before_the_result(self):
        url = 'https://example.com/cats'
        self.word_count(url)
        key = self.word_count.key(url)

        class FailingDelete(type(self.db)):
            def __delitem__(self, key):
                raise RuntimeError('storage unavailable')

        self.db.__class__ = FailingDelete
        try:
            self.assertRaises(RuntimeError, lambda: self.word_count.delete(url))
        finally:
            self.db.__class__ = LmdbCollection

        # the result survived, but its index entries are gone, so it's
        # indexed again on the next cache hit
        self.assertTrue(self.word_count.exists(url))
        self.assertNotIn(key, self.word_count.indices.length)
        self.word_count(url)
        self.assertIn(key, self.word_count.indices.length)
        self.assertEqual([key], [h.key for h in self.word_count.indices.length.sorted()])

    def test_indices_live_only_in_the_index_store(self):
        self.word_count('https://example.com/cats')
        tables = {row[0] for row in self.index_store._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue(any(t.startswith('ix_length_') for t in tables))
        self.assertTrue(any(t.startswith('ix_domain_') for t in tables))
