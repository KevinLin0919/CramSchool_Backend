"""Rate limiting for the endpoints anyone can reach.

Everything else in this API needs a Bearer token, and those tokens carry 256
bits of entropy — guessing one is not difficult, it is impossible. So this is
not here to protect credentials. It is here because the two endpoints that
accept unauthenticated requests each do real work — a database lookup, a SHA-256,
and for the Microsoft path an outbound key fetch — and the machine running all
this sits in a cram school, serving teachers who are mid-way through a stack of
papers. The failure worth preventing is not a break-in; it is the box falling
over while somebody is grading.

In-process and in-memory on purpose. There is one container, and reaching for
Redis to count requests would add a service that can fail to a system whose
whole point is that grading keeps working when the network does not.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request, status


@dataclass
class _Window:
    """Timestamps inside the window, oldest first."""

    hits: deque[float] = field(default_factory=deque)


class RateLimiter:
    """A sliding window, counted twice: per caller and for everyone at once.

    Per-caller is the useful one — it stops a single source without touching
    anybody else. The global ceiling exists because the per-caller key comes
    from the network and can be varied at will: a caller with a thousand
    addresses is a thousand callers as far as the first counter knows. One
    limit that cannot be split is what actually bounds the work this process
    will do.
    """

    def __init__(self, *, per_key: int, overall: int, window_seconds: int,
                 max_tracked_keys: int = 10_000) -> None:
        self.per_key = per_key
        self.overall = overall
        self.window = window_seconds
        # A dict keyed by something the caller controls is itself a way to
        # exhaust memory. Past this many distinct keys the per-caller counter
        # stops admitting new ones and the global ceiling carries the load,
        # which is the degradation worth having: less precision, same bound.
        self.max_tracked_keys = max_tracked_keys

        self._keys: dict[str, _Window] = {}
        self._all = _Window()

    def _trim(self, window: _Window, now: float) -> None:
        cutoff = now - self.window
        while window.hits and window.hits[0] <= cutoff:
            window.hits.popleft()

    def _sweep(self, now: float) -> None:
        """Drop keys with nothing left in the window."""
        cutoff = now - self.window
        stale = [k for k, w in self._keys.items() if not w.hits or w.hits[-1] <= cutoff]
        for k in stale:
            del self._keys[k]

    def check(self, key: str) -> None:
        """Records one request, or raises 429 if it is one too many."""
        now = time.monotonic()

        self._trim(self._all, now)
        if len(self._all.hits) >= self.overall:
            raise self._too_many(self._all, now)

        window = self._keys.get(key)
        if window is None:
            if len(self._keys) >= self.max_tracked_keys:
                self._sweep(now)
            if len(self._keys) < self.max_tracked_keys:
                window = self._keys.setdefault(key, _Window())

        if window is not None:
            self._trim(window, now)
            if len(window.hits) >= self.per_key:
                raise self._too_many(window, now)
            window.hits.append(now)

        self._all.hits.append(now)

    def _too_many(self, window: _Window, now: float) -> HTTPException:
        # How long until the oldest hit leaves the window — a real number, so a
        # well-behaved client can wait exactly once instead of polling.
        if window.hits:
            retry = max(1, int(self.window - (now - window.hits[0])) + 1)
        else:
            retry = self.window
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="請求太頻繁，請稍後再試",
            headers={"Retry-After": str(retry)},
        )

    def reset(self) -> None:
        """For tests, which must not inherit each other's counters."""
        self._keys.clear()
        self._all = _Window()


def client_key(request: Request, trusted_proxies: tuple[str, ...]) -> str:
    """Who to count this request against.

    `X-Forwarded-For` is a header, which means it is whatever the sender says
    it is. It becomes evidence only when the machine that handed us the request
    is one we put there — a reverse proxy, or Tailscale Funnel terminating TLS
    on this host. Anything else and the peer address is the only fact available.

    The rightmost entry is the one our own proxy appended, so it is the only
    entry not under the caller's control.
    """
    peer = request.client.host if request.client else "unknown"
    if not trusted_proxies:
        return peer

    try:
        peer_ip = ip_address(peer)
    except ValueError:
        return peer

    if not any(peer_ip in ip_network(net, strict=False) for net in trusted_proxies):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return peer
    return forwarded.split(",")[-1].strip() or peer
