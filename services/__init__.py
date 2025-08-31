"""Service layer package.

Exports stable entry points for embeddings, jobs, and search adapter.
This file also makes `services` an explicit Python package for clearer imports.
"""

from .search_adapter import SearchService  # re-export

__all__ = ["SearchService"]

