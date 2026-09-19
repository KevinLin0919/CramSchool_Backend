"""A ceiling on how much body this process will read.

FastAPI reads the whole request body before dependencies run — `request.form()`
and `request.json()` both happen in `routing.py` ahead of `solve_dependencies`.
So `current_teacher` on the upload endpoint runs *after* the upload is already
buffered, and the 25 MB check in `BlobStore.put` runs after that again. An
unauthenticated POST to `/api/v1/images` therefore costs a full body read and a
spool to disk before it is told 401, and the rate limiter — also a dependency —
cannot help, because a 429 is likewise decided after the read.

Starlette spools multipart parts past 1 MB to a temporary file with no total
cap, and that file sits on the same disk as the blob store and Postgres. The
failure is not the API running out of memory; it is the database running out of
room.

This is ASGI middleware rather than a dependency for exactly that reason: it is
the only layer that sees bytes before the framework does.
"""

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyTooLarge(Exception):
    pass


class LimitBodySize:
    """Refuse oversized requests before reading them.

    Two checks, because either alone is bypassable:

    * `Content-Length`, when the client declares one. Cheap, and rejects
      before a single byte of body arrives.
    * A running total while the body streams. `Transfer-Encoding: chunked`
      carries no length, and a declared length is only a claim.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    await self._refuse(send)
                    return
            except ValueError:
                pass  # Unparseable: let the streamed count deal with it.

        read = 0

        async def counted() -> Message:
            nonlocal read
            message = await receive()
            if message["type"] == "http.request":
                read += len(message.get("body", b""))
                if read > self.max_bytes:
                    # Cannot send a response from here — the app is already
                    # running — so cut the body short and let it fail on a
                    # truncated payload. The bytes stop arriving either way,
                    # which is the whole point.
                    raise BodyTooLarge
            return message

        try:
            await self.app(scope, counted, send)
        except BodyTooLarge:
            await self._refuse(send)

    async def _refuse(self, send: Send) -> None:
        body = '{"detail":"請求內容過大"}'.encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        })
        await send({"type": "http.response.body", "body": body})
