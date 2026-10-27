"""Database bootstrap: connect to PostgreSQL and create any missing (empty) tables."""
import logging
import time

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

log = logging.getLogger('hms.db')

# Arbitrary constant: serialises concurrent workers creating tables at startup
_LOCK_KEY = 7272701


def init_database(flask_app, retries=4, delay=3):
    """Create every table that does not exist yet. Never inserts any data.

    - Safe to run on every start (existing tables / data are untouched).
    - Uses a transaction-scoped advisory lock so several gunicorn workers
      starting together do not race (also works behind Neon's PgBouncer).
    - Retries a few times because a suspended Neon compute needs a moment to wake up.
    """
    from app import db
    from app import models  # noqa: F401  (registers all models on db.metadata)

    last_error = None
    with flask_app.app_context():
        for attempt in range(1, retries + 1):
            try:
                with db.engine.begin() as conn:
                    if conn.dialect.name == 'postgresql':
                        conn.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': _LOCK_KEY})
                    before = set(inspect(conn).get_table_names())
                    db.metadata.create_all(bind=conn)
                    after = set(inspect(conn).get_table_names())
                created = sorted(after - before)
                if created:
                    log.info('Created %d empty table(s): %s', len(created), ', '.join(created))
                else:
                    log.info('Database ready - all %d tables already exist.', len(after))
                return
            except OperationalError as exc:
                last_error = exc
                log.warning('Database connection attempt %d/%d failed: %s',
                            attempt, retries, str(exc).splitlines()[0])
                time.sleep(delay)
    raise RuntimeError(
        "Could not connect to the PostgreSQL database. Check DATA_BASE_URL in your .env file "
        "and your internet connection.\nLast error: " + str(last_error)
    )
