import json
import multiprocessing
from collections import Counter
from unittest import TestCase
from uuid import uuid4 as v4
import zlib

import numpy as np

from conjure import json_conjure
from conjure.indexes import IndexHit, TextIndex, VectorIndex
from conjure.index_store import SqliteIndexStore
from conjure.identifier import FunctionNameIdentifier, LiteralFunctionIdentifier
from conjure.storage import LmdbCollection, LocalCollectionWithBackup, SqliteCollection


EMBEDDING_DIM = 32

# stands in for the internet, so that "downloading" a URL is deterministic
PAGES = {
    'https://example.com/cats': 'cats purr and cats nap and cats chase mice',
    'https://example.com/dogs': 'dogs bark and dogs fetch and dogs chase cats',
    'https://music.example.org/synths': 'synths hum and oscillators drone and filters sweep',
    'https://music.example.org/drums': 'drums thump and cymbals crash and snares crack',
}


def download(url: str) -> str:
    return PAGES[url]


def word_vector(word: str) -> np.ndarray:
    # a fixed random vector per word, stable across processes
    rng = np.random.default_rng(zlib.crc32(word.encode()))
    return rng.normal(0, 1, EMBEDDING_DIM)


def embed(counts: dict) -> np.ndarray:
    """
    A bag-of-words embedding, so that pages sharing words are near each other
    """
    vec = np.zeros(EMBEDDING_DIM)
    for word, count in counts.items():
        vec += count * word_vector(word)
    return vec


def make_word_count(db, extract_calls: list = None, index_store=None):
    """
    The example from the design discussion:  a function that downloads a URL
    and counts its words, with a text index over the URL, and a vector index
    over an embedding of the page's content
    """

    def extract_url(result, url):
        if extract_calls is not None:
            extract_calls.append(url)
        return url

    @json_conjure(db, index_store=index_store, indices=[
        TextIndex('urls', extract=extract_url),
        VectorIndex('content', dim=EMBEDDING_DIM, extract=lambda result, url: embed(result)),
    ])
    def word_count(url: str) -> dict:
        return dict(Counter(download(url).split()))

    return word_count


def _compute_in_subprocess(path: str, urls):
    db = SqliteCollection(path)
    word_count = make_word_count(db)
    for url in urls:
        word_count(url)
    db.close()


