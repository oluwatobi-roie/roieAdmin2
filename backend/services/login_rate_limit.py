"""Bounded, persistent login budgets shared by workers on the same host.

Uses a separate locked JSON file on the existing data volume, never Traccar SQL.
The socket peer is trusted; unverified forwarding headers never select a bucket.
"""
import hashlib
import math
import time
from services.finance import Ledger


class LoginRateLimiter:
    def __init__(self, directory, window=300, ip_limit=60, email_limit=10,
                 total_limit=200, max_keys=2048, clock=time.time):
        self.store = Ledger(directory)
        self.window, self.ip_limit, self.email_limit = window, ip_limit, email_limit
        self.total_limit, self.max_keys, self.clock = total_limit, max_keys, clock

    def consume(self, peer, email):
        current = self.clock()
        def digest(value):
            return hashlib.sha256(value.encode("utf-8")).hexdigest()
        identities = [("ip:" + digest(peer), self.ip_limit),
                      ("email:" + digest(email.strip().casefold()), self.email_limit),
                      ("all", self.total_limit)]
        budgets = [(key, limit, self.window) for key, limit in identities]
        budgets += [("long:" + key, limit * 4, self.window * 12) for key, limit in identities]
        with self.store.transaction(write=True) as data:
            buckets = {key: value for key, value in data.get("login_buckets", {}).items() if value["reset"] > current}
            data["login_buckets"] = buckets
            blocked = [buckets[key]["reset"] for key, limit, _ in budgets
                       if key in buckets and buckets[key]["count"] >= limit]
            if blocked:
                return max(1, math.ceil(max(blocked) - current))
            needed = sum(key not in buckets for key, _, _ in budgets)
            if len(buckets) + needed > self.max_keys:
                return max(1, math.ceil(min(item["reset"] for item in buckets.values()) - current))
            for key, _, duration in budgets:
                bucket = buckets.setdefault(key, {"reset": current + duration, "count": 0})
                bucket["count"] += 1
        return 0
