import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor


@contextmanager
def cursor():
    connection = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=8)
    try:
        with connection:
            with connection.cursor(cursor_factory=RealDictCursor) as result:
                yield result
    finally:
        connection.close()