"""
deps.py -- dependency FastAPI utk koneksi DB (reuse db_helper.get_conn() yang
sudah ada, SATU-SATUNYA tempat baca kredensial -- lihat db_helper.py & Invariant I6).
"""
from typing import Generator

import settings  # noqa: F401 -- import pertama, memastikan sys.path sudah benar
                  # sebelum `import db_helper` di bawah (lihat settings.py).
import psycopg2.extensions

import db_helper


def get_db() -> Generator[psycopg2.extensions.connection, None, None]:
    conn = db_helper.get_conn()
    try:
        yield conn
    finally:
        conn.close()
