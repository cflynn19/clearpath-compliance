import hashlib

from fastapi import Request


def visitor_id(request: Request) -> str:
    """Who to count usage against: the client's IP address, hashed so it isn't stored raw.

    Behind Render's proxy the client address is the first X-Forwarded-For entry. A client
    can forge that header, but all it gains is more per-visitor quota; the global daily
    cap still bounds the cost (D11).
    """
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
    return hashlib.sha256(ip.encode()).hexdigest()[:32]
