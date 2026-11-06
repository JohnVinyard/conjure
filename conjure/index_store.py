"""
Storage for index entries, independent of where results themselves are
stored.  See `conjure.indexes` for index definitions.
"""

import os
from os import PathLike
import sqlite3
from typing import Dict, List, Sequence, Tuple

import numpy as np

from conjure.indexes import (
    ConjureIndex, HasTags, IndexFilter, IndexHit, Range, ScalarIndex, TagIndex,
    TextIndex, TextMatch, VectorIndex)
from conjure.sqlite import SqliteConnections


Entries = Sequence[Tuple[ConjureIndex, Sequence]]


class IndexStore(object):
    """
    The interface between index definitions and wherever index entries live.

    Each index processes a key exactly once (until the key is deleted, or the
    key's index entries are replaced), and stores have to remember which keys
    an index has processed, even when it produced no values for them.
    """

    def attach(self, index: ConjureIndex):
        """
        Prepare to store entries for index, e.g. by creating tables
        """
        raise NotImplementedError()

    def unprocessed(self, key: bytes, indices: Sequence[ConjureIndex]) -> List[ConjureIndex]:
        """
        The indices, of those given, that haven't processed key
        """
        return [index for index in indices if not self.is_processed(index, key)]

    def is_processed(self, index: ConjureIndex, key: bytes) -> bool:
        raise NotImplementedError()

    def write(self, key: bytes, entries: Entries):
        """
        Replace key's entries in each index with the given values, and mark
        key as processed by each index
        """
        raise NotImplementedError()

    def delete(self, key: bytes, indices: Sequence[ConjureIndex]):
        """
        Remove all of key's entries from each index
        """
        raise NotImplementedError()

    def keys(self, index: ConjureIndex) -> List[bytes]:
        raise NotImplementedError()

    def text_search(
            self,
            index: TextIndex,
            expression: str,
            limit: int,
            offset: int,
            where: List[IndexFilter]) -> List[IndexHit]:
        raise NotImplementedError()

    def vector_search(
            self,
            index: VectorIndex,
            vector: np.ndarray,
            limit: int,
            where: List[IndexFilter]) -> List[IndexHit]:
        raise NotImplementedError()

    def scalar_range(
            self,
            index: ScalarIndex,
            min,
            max,
            descending: bool,
            limit: int,
            offset: int,
            where: List[IndexFilter]) -> List[IndexHit]:
        raise NotImplementedError()

    def tag_search(
            self,
            index: TagIndex,
            tags: List[str],
            match: str,
            limit: int,
            offset: int,
            where: List[IndexFilter]) -> List[IndexHit]:
        raise NotImplementedError()

    def tag_counts(self, index: TagIndex, where: List[IndexFilter]) -> Dict[str, int]:
        raise NotImplementedError()


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _limit(limit) -> int:
    # SQLite treats a negative limit as "no limit"
    return -1 if limit is None else int(limit)


class _Tables(object):
    """
    Table names for one index.  Every index has:

      - a keys table, mapping entry row ids to result keys, so that a key can
        have any number of entries, which can be found and removed together
      - a processed table, recording which keys the index has processed
      - a values table, whose structure depends on the type of index, and
        whose row ids match the keys table
    """

    def __init__(self, index: ConjureIndex):
        super().__init__()
        self.keys = _quote(f'{index.id}_keys')
        self.processed = _quote(f'{index.id}_processed')
        self.values = _quote(index.id)
        self.key_index = _quote(f'{index.id}_keys_key')
        self.value_index = _quote(f'{index.id}_value')