class IndicesTests(TestCase):

    def setUp(self) -> None:
        self.path = f'tests/tmp/{v4().hex}.sqlite'
        self.db = SqliteCollection(self.path)
        self.extract_calls = []
        self.word_count = make_word_count(self.db, self.extract_calls)

    def tearDown(self) -> None:
        self.db.destroy()

    def compute_all(self):
        for url in PAGES:
            self.word_count(url)

    def key_for(self, url: str) -> bytes:
        return self.word_count.key(url)

    def urls_for(self, hits):
        by_key = {self.key_for(url): url for url in PAGES}
        return [by_key[hit.key] for hit in hits]

    # access ##################################################################

    def test_indices_are_accessible_as_attributes_and_items(self):
        self.assertIsInstance(self.word_count.indices.urls, TextIndex)
        self.assertIs(self.word_count.indices.urls, self.word_count.indices['urls'])
        self.assertIn('content', self.word_count.indices)
        self.assertEqual(2, len(self.word_count.indices))
        self.assertEqual(
            {'urls', 'content'}, {index.name for index in self.word_count.indices})

    def test_unknown_index_raises_attribute_error(self):
        self.assertRaises(AttributeError, lambda: self.word_count.indices.missing)

    def test_function_without_indices_has_empty_indices(self):
        @json_conjure(self.db)
        def no_indices(x):
            return x

        self.assertEqual(0, len(no_indices.indices))
        self.assertFalse(no_indices.indices)

    # text index ##############################################################

    def test_can_search_urls(self):
        self.compute_all()

        hits = self.word_count.indices.urls.search('music')
        self.assertEqual(
            {'https://music.example.org/synths', 'https://music.example.org/drums'},
            set(self.urls_for(hits)))

    def test_text_search_requires_all_terms(self):
        self.compute_all()

        hits = self.word_count.indices.urls.search('music drums')
        self.assertEqual(['https://music.example.org/drums'], self.urls_for(hits))

    def test_text_search_handles_punctuation(self):
        self.compute_all()

        hits = self.word_count.indices.urls.search('example.com/cats')
        self.assertEqual(['https://example.com/cats'], self.urls_for(hits))

    def test_text_search_with_no_matches_returns_empty_list(self):
        self.compute_all()
        self.assertEqual([], self.word_count.indices.urls.search('giraffes'))
        self.assertEqual([], self.word_count.indices.urls.search('   '))

    def test_text_search_supports_raw_fts_expressions(self):
        self.compute_all()

        hits = self.word_count.indices.urls.match('synth*')
        self.assertEqual(['https://music.example.org/synths'], self.urls_for(hits))

        hits = self.word_count.indices.urls.match('cats OR dogs')
        self.assertEqual(
            {'https://example.com/cats', 'https://example.com/dogs'},
            set(self.urls_for(hits)))

    def test_text_search_respects_limit(self):
        self.compute_all()
        hits = self.word_count.indices.urls.search('https', limit=3)
        self.assertEqual(3, len(hits))

    def test_hits_can_be_resolved_to_results(self):
        self.compute_all()

        hit = self.word_count.indices.urls.search('drums')[0]
        self.assertIsInstance(hit, IndexHit)
        self.assertEqual(
            self.word_count('https://music.example.org/drums'),
            self.word_count.get(hit.key))

    def test_trigram_tokenizer_supports_substring_search(self):
        @json_conjure(self.db, indices=[
            TextIndex('urls', extract=lambda result, url: url, tokenizer='trigram')])
        def page_length(url: str) -> int:
            return len(download(url))

        for url in PAGES:
            page_length(url)

        # 'xample' isn't a token, but is a substring
        hits = page_length.indices.urls.search('xample.org')
        self.assertEqual(2, len(hits))

    # vector index ############################################################

    def test_can_search_content_by_embedding(self):
        self.compute_all()

        query = embed(Counter('cats chase mice'.split()))
        hits = self.word_count.indices.content.search(query, limit=4)

        self.assertEqual(4, len(hits))
        self.assertEqual('https://example.com/cats', self.urls_for(hits)[0])
        distances = [hit.score for hit in hits]
        self.assertEqual(sorted(distances), distances)

    def test_identical_content_has_zero_distance(self):
        self.compute_all()

        result = self.word_count('https://music.example.org/drums')
        hits = self.word_count.indices.content.search(embed(result), limit=1)

        self.assertEqual(['https://music.example.org/drums'], self.urls_for(hits))
        self.assertAlmostEqual(0, hits[0].score, places=5)

    def test_vector_search_on_empty_index_returns_empty_list(self):
        self.assertEqual(
            [], self.word_count.indices.content.search(np.ones(EMBEDDING_DIM)))

    def test_vector_search_accepts_torch_tensors(self):
        import torch
        self.compute_all()

        query = torch.from_numpy(embed(Counter(['drums'])))
        hits = self.word_count.indices.content.search(query, limit=1)
        self.assertEqual(['https://music.example.org/drums'], self.urls_for(hits))

    def test_vector_search_rejects_wrong_dimension(self):
        self.assertRaises(
            ValueError,
            lambda: self.word_count.indices.content.search(np.ones(EMBEDDING_DIM + 1)))

    def test_wrong_dimension_from_extractor_stores_nothing(self):
        @json_conjure(self.db, indices=[
            VectorIndex('content', dim=EMBEDDING_DIM, extract=lambda result, x: np.ones(3))])
        def bad_embedding(x):
            return x

        self.assertRaises(ValueError, lambda: bad_embedding(1))
        self.assertFalse(bad_embedding.exists(1))

    def test_key_with_several_vectors_is_returned_once(self):
        @json_conjure(self.db, indices=[
            VectorIndex(
                'words',
                dim=EMBEDDING_DIM,
                # one vector per distinct word
                extract=lambda result, url: np.stack([word_vector(w) for w in result]))
        ])
        def word_count_per_word(url: str) -> dict:
            return dict(Counter(download(url).split()))

        for url in PAGES:
            word_count_per_word(url)

        hits = word_count_per_word.indices.words.search(word_vector('cats'), limit=4)

        keys = [hit.key for hit in hits]
        self.assertEqual(len(set(keys)), len(keys))
        self.assertEqual(4, len(keys))
        # both pages mentioning cats contain the exact vector
        self.assertAlmostEqual(0, hits[0].score, places=5)
        self.assertAlmostEqual(0, hits[1].score, places=5)
        self.assertEqual(
            {word_count_per_word.key('https://example.com/cats'),
             word_count_per_word.key('https://example.com/dogs')},
            set(keys[:2]))

    def test_supports_l2_metric(self):
        @json_conjure(self.db, indices=[
            VectorIndex('vec', dim=2, metric='l2', extract=lambda result, x, y: [x, y])])
        def point(x, y):
            return [x, y]

        point(0, 0)
        point(3, 4)
        hits = point.indices.vec.search([3, 4], limit=2)
        self.assertEqual([point.key(3, 4), point.key(0, 0)], [h.key for h in hits])
        self.assertAlmostEqual(5, hits[1].score, places=5)

    # extraction ##############################################################

    def test_extractor_receives_result_args_and_kwargs(self):
        received = []

        def extract(result, a, b=None):
            received.append((result, a, b))
            return f'{a} {b}'

        @json_conjure(self.db, indices=[TextIndex('ab', extract=extract)])
        def add(a, b=None):
            return a + b

        add(1, b=2)
        self.assertEqual([(3, 1, 2)], received)
        self.assertEqual([add.key(1, b=2)], [h.key for h in add.indices.ab.search('1 2')])

    def test_extractor_may_return_none_or_several_values(self):
        @json_conjure(self.db, indices=[
            TextIndex('words', extract=lambda result, text: text.split() or None)])
        def length(text):
            return len(text)

        length('')
        length('alpha beta gamma')

        self.assertEqual(1, len(length.indices.words))
        self.assertEqual(
            [length.key('alpha beta gamma')],
            [h.key for h in length.indices.words.search('beta')])

    def test_extraction_error_stores_nothing(self):
        def fail(result, x):
            raise RuntimeError('extraction failed')

        @json_conjure(self.db, indices=[TextIndex('failing', extract=fail)])
        def identity(x):
            return x

        self.assertRaises(RuntimeError, lambda: identity(1))
        self.assertFalse(identity.exists(1))

    def test_cache_hits_do_not_extract_again(self):
        url = 'https://example.com/cats'
        self.word_count(url)
        self.word_count(url)
        self.word_count(url)

        self.assertEqual([url], self.extract_calls)
        self.assertEqual(1, len(self.word_count.indices.urls.search('cats')))

    # lifecycle ###############################################################

    def test_recomputing_replaces_index_entries(self):
        values = {'text': 'first'}

        @json_conjure(self.db, indices=[
            TextIndex('text', extract=lambda result: result)])
        def current_text():
            return values['text']

        current_text.prefer_cache = False

        current_text()
        values['text'] = 'second'
        current_text()

        self.assertEqual([], current_text.indices.text.search('first'))
        self.assertEqual(1, len(current_text.indices.text.search('second')))
        self.assertEqual(1, len(current_text.indices.text))

    def test_delete_removes_index_entries(self):
        self.compute_all()
        url = 'https://example.com/cats'

        self.word_count.delete(url)

        self.assertFalse(self.word_count.exists(url))
        self.assertEqual([], self.word_count.indices.urls.search('cats'))
        self.assertNotIn(
            self.key_for(url),
            [hit.key for hit in self.word_count.indices.content.search(np.ones(EMBEDDING_DIM), limit=10)])
        self.assertEqual(len(PAGES) - 1, len(self.word_count.indices.content))

    def test_indices_persist_after_reopening(self):
        self.compute_all()
        self.db.close()

        db = SqliteCollection(self.path)
        word_count = make_word_count(db)
        self.assertEqual(2, len(word_count.indices.urls.search('music')))
        self.assertEqual(
            len(PAGES), len(word_count.indices.content.search(np.ones(EMBEDDING_DIM))))
        db.close()

    def test_functions_sharing_storage_have_separate_indices(self):
        @json_conjure(self.db, indices=[
            TextIndex('urls', extract=lambda result, url: url)])
        def page_length(url: str) -> int:
            return len(download(url))

        self.word_count('https://example.com/cats')
        page_length('https://example.com/dogs')

        self.assertEqual(
            [self.key_for('https://example.com/cats')],
            [h.key for h in self.word_count.indices.urls.search('example')])
        self.assertEqual(
            [page_length.key('https://example.com/dogs')],
            [h.key for h in page_length.indices.urls.search('example')])

    # configuration ###########################################################

    def test_duplicate_index_names_are_rejected(self):
        def define():
            @json_conjure(self.db, indices=[
                TextIndex('same', extract=lambda result, x: str(x)),
                TextIndex('same', extract=lambda result, x: str(x)),
            ])
            def f(x):
                return x

        self.assertRaises(ValueError, define)

    def test_index_cannot_be_shared_between_functions(self):
        index = TextIndex('shared', extract=lambda result, x: str(x))

        @json_conjure(self.db, indices=[index])
        def f(x):
            return x

        def define_second():
            @json_conjure(self.db, indices=[index])
            def g(x):
                return x + 1

        self.assertRaises(ValueError, define_second)

    def test_index_names_must_be_identifiers(self):
        self.assertRaises(ValueError, lambda: TextIndex('1abc', extract=None))
        self.assertRaises(ValueError, lambda: TextIndex('a-b', extract=None))
        self.assertRaises(ValueError, lambda: TextIndex('a b', extract=None))

    def test_invalid_vector_configuration_is_rejected(self):
        self.assertRaises(ValueError, lambda: VectorIndex('v', dim=0, extract=None))
        self.assertRaises(ValueError, lambda: VectorIndex('v', dim=4, extract=None, metric='dot'))

    def test_storage_without_index_support_is_rejected(self):
        db = LmdbCollection(f'tests/tmp/{v4().hex}')
        try:
            def define():
                @json_conjure(db, indices=[TextIndex('t', extract=lambda result, x: str(x))])
                def f(x):
                    return x

            self.assertRaises(TypeError, define)
        finally:
            db.destroy()

    def test_works_with_local_collection_with_backup(self):
        path = f'tests/tmp/{v4().hex}.sqlite'
        backup = SqliteCollection(f'tests/tmp/{v4().hex}.sqlite')
        index_store = SqliteIndexStore(f'tests/tmp/{v4().hex}.sqlite')
        db = LocalCollectionWithBackup(
            path,
            remote_bucket=None,
            local_backup=backup,
            local_collection_class=SqliteCollection)
        try:
            word_count = make_word_count(db, index_store=index_store)
            for url in PAGES:
                word_count(url)

            self.assertEqual(2, len(word_count.indices.urls.search('music')))
            self.assertIn(word_count.key('https://example.com/cats'), backup)

            word_count.delete('https://example.com/cats')
            self.assertEqual([], word_count.indices.urls.search('cats'))
            self.assertNotIn(word_count.key('https://example.com/cats'), backup)
        finally:
            db.destroy()
            backup.destroy()
            index_store.destroy()

    # multiple processes ######################################################

    def test_processes_can_write_to_the_same_indices(self):
        urls = list(PAGES)
        ctx = multiprocessing.get_context('spawn')
        processes = [
            ctx.Process(target=_compute_in_subprocess, args=(self.path, [url]))
            for url in urls]
        for p in processes:
            p.start()
        for p in processes:
            p.join(60)
            self.assertEqual(0, p.exitcode)

        self.assertEqual(2, len(self.word_count.indices.urls.search('music')))
        self.assertEqual(
            len(PAGES), len(self.word_count.indices.content.search(np.ones(EMBEDDING_DIM))))
        # everything was computed by the subprocesses
        self.assertEqual([], self.extract_calls)


