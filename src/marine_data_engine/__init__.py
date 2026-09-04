"""Marine Data Engine — source-agnostic marine data layer backend.

This package implements the backend data layer described in the project
requirements: ingestion, immutable raw storage, canonical normalization,
quality control, freshness/provenance tracking, and a query-only API.

The package is intentionally AI-agnostic: no LLM, agent framework, or vector
database is imported anywhere in the runtime path.
"""

__version__ = "0.1.0"
