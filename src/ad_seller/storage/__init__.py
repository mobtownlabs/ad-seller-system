"""Storage backends for the Ad Seller System.

Supports SQLite (default) and Redis for persistence.
"""

from ad_seller.storage.base import StorageBackend
from ad_seller.storage.factory import get_storage_backend

__all__ = ["StorageBackend", "get_storage_backend"]
