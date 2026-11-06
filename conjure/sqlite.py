"""
Connection management shared by SQLite-backed value storage and index storage
"""

from contextlib import contextmanager
import os
import sqlite3
import threading
from typing import Callable, Iterator


ConnectHook = Callable[[sqlite3.Connection], None]


def load_vector_extension(conn: sqlite3.Connection):
    try:
        import sqlite_vec
    except ImportError:
        raise ImportError(
            'VectorIndex requires the sqlite-vec package:  pip install sqlite-vec')

    if not hasattr(conn, 'enable_load_extension'):
        raise RuntimeError(
            "This Python's sqlite3 module was built without support for loading "
            'extensions, which VectorIndex requires.  Use a Python build that '
            'supports it, or install pysqlite3.')

    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """
    A transaction that takes the write lock up front, so that SQLite's busy
    timeout applies, rather than failing when a read lock is later upgraded
    to a write lock.  Requires a connection with isolation_level=None.
    """
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    else:
        conn.execute('COMMIT')


class SqliteConnections(object):
    """
    Lazily opened connections to a single SQLite file, in WAL mode.

    Connections must never cross a fork, and sqlite3 connections shouldn't be
    shared between threads, so there's one per (process, thread).  This makes
    an instance created before a fork (e.g. by a gunicorn master process)
    safe to use in the child processes.

    Note that WAL mode does not work on network filesystems.
    """

    def __init__(self, path: str, timeout: float = 30, on_connect: ConnectHook = None):
        super().__init__()
        self.path = path
        self.timeout = timeout
        self.on_connect = on_connect

        self._thread_local = threading.local()
        self._lock = threading.Lock()
        self._connections = []
        self._vector_extension = False

        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def enable_vector_extension(self):
        """
        Load the sqlite-vec extension into every connection, from now on
        """
        self._vector_extension = True
        # fail early, rather than on first use
        self.connection

    @property
    def connection(self) -> sqlite3.Connection:
        pid = os.getpid()
        local = self._thread_local
        conn = getattr(local, 'conn', None)

        if conn is None or local.pid != pid:
            conn = self._connect()
            local.conn = conn
            local.pid = pid
            local.vector_extension = False
            with self._lock:
                self._connections.append((pid, conn))

        if self._vector_extension and not local.vector_extension:
            load_vector_extension(conn)
            local.vector_extension = True

        return conn

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None means that transactions are managed explicitly
        conn = sqlite3.connect(
            self.path,
            timeout=self.timeout,
            isolation_level=None,
            check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        if self.on_connect is not None:
            self.on_connect(conn)
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        A write transaction on this process's (and thread's) connection.
        Everything executed within it is committed atomically, or not at all.
        """
        with write_transaction(self.connection) as conn:
            yield conn

    def close(self):
        """
        Close every connection opened in the current process
        """
        pid = os.getpid()
        with self._lock:
            remaining = []
            for conn_pid, conn in self._connections:
                if conn_pid == pid:
                    conn.close()
                else:
                    remaining.append((conn_pid, conn))
            self._connections = remaining
        self._thread_local = threading.local()

    def destroy(self):
        """
        Close all connections, and delete the database file
        """
        self.close()
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(f'{self.path}{suffix}')
            except FileNotFoundError:
                pass
