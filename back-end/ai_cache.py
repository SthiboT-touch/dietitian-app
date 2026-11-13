"""Bounded process-local AI response cache; never writes prompts or replies to disk."""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
from threading import RLock
from time import monotonic

import config


class ResponseCache:
    def __init__(self, clock=monotonic):
        self._entries = OrderedDict()
        self._lock = RLock()
        self._clock = clock

    def key(self, payload):
        return sha256(json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()

    def get(self, key):
        if config.AI_CACHE_TTL_SECONDS <= 0 or config.AI_CACHE_MAX_ENTRIES <= 0:
            return None
        with self._lock:
            self._prune()
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return deepcopy(entry[1])

    def _prune(self):
        now = self._clock()
        for key in list(self._entries):
            if self._entries[key][0] <= now:
                del self._entries[key]

    def put(self, key, value):
        if config.AI_CACHE_TTL_SECONDS <= 0 or config.AI_CACHE_MAX_ENTRIES <= 0:
            return
        # Bound memory even if an upstream model ignores its output limit.
        if len(json.dumps(value, default=str).encode()) > 64000:
            return
        with self._lock:
            self._prune()
            self._entries[key] = (self._clock() + config.AI_CACHE_TTL_SECONDS, deepcopy(value))
            self._entries.move_to_end(key)
            while len(self._entries) > config.AI_CACHE_MAX_ENTRIES:
                self._entries.popitem(last=False)

    def clear(self):
        with self._lock:
            self._entries.clear()


response_cache = ResponseCache()