class SqliteIndexStore(IndexStore):
    """
    Index entries stored in a SQLite file, which may be the same file used by
    a `SqliteCollection`, or a separate one, e.g. alongside an `LmdbCollection`
    or `S3Collection`.

    Like `SqliteCollection`, this is safe to use from multiple processes,
    including ones forked after it was created.

      - text indices use FTS5
      - vector indices use the sqlite-vec extension
      - scalar and tag indices use ordinary tables with B-tree indices
    """

    def __init__(self, path: PathLike, timeout: float = 30):
        super().__init__()
        self.path = os.fspath(path)
        self._connections = SqliteConnections(self.path, timeout=timeout)

    @property
    def _connection(self) -> sqlite3.Connection:
        return self._connections.connection

    def close(self):
        self._connections.close()

    def destroy(self):
        self._connections.destroy()

    # writing #################################################################

    def attach(self, index: ConjureIndex):
        if index.kind == 'vector':
            self._connections.enable_vector_extension()

        t = _Tables(index)
        with self._connections.transaction() as txn:
            txn.execute(f'''
                CREATE TABLE IF NOT EXISTS {t.keys} (
                    rowid INTEGER PRIMARY KEY,
                    key BLOB NOT NULL
                )
            ''')
            txn.execute(f'CREATE INDEX IF NOT EXISTS {t.key_index} ON {t.keys} (key)')
            txn.execute(f'''
                CREATE TABLE IF NOT EXISTS {t.processed} (
                    key BLOB PRIMARY KEY
                )
            ''')
            self._create_values_table(txn, index, t)

    def _create_values_table(self, conn: sqlite3.Connection, index: ConjureIndex, t: _Tables):
        if isinstance(index, TextIndex):
            tokenizer = index.tokenizer.replace("'", "''")
            conn.execute(f'''
                CREATE VIRTUAL TABLE IF NOT EXISTS {t.values}
                USING fts5(text, tokenize = '{tokenizer}')
            ''')
        elif isinstance(index, VectorIndex):
            conn.execute(f'''
                CREATE VIRTUAL TABLE IF NOT EXISTS {t.values}
                USING vec0(embedding float[{index.dim}] distance_metric={index.metric})
            ''')
        elif isinstance(index, ScalarIndex):
            # the key is repeated here, so that range queries need no join
            conn.execute(f'''
                CREATE TABLE IF NOT EXISTS {t.values} (
                    rowid INTEGER PRIMARY KEY,
                    key BLOB NOT NULL,
                    value NUMERIC NOT NULL
                )
            ''')
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS {t.value_index} ON {t.values} (value, key)')
        elif isinstance(index, TagIndex):
            conn.execute(f'''
                CREATE TABLE IF NOT EXISTS {t.values} (
                    rowid INTEGER PRIMARY KEY,
                    key BLOB NOT NULL,
                    tag TEXT NOT NULL
                )
            ''')
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS {t.value_index} ON {t.values} (tag, key)')
        else:
            raise TypeError(f'SqliteIndexStore does not support {type(index).__name__}')

    def _insert_value(self, conn: sqlite3.Connection, index: ConjureIndex, t: _Tables, rowid, key, value):
        if isinstance(index, TextIndex):
            conn.execute(
                f'INSERT INTO {t.values} (rowid, text) VALUES (?, ?)', (rowid, value))
        elif isinstance(index, VectorIndex):
            conn.execute(
                f'INSERT INTO {t.values} (rowid, embedding) VALUES (?, ?)',
                (rowid, np.asarray(value, dtype=np.float32).tobytes()))
        elif isinstance(index, ScalarIndex):
            conn.execute(
                f'INSERT INTO {t.values} (rowid, key, value) VALUES (?, ?, ?)',
                (rowid, key, value))
        elif isinstance(index, TagIndex):
            conn.execute(
                f'INSERT INTO {t.values} (rowid, key, tag) VALUES (?, ?, ?)',
                (rowid, key, value))

    def _delete(self, conn: sqlite3.Connection, index: ConjureIndex, key: bytes):
        t = _Tables(index)
        rowids = [row[0] for row in conn.execute(
            f'SELECT rowid FROM {t.keys} WHERE key = ?', (key,))]
        for rowid in rowids:
            conn.execute(f'DELETE FROM {t.values} WHERE rowid = ?', (rowid,))
        conn.execute(f'DELETE FROM {t.keys} WHERE key = ?', (key,))
        conn.execute(f'DELETE FROM {t.processed} WHERE key = ?', (key,))

    def write(self, key: bytes, entries: Entries):
        with self._connections.transaction() as txn:
            for index, values in entries:
                t = _Tables(index)
                self._delete(txn, index, key)
                for value in values:
                    rowid = txn.execute(
                        f'INSERT INTO {t.keys} (key) VALUES (?)', (key,)).lastrowid
                    self._insert_value(txn, index, t, rowid, key, value)
                txn.execute(f'INSERT INTO {t.processed} (key) VALUES (?)', (key,))

    def delete(self, key: bytes, indices: Sequence[ConjureIndex]):
        with self._connections.transaction() as txn:
            for index in indices:
                self._delete(txn, index, key)

    # reading #################################################################

    def is_processed(self, index: ConjureIndex, key: bytes) -> bool:
        t = _Tables(index)
        row = self._connection.execute(
            f'SELECT 1 FROM {t.processed} WHERE key = ?', (key,)).fetchone()
        return row is not None

    def keys(self, index: ConjureIndex) -> List[bytes]:
        t = _Tables(index)
        return [bytes(row[0]) for row in self._connection.execute(
            f'SELECT DISTINCT key FROM {t.keys} ORDER BY key')]

    def _filter_subquery(self, f: IndexFilter) -> Tuple[str, list]:
        """
        A query selecting the keys that pass filter f
        """
        t = _Tables(f.index)

        if isinstance(f, TextMatch):
            return (
                f'SELECT k.key FROM {t.values} '
                f'JOIN {t.keys} AS k ON k.rowid = {t.values}.rowid '
                f'WHERE {t.values} MATCH ?',
                [f.expression])

        if isinstance(f, Range):
            conditions, params = [], []
            if f.min is not None:
                conditions.append('value >= ?')
                params.append(f.min)
            if f.max is not None:
                conditions.append('value <= ?')
                params.append(f.max)
            where = f' WHERE {" AND ".join(conditions)}' if conditions else ''
            return f'SELECT key FROM {t.values}{where}', params

        if isinstance(f, HasTags):
            placeholders = ', '.join('?' for _ in f.tags)
            query = f'SELECT key FROM {t.values} WHERE tag IN ({placeholders})'
            params = list(f.tags)
            if f.match == 'all':
                query += ' GROUP BY key HAVING count(DISTINCT tag) = ?'
                params.append(len(f.tags))
            return query, params

        raise TypeError(f'SqliteIndexStore does not support {type(f).__name__} filters')

    def _where(self, column: str, filters: List[IndexFilter]) -> Tuple[str, list]:
        """
        SQL conditions (each prefixed with AND) restricting column to keys
        that pass every filter
        """
        sql, params = '', []
        for f in filters:
            subquery, subparams = self._filter_subquery(f)
            sql += f' AND {column} IN ({subquery})'
            params.extend(subparams)
        return sql, params

    def text_search(self, index, expression, limit, offset, where) -> List[IndexHit]:
        t = _Tables(index)
        filter_sql, filter_params = self._where('k.key', where)
        rows = self._connection.execute(
            f'''
            SELECT k.key, min({t.values}.rank) AS score
            FROM {t.values}
            JOIN {t.keys} AS k ON k.rowid = {t.values}.rowid
            WHERE {t.values} MATCH ?{filter_sql}
            GROUP BY k.key
            ORDER BY score, k.key
            LIMIT ? OFFSET ?
            ''',
            [expression, *filter_params, _limit(limit), offset]).fetchall()
        return [IndexHit(bytes(key), score) for key, score in rows]

    # sqlite-vec's upper limit on the number of neighbors per query
    _MAX_K = 4096

    def vector_search(self, index, vector, limit, where) -> List[IndexHit]:
        if where:
            return self._filtered_vector_search(index, vector, limit, where)

        t = _Tables(index)
        query = np.asarray(vector, dtype=np.float32).tobytes()
        conn = self._connection
        n_entries = conn.execute(f'SELECT count(*) FROM {t.keys}').fetchone()[0]

        # several entries may belong to the same key, so keep asking for more
        # neighbors until there are `limit` distinct keys, or no entries remain
        k = min(limit, n_entries, self._MAX_K)
        while True:
            if k == 0:
                return []

            rows = conn.execute(
                f'''
                SELECT k.key, v.distance
                FROM (
                    SELECT rowid, distance FROM {t.values}
                    WHERE embedding MATCH ? AND k = ?
                ) AS v
                JOIN {t.keys} AS k ON k.rowid = v.rowid
                ORDER BY v.distance
                ''',
                (query, k)).fetchall()

            hits = {}
            for key, distance in rows:
                key = bytes(key)
                if key not in hits:
                    hits[key] = IndexHit(key, distance)

            if len(hits) >= limit or k >= min(n_entries, self._MAX_K):
                return list(hits.values())[:limit]

            k = min(k * 2, n_entries, self._MAX_K)

    def _filtered_vector_search(self, index, vector, limit, where) -> List[IndexHit]:
        """
        Filter first, then compute exact distances to the remaining entries,
        which always finds the nearest `limit` keys that pass the filters
        """
        t = _Tables(index)
        filter_sql, filter_params = self._where('k.key', where)
        query = np.asarray(vector, dtype=np.float32).tobytes()

        # CROSS JOIN makes the (filtered) keys table the outer loop, so that
        # only matching entries' vectors are read
        rows = self._connection.execute(
            f'''
            SELECT k.key, min(vec_distance_{index.metric}(v.embedding, ?)) AS distance
            FROM {t.keys} AS k
            CROSS JOIN {t.values} AS v ON v.rowid = k.rowid
            WHERE 1{filter_sql}
            GROUP BY k.key
            ORDER BY distance, k.key
            LIMIT ?
            ''',
            [query, *filter_params, _limit(limit)]).fetchall()
        return [IndexHit(bytes(key), distance) for key, distance in rows]

    def scalar_range(self, index, min, max, descending, limit, offset, where) -> List[IndexHit]:
        t = _Tables(index)
        conditions, params = [], []
        if min is not None:
            conditions.append('value >= ?')
            params.append(min)
        if max is not None:
            conditions.append('value <= ?')
            params.append(max)
        filter_sql, filter_params = self._where('key', where)

        # a key with several values is sorted by its best one
        aggregate, direction = ('max', 'DESC') if descending else ('min', 'ASC')
        rows = self._connection.execute(
            f'''
            SELECT key, {aggregate}(value) AS score
            FROM {t.values}
            WHERE 1{''.join(' AND ' + c for c in conditions)}{filter_sql}
            GROUP BY key
            ORDER BY score {direction}, key
            LIMIT ? OFFSET ?
            ''',
            [*params, *filter_params, _limit(limit), offset]).fetchall()
        return [IndexHit(bytes(key), score) for key, score in rows]

    def tag_search(self, index, tags, match, limit, offset, where) -> List[IndexHit]:
        t = _Tables(index)
        placeholders = ', '.join('?' for _ in tags)
        filter_sql, filter_params = self._where('key', where)
        having, having_params = '', []
        if match == 'all':
            having, having_params = 'HAVING score = ?', [len(tags)]

        rows = self._connection.execute(
            f'''
            SELECT key, count(DISTINCT tag) AS score
            FROM {t.values}
            WHERE tag IN ({placeholders}){filter_sql}
            GROUP BY key
            {having}
            ORDER BY score DESC, key
            LIMIT ? OFFSET ?
            ''',
            [*tags, *filter_params, *having_params, _limit(limit), offset]).fetchall()
        return [IndexHit(bytes(key), score) for key, score in rows]

    def tag_counts(self, index, where) -> Dict[str, int]:
        t = _Tables(index)
        filter_sql, filter_params = self._where('key', where)
        rows = self._connection.execute(
            f'''
            SELECT tag, count(DISTINCT key) AS n
            FROM {t.values}
            WHERE 1{filter_sql}
            GROUP BY tag
            ORDER BY n DESC, tag
            ''',
            filter_params).fetchall()
        return {tag: n for tag, n in rows}
