"""Per-host async httpx clients with HTTP/2, connection pooling, and custom UA."""
import httpx

_USER_AGENT = "personal-job-tracker/0.1"

_clients: dict[str, httpx.AsyncClient] = {}


def get_client(host: str) -> httpx.AsyncClient:
    """Return a cached AsyncClient for the given host."""
    if host not in _clients:
        _clients[host] = httpx.AsyncClient(
            http2=True,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30.0,
            ),
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        )
    return _clients[host]


async def close_all_clients() -> None:
    for client in _clients.values():
        await client.aclose()
    _clients.clear()