def _word_count(url: str) -> dict:
    return dict(Counter(download(url).split()))


class IndexOnCacheHitTests(TestCase):
    """
    Results cached before an index existed are indexed on their next cache
    hit, since that's when the function's arguments are available again
    """

    def setUp(self) -> None:
        self.path = f'tests/tmp/{v4().hex}.sqlite'
        self.db = SqliteCollection(self.path)
        self.calls = Counter()

    def tearDown(self) -> None:
        self.db.destroy()

    def counting(self, name, extract):
        def wrapped(*args, **kwargs):
            self.calls[name] += 1
            return extract(*args, **kwargs)
        return wrapped

    def define(self, *indices, func=_word_count):
        # decorating the same function object yields the same identifier and
        # keys, which simulates redeploying a function with new indices
        return json_conjure(self.db, indices=list(indices))(func)

    def url_index(self, name='urls'):
        return TextIndex(name, extract=self.counting(name, lambda result, url: url))

    def test_results_cached_before_index_existed_are_indexed_on_cache_hit(self):
        unindexed = self.define()
        for url in PAGES:
            unindexed(url)

        word_count = self.define(self.url_index())
        self.assertEqual([], word_count.indices.urls.search('music'))
        self.assertNotIn(word_count.key('https://music.example.org/drums'), word_count.indices.urls)

        word_count('https://music.example.org/drums')

        self.assertIn(word_count.key('https://music.example.org/drums'), word_count.indices.urls)
        self.assertEqual(
            [word_count.key('https://music.example.org/drums')],
            [hit.key for hit in word_count.indices.urls.search('music')])

    def test_backfill_does_not_recompute_the_result(self):
        computed = Counter()

        def tracked_word_count(url: str) -> dict:
            computed[url] += 1
            return _word_count(url)

        self.define(func=tracked_word_count)('https://example.com/cats')
        word_count = self.define(self.url_index(), func=tracked_word_count)
        word_count('https://example.com/cats')

        self.assertEqual(1, computed['https://example.com/cats'])
        self.assertEqual(1, len(word_count.indices.urls.search('cats')))

    def test_backfill_happens_only_once(self):
        self.define()('https://example.com/cats')

        word_count = self.define(self.url_index())
        for _ in range(5):
            word_count('https://example.com/cats')

        self.assertEqual(1, self.calls['urls'])
        self.assertEqual(1, len(word_count.indices.urls.search('cats')))

    def test_index_with_no_values_for_a_key_is_not_retried(self):
        self.define()('https://example.com/cats')

        word_count = self.define(
            TextIndex('nothing', extract=self.counting('nothing', lambda result, url: None)))
        for _ in range(3):
            word_count('https://example.com/cats')

        self.assertEqual(1, self.calls['nothing'])
        self.assertIn(word_count.key('https://example.com/cats'), word_count.indices.nothing)
        self.assertEqual(0, len(word_count.indices.nothing))

    def test_only_new_indices_are_backfilled(self):
        first = self.define(self.url_index('urls'))
        first('https://example.com/cats')
        self.assertEqual(1, self.calls['urls'])

        second = self.define(
            self.url_index('urls'),
            VectorIndex(
                'content',
                dim=EMBEDDING_DIM,
                extract=self.counting('content', lambda result, url: embed(result))))
        second('https://example.com/cats')

        self.assertEqual(1, self.calls['urls'])
        self.assertEqual(1, self.calls['content'])
        self.assertEqual(1, len(second.indices.content.search(np.ones(EMBEDDING_DIM))))

    def test_freshly_computed_results_are_not_extracted_twice(self):
        word_count = self.define(self.url_index())
        word_count('https://example.com/cats')
        word_count('https://example.com/cats')
        self.assertEqual(1, self.calls['urls'])

    def test_failed_backfill_raises_keeps_value_and_retries_next_time(self):
        self.define()('https://example.com/cats')
        attempts = Counter()

        def flaky(result, url):
            attempts['n'] += 1
            if attempts['n'] == 1:
                raise RuntimeError('extraction failed')
            return url

        word_count = self.define(TextIndex('urls', extract=flaky))

        self.assertRaises(RuntimeError, lambda: word_count('https://example.com/cats'))
        self.assertTrue(word_count.exists('https://example.com/cats'))
        self.assertNotIn(word_count.key('https://example.com/cats'), word_count.indices.urls)

        word_count('https://example.com/cats')
        self.assertEqual(2, attempts['n'])
        self.assertEqual(1, len(word_count.indices.urls.search('cats')))

    def test_key_error_in_extractor_is_not_treated_as_cache_miss(self):
        computed = Counter()

        def tracked_word_count(url: str) -> dict:
            computed[url] += 1
            return _word_count(url)

        self.define(func=tracked_word_count)('https://example.com/cats')
        word_count = self.define(
            TextIndex('bad', extract=lambda result, url: result['not a word']),
            func=tracked_word_count)

        self.assertRaises(KeyError, lambda: word_count('https://example.com/cats'))
        self.assertEqual(1, computed['https://example.com/cats'])

    def test_deleted_results_are_no_longer_marked_as_indexed(self):
        word_count = self.define(self.url_index())
        word_count('https://example.com/cats')
        key = word_count.key('https://example.com/cats')
        self.assertIn(key, word_count.indices.urls)

        word_count.delete('https://example.com/cats')
        self.assertNotIn(key, word_count.indices.urls)

        # recomputing indexes it again
        word_count('https://example.com/cats')
        self.assertEqual(2, self.calls['urls'])
        self.assertIn(key, word_count.indices.urls)

    def test_results_read_through_from_backup_are_indexed(self):
        backup = SqliteCollection(f'tests/tmp/{v4().hex}.sqlite')
        index_store = SqliteIndexStore(f'tests/tmp/{v4().hex}.sqlite')
        db = LocalCollectionWithBackup(
            f'tests/tmp/{v4().hex}.sqlite',
            remote_bucket=None,
            local_backup=backup,
            local_collection_class=SqliteCollection)
        try:
            computed = Counter()

            def tracked_word_count(url: str) -> dict:
                computed[url] += 1
                return _word_count(url)

            word_count = json_conjure(
                db, indices=[self.url_index()], index_store=index_store)(tracked_word_count)
            word_count('https://example.com/cats')

            # simulate a fresh machine:  the value exists only in the backup
            key = word_count.key('https://example.com/cats')
            word_count.delete('https://example.com/cats')
            backup.put(key, json.dumps(_word_count('https://example.com/cats')).encode(), None)
            self.assertEqual([], word_count.indices.urls.search('cats'))

            word_count('https://example.com/cats')

            self.assertEqual(1, computed['https://example.com/cats'])
            self.assertEqual([key], [hit.key for hit in word_count.indices.urls.search('cats')])
        finally:
            db.destroy()
            backup.destroy()
            index_store.destroy()


