from functools import lru_cache

from .config import get_settings
from .storage import BlobStore


@lru_cache
def get_store() -> BlobStore:
    return BlobStore(get_settings())
