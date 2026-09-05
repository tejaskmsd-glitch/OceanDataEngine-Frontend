# Known / Intentional Limitations (Phase 0)

1. **Authentication/Live Sources**: Some live source connectors require authentication (e.g. IMD, MOSDAC) which are not yet fully configured with real credentials.
2. **Geospatial Processing**: PostGIS is documented but the database currently uses `TEXT` (GeoJSON) for geometry columns as an interim solution.
3. **Queue Scalability**: While NATS JetStream provides durable queues, if NATS is unavailable the system falls back to an in-memory queue.
4. **Airflow Local Executor**: Airflow is currently configured with the LocalExecutor, meaning tasks run sequentially on the scheduler node rather than a scalable Celery cluster.