class IndexIdentityTests(TestCase):
    """
    By default, an index's identity includes a hash of its extractor's code,
    so changing the extractor starts a fresh index.  This is configurable via
    the same identifier strategies used for conjured functions.  Structural
    configuration (e.g. vector dimension) is always part of an index's identity.
    """

    def setUp(self) -> None:
        self.path = f'tests/tmp/{v4().hex}.sqlite'
        self.db = SqliteCollection(self.path)
        self.url = 'https://example.com/cats'

    def tearDown(self) -> None:
        self.db.destroy()

    def define(self, index):
        return json_conjure(self.db, indices=[index])(_word_count)

    def test_changing_extractor_code_starts_a_fresh_index(self):
        before = self.define(TextIndex('urls', extract=lambda result, url: url))
        before(self.url)
        self.assertEqual(1, len(before.indices.urls.search('cats')))

        after = self.define(
            TextIndex('urls', extract=lambda result, url: url + ' changed'))
        self.assertEqual([], after.indices.urls.search('cats'))
        self.assertNotIn(after.key(self.url), after.indices.urls)

        # populated on the next cache hit, using the new extractor
        after(self.url)
        self.assertEqual(1, len(after.indices.urls.search('cats changed')))

        # the old index is left untouched
        self.assertEqual([], before.indices.urls.search('changed'))
        self.assertEqual(1, len(before.indices.urls.search('cats')))

    def test_identical_extractor_code_reuses_the_index(self):
        def define():
            return self.define(TextIndex('urls', extract=lambda result, url: url))

        define()(self.url)
        self.assertEqual(1, len(define().indices.urls.search('cats')))

    def test_name_identifier_keeps_index_when_extractor_code_changes(self):
        def extract_url(result, url):
            return url

        before = self.define(
            TextIndex('urls', extract=extract_url, identifier=FunctionNameIdentifier()))
        before(self.url)

        def extract_url(result, url):
            return 'something else entirely'

        after = self.define(
            TextIndex('urls', extract=extract_url, identifier=FunctionNameIdentifier()))

        self.assertIn(after.key(self.url), after.indices.urls)
        self.assertEqual(1, len(after.indices.urls.search('cats')))

        # already indexed, so the new extractor isn't run on a cache hit
        after(self.url)
        self.assertEqual([], after.indices.urls.search('something'))

    def test_literal_identifier_controls_index_version(self):
        def define(version, extract):
            return self.define(TextIndex(
                'urls', extract=extract, identifier=LiteralFunctionIdentifier(version)))

        define('v1', lambda result, url: url)(self.url)

        same_version = define('v1', lambda result, url: url + ' changed')
        self.assertEqual(1, len(same_version.indices.urls.search('cats')))
        self.assertEqual([], same_version.indices.urls.search('changed'))

        new_version = define('v2', lambda result, url: url + ' changed')
        self.assertEqual([], new_version.indices.urls.search('cats'))
        new_version(self.url)
        self.assertEqual(1, len(new_version.indices.urls.search('changed')))

    def test_changing_vector_dimension_always_starts_a_fresh_index(self):
        def define(dim):
            return self.define(VectorIndex(
                'content',
                dim=dim,
                extract=lambda result, url: np.ones(len(url)),
                identifier=LiteralFunctionIdentifier('fixed')))

        # the extractor's output depends on the url, so dim must match it
        dim = len(self.url)
        define(dim)(self.url)

        # same identifier, different dimension:  doesn't reuse the old table
        resized = self.define(VectorIndex(
            'content',
            dim=dim * 2,
            extract=lambda result, url: np.ones(len(url) * 2),
            identifier=LiteralFunctionIdentifier('fixed')))
        self.assertEqual([], resized.indices.content.search(np.ones(dim * 2)))

        resized(self.url)
        self.assertEqual(1, len(resized.indices.content.search(np.ones(dim * 2))))

        # the original is still intact
        self.assertEqual(1, len(define(dim).indices.content.search(np.ones(dim))))

    def test_changing_metric_or_tokenizer_starts_a_fresh_index(self):
        literal = LiteralFunctionIdentifier('fixed')

        self.define(TextIndex(
            'urls', extract=lambda result, url: url, identifier=literal))(self.url)
        trigram = self.define(TextIndex(
            'urls', extract=lambda result, url: url, tokenizer='trigram', identifier=literal))
        self.assertNotIn(trigram.key(self.url), trigram.indices.urls)

        cosine = self.define(VectorIndex(
            'v', dim=2, extract=lambda result, url: [1, 2], identifier=literal))
        cosine(self.url)
        l2 = self.define(VectorIndex(
            'v', dim=2, extract=lambda result, url: [1, 2], metric='l2', identifier=literal))
        self.assertNotIn(l2.key(self.url), l2.indices.v)

    def test_extractor_without_code_needs_another_identifier(self):
        from functools import partial

        def extract(result, url, suffix):
            return url + suffix

        self.assertRaises(
            TypeError,
            lambda: self.define(TextIndex('urls', extract=partial(extract, suffix='!'))))

        word_count = self.define(TextIndex(
            'urls',
            extract=partial(extract, suffix=' partial'),
            identifier=LiteralFunctionIdentifier('v1')))
        word_count(self.url)
        self.assertEqual(1, len(word_count.indices.urls.search('partial')))

    def test_extractor_identifier_is_exposed(self):
        index = TextIndex(
            'urls', extract=lambda result, url: url, identifier=LiteralFunctionIdentifier('v7'))
        self.assertEqual(b'v7', index.extractor_identifier)
