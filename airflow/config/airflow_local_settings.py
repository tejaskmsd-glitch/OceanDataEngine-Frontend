"""Airflow local settings for the Marine Data Layer.

Kept minimal: Airflow only ORCHESTRATES/SCHEDULES source polling and hands work
to the Python worker queues (NATS) / API. Heavy scientific decoding must NOT run
inside Airflow tasks (prompt §4: heavy processing runs in separate workers).
"""

# Default pool sizing so scheduled polls don't overwhelm upstream sources.
# (Airflow reads this module if mounted at /opt/airflow/config.)
