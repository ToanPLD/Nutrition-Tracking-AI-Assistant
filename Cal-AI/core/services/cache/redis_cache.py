import redis
import json
import zlib
from config.settings import settings


class RedisCache:
    COMPRESSED_PREFIX = b"zlib:"

    def __init__(self):
        self.client = None
        self.memory = {}

        if not getattr(settings, "REDIS_ENABLED", False):
            print("[INFO] Redis disabled, using in-memory cache.")
            return

        print("Connecting Redis...")
        print("HOST:", settings.REDIS_HOST)
        print("PORT:", settings.REDIS_PORT)

        try:
            self.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            self.client.ping()
            print("[INFO] Redis connected")
        except Exception as e:
            print("[WARN] Redis connection FAILED, using in-memory cache:", e)
            self.client = None

    def _encode(self, value):
        if isinstance(value, bytes):
            raw = value
        elif isinstance(value, str):
            raw = value.encode("utf-8")
        else:
            raw = json.dumps(value, ensure_ascii=False).encode("utf-8")

        if len(raw) > settings.REDIS_CACHE_MAX_VALUE_BYTES:
            return None

        if len(raw) >= settings.REDIS_CACHE_COMPRESS_MIN_BYTES:
            return self.COMPRESSED_PREFIX + zlib.compress(raw, level=6)

        return raw

    def _decode(self, value):
        if isinstance(value, bytes) and value.startswith(self.COMPRESSED_PREFIX):
            return zlib.decompress(value[len(self.COMPRESSED_PREFIX):])
        return value

    def get(self, key):
        try:
            if self.client is None:
                return self._decode(self.memory.get(key))
            return self._decode(self.client.get(key))
        except Exception:
            return None

    def set(self, key, value, ttl=None):
        try:
            ttl = ttl or settings.CACHE_TTL
            value = self._encode(value)
            if value is None:
                return
            if self.client is None:
                self.memory[key] = value
                return
            self.client.setex(key, ttl, value)
        except Exception:
            pass

    def ttl(self, key):
        try:
            if self.client is None:
                return None
            return self.client.ttl(key)
        except Exception:
            return None
