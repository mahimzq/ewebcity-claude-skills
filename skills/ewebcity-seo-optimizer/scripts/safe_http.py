"""Small, bounded HTTP reader for the eWebCity source-HTML auditor.

No cookies, credentials, environment proxies, JavaScript, or third-party requests.
DNS is checked and the selected address is pinned to the actual connection.
"""
from __future__ import annotations

import http.client
import io
import ipaddress
import queue
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

USER_AGENT = "EWebCitySEO/2.0 (+https://ewebcity.co.uk)"
PRODUCT_TOKEN = "EWebCitySEO"


class FetchError(Exception):
    """An unavailable or deliberately blocked resource, never a clean SEO pass."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BudgetExceeded(FetchError):
    pass


def normalise_url(url: str, base: str | None = None) -> str:
    """Normalise transport identity without stripping meaningful query parameters."""
    if not isinstance(url, str) or not url.strip():
        raise FetchError("invalid_url", "Expected a nonempty HTTP(S) URL.")
    if len(url) > 8192:
        raise FetchError("invalid_url", "URL exceeds the 8,192-character limit.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in url) or "\\" in url:
        raise FetchError("invalid_url", "Control characters and backslashes are not allowed in URLs.")
    candidate = urljoin(base, url.strip()) if base else url.strip()
    try:
        parts = urlsplit(candidate)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("Only absolute HTTP(S) URLs are supported.")
        if parts.username is not None or parts.password is not None:
            raise ValueError("URLs containing credentials are not supported.")
        host = parts.hostname.rstrip(".").lower()
        if not host or "%" in host:
            raise ValueError("Empty hosts and scoped IP addresses are not supported.")
        try:
            address = ipaddress.ip_address(host)
            host = address.compressed
        except ValueError:
            host = host.encode("idna").decode("ascii")
            if not re.fullmatch(r"[a-z0-9.-]+", host) or ".." in host:
                raise ValueError("Invalid hostname.")
        port = parts.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("Invalid port.")
        netloc = f"[{host}]" if ":" in host else host
        if port is not None and port != (443 if scheme == "https" else 80):
            netloc += f":{port}"
        # Keep valid escapes, reserved path characters and query semantics intact.
        path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(parts.query, safe="/%?:@!$&'()*+,;=-._~")
        return urlunsplit((scheme, netloc, path, query, ""))
    except (ValueError, UnicodeError) as exc:
        raise FetchError("invalid_url", str(exc)) from exc


def origin(url: str) -> str:
    parts = urlsplit(normalise_url(url))
    return f"{parts.scheme}://{parts.netloc}"


def _explicit_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _permitted_address(value: str, host: str, allow_localhost: bool) -> bool:
    address = ipaddress.ip_address(value)
    mapped = getattr(address, "ipv4_mapped", None)
    effective = mapped or address
    if allow_localhost and _explicit_loopback_host(host) and effective.is_loopback:
        return True
    if isinstance(address, ipaddress.IPv6Address):
        # Transition/translation ranges can embed otherwise blocked IPv4 hosts.
        if address.sixtofour is not None or address.teredo is not None or address in ipaddress.ip_network("64:ff9b::/96") or address in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
    return effective.is_global and not any((effective.is_multicast, effective.is_unspecified,
        effective.is_private, effective.is_loopback, effective.is_link_local,
        effective.is_reserved, getattr(effective, "is_site_local", False)))


def resolve_public_addresses(host: str, port: int, *, allow_localhost: bool = False,
                             timeout: float = 10.0) -> list[tuple[int, str]]:
    """Reject mixed public/private DNS results; do not resolve again on connect.

    A daemon resolver enforces the caller's wait bound even where the OS resolver
    does not support a per-query timeout. DNS timeout is fatal to the audit.
    """
    result: queue.Queue = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            result.put((True, socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
        except Exception as exc:  # captured and re-raised in the calling thread
            result.put((False, exc))

    worker = threading.Thread(target=resolve, name="ewebcity-dns", daemon=True)
    worker.start()
    try:
        success, value = result.get(timeout=max(0.001, timeout))
    except queue.Empty as exc:
        raise BudgetExceeded("dns_timeout", "DNS lookup exceeded its time limit.") from exc
    if not success:
        raise FetchError("dns_error", f"DNS lookup failed: {value}") from value
    addresses: list[tuple[int, str]] = []
    for family, _socktype, _proto, _canonname, sockaddr in value:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        address = sockaddr[0]
        if not _permitted_address(address, host, allow_localhost):
            raise FetchError("non_public_address", "DNS resolved to a non-public address outside the explicit localhost scope.")
        item = (family, address)
        if item not in addresses:
            addresses.append(item)
    if not addresses:
        raise FetchError("dns_error", "DNS returned no usable addresses.")
    return sorted(addresses, key=lambda item: (item[0], item[1]))


class _DeadlineReader(io.RawIOBase):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        remaining = self.owner.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Request deadline exceeded.")
        self.owner.sock.settimeout(min(self.owner.timeout, remaining))
        return self.owner.sock.recv_into(buffer)

    def close(self) -> None:
        if not self.closed:
            self.owner.reader_count -= 1
            if self.owner.closed and self.owner.reader_count == 0:
                self.owner.sock.close()
        super().close()


class _DeadlineSocket:
    def __init__(self, sock: socket.socket, deadline: float, timeout: float):
        self.sock, self.deadline, self.timeout = sock, deadline, timeout
        self.reader_count = 0
        self.closed = False

    def makefile(self, mode: str, *args, **kwargs):
        if mode != "rb":
            raise ValueError("Only binary reads are supported.")
        self.reader_count += 1
        return io.BufferedReader(_DeadlineReader(self))

    def sendall(self, data: bytes) -> None:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Request deadline exceeded.")
        self.sock.settimeout(min(self.timeout, remaining))
        self.sock.sendall(data)

    def close(self) -> None:
        # HTTPConnection closes its transport early for Connection: close while
        # HTTPResponse still owns the reader, as socket.makefile also permits.
        self.closed = True
        if not self.reader_count:
            self.sock.close()


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: tuple[int, str], *, tls: bool,
                 timeout: float, deadline: float):
        super().__init__(host, port, timeout=timeout)
        self.address, self.tls, self.deadline = address, tls, deadline

    def connect(self) -> None:
        family, address = self.address
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Request deadline exceeded.")
            sock.settimeout(min(self.timeout, remaining))
            endpoint = (address, self.port, 0, 0) if family == socket.AF_INET6 else (address, self.port)
            sock.connect(endpoint)
            if self.tls:
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Request deadline exceeded.")
                sock.settimeout(min(self.timeout, remaining))
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
            self.sock = _DeadlineSocket(sock, self.deadline, self.timeout)
        except BaseException:
            sock.close()
            raise


@dataclass
class Response:
    requested_url: str
    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    redirects: list[dict] = field(default_factory=list)


class SafeClient:
    """A same-origin HTTP reader with per-response and run-wide budgets."""

    def __init__(self, target: str, *, timeout: float = 10.0, delay: float = 0.25,
                 max_bytes: int = 2_000_000, max_total_bytes: int = 20_000_000,
                 max_requests: int = 100, max_seconds: float = 120.0,
                 allow_localhost: bool = False):
        self.scope = origin(target)
        self.timeout, self.delay = timeout, delay
        self.max_bytes, self.max_total_bytes = max_bytes, max_total_bytes
        self.max_requests, self.max_seconds = max_requests, max_seconds
        self.allow_localhost = allow_localhost
        self.requests = self.bytes_received = 0
        self.started = time.monotonic()
        self.deadline = self.started + max_seconds
        self.last_request_started: float | None = None

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise BudgetExceeded("time_budget", "Audit time budget exhausted.")
        return remaining

    def _request(self, url: str) -> Response:
        if origin(url) != self.scope:
            raise FetchError("outside_scope", "Request would leave the exact requested origin.")
        if self.requests >= self.max_requests:
            raise BudgetExceeded("request_budget", "Audit request budget exhausted.")
        if self.bytes_received >= self.max_total_bytes:
            raise BudgetExceeded("byte_budget", "Audit byte budget exhausted.")
        self.remaining()
        if self.last_request_started is not None:
            wait = self.delay - (time.monotonic() - self.last_request_started)
            if wait > 0:
                if wait >= self.remaining():
                    raise BudgetExceeded("time_budget", "Crawl delay would exceed the audit time budget.")
                time.sleep(wait)
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        request_deadline = min(self.deadline, time.monotonic() + self.timeout)
        addresses = resolve_public_addresses(parts.hostname, port,
            allow_localhost=self.allow_localhost,
            timeout=max(0.001, request_deadline - time.monotonic()))
        self.requests += 1
        self.last_request_started = time.monotonic()
        # A failed endpoint is reported honestly; no hidden unbounded retry loop.
        connection = _PinnedConnection(parts.hostname, port, addresses[0],
            tls=parts.scheme == "https", timeout=self.timeout, deadline=request_deadline)
        response = None
        try:
            path = parts.path + (f"?{parts.query}" if parts.query else "")
            connection.request("GET", path, headers={
                "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.8,*/*;q=0.1",
                "Accept-Encoding": "identity", "Connection": "close", "Host": parts.netloc,
            })
            response = connection.getresponse()
            headers: dict[str, str] = {}
            for key, value in response.getheaders():
                key = key.lower()
                headers[key] = f"{headers[key]}, {value}" if key in headers else value
            # Never decompress arbitrary responses: a compressed body can expand
            # beyond its advertised transfer size and bypass the memory budget.
            encoding = headers.get("content-encoding", "identity").strip().lower()
            if encoding not in ("", "identity"):
                raise FetchError("unsupported_encoding", f"Server ignored identity encoding (received {encoding[:80]}).")
            remaining_bytes = self.max_total_bytes - self.bytes_received
            limit = min(self.max_bytes, remaining_bytes)
            body = bytearray()
            while True:
                chunk = response.read(min(65_536, limit - len(body) + 1))
                if not chunk:
                    break
                body.extend(chunk)
                self.bytes_received += len(chunk)
                if len(body) > limit:
                    if remaining_bytes <= self.max_bytes:
                        raise BudgetExceeded("byte_budget", "Audit byte budget exhausted while reading a response.")
                    raise FetchError("response_too_large", "Response exceeded the per-response byte limit; it was not analysed.")
            return Response(url, url, response.status, headers, bytes(body))
        except FetchError:
            raise
        except (OSError, http.client.HTTPException, ValueError) as exc:
            code = "request_timeout" if isinstance(exc, TimeoutError) else "http_error"
            raise FetchError(code, f"Request failed: {type(exc).__name__}: {str(exc)[:250]}") from exc
        finally:
            if response is not None:
                response.close()
            connection.close()

    def fetch(self, url: str, *, allowed: Callable[[str], bool] | None = None) -> Response:
        start = normalise_url(url)
        current = start
        redirects: list[dict] = []
        visited: set[str] = set()
        for _ in range(6):
            if current in visited:
                raise FetchError("redirect_loop", "A redirect loop was observed.")
            visited.add(current)
            if origin(current) != self.scope:
                raise FetchError("redirect_outside_scope", "A redirect would leave the exact requested origin; audit the canonical origin separately.")
            if allowed is not None and not allowed(current):
                raise FetchError("robots_disallowed", "robots.txt disallows this URL for EWebCitySEO.")
            result = self._request(current)
            if result.status not in (301, 302, 303, 307, 308):
                result.requested_url, result.redirects = start, redirects
                return result
            location = result.headers.get("location")
            if not location:
                raise FetchError("redirect_without_location", "Redirect response did not contain a Location header.")
            following = normalise_url(location, current)
            redirects.append({"url": current, "status": result.status, "location": following})
            current = following
        raise FetchError("redirect_limit", "More than five redirects were required; fetching stopped.")


def _robots_path(value: str) -> str:
    """RFC 9309 comparison: decode unreserved escapes, preserve reserved escapes."""
    unreserved = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    output: list[str] = []
    cursor = 0
    while cursor < len(value):
        if value[cursor] == "%" and re.fullmatch(r"[0-9A-Fa-f]{2}", value[cursor + 1:cursor + 3]):
            byte = int(value[cursor + 1:cursor + 3], 16)
            char = chr(byte)
            output.append(char if char in unreserved else f"%{byte:02X}")
            cursor += 3
        else:
            char = value[cursor]
            output.append(quote(char, safe="/:?@!$&'()*+,;=-._~"))
            cursor += 1
    return "".join(output)


class RobotsPolicy:
    """Product-token groups, merged ties, wildcard paths, longest rule, allow ties."""

    def __init__(self, text: str = ""):
        if len(text.encode("utf-8")) > 512_000 or len(text.splitlines()) > 10_000:
            raise FetchError("robots_too_large", "robots.txt exceeds the bounded parser limit.")
        self.groups: list[dict] = []
        self.sitemaps: list[str] = []
        self.recognised_lines = 0
        group: dict = {"agents": [], "rules": [], "delays": []}
        rules_started = False
        for raw_line in text.lstrip("\ufeff").splitlines():
            if len(raw_line) > 8192:
                raise FetchError("robots_rule_too_large", "A robots.txt line exceeds the bounded parser limit.")
            line = raw_line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                self.recognised_lines += 1
                if rules_started:
                    if group["agents"]:
                        self.groups.append(group)
                    group, rules_started = {"agents": [], "rules": [], "delays": []}, False
                if value:
                    group["agents"].append(value.lower())
            elif key in ("allow", "disallow") and group["agents"]:
                self.recognised_lines += 1
                rules_started = True
                if value:
                    group["rules"].append((key == "allow", _robots_path(value)))
            elif key == "crawl-delay" and group["agents"]:
                self.recognised_lines += 1
                rules_started = True
                try:
                    delay = float(value)
                    if 0 <= delay <= 86_400:
                        group["delays"].append(delay)
                except ValueError:
                    pass
            elif key == "sitemap" and value:
                self.recognised_lines += 1
                self.sitemaps.append(value)
        if group["agents"]:
            self.groups.append(group)

    def _groups_for(self, token: str) -> list[dict]:
        token = token.lower()
        matches = []
        best = -1
        for group in self.groups:
            lengths = [0 if agent == "*" else len(agent)
                       for agent in group["agents"] if agent == "*" or agent in token]
            if not lengths:
                continue
            length = max(lengths)
            if length > best:
                matches, best = [group], length
            elif length == best:
                matches.append(group)
        return matches

    def can_fetch(self, url: str, token: str = PRODUCT_TOKEN) -> bool:
        parts = urlsplit(url)
        path = _robots_path((parts.path or "/") + (f"?{parts.query}" if parts.query else ""))
        best = -1
        permitted = True
        for group in self._groups_for(token):
            for allow, pattern in group["rules"]:
                terminal = pattern.endswith("$")
                body = pattern[:-1] if terminal else pattern
                if _robots_match(body, path, terminal):
                    specificity = len(body.replace("*", "").encode("utf-8"))
                    if specificity > best or (specificity == best and allow):
                        best, permitted = specificity, allow
        return permitted

    def crawl_delay(self, token: str = PRODUCT_TOKEN) -> float:
        delays = [value for group in self._groups_for(token) for value in group["delays"]]
        return max(delays, default=0.0)


def _robots_match(pattern: str, path: str, terminal: bool) -> bool:
    # Ordered fixed segments avoid regex backtracking on attacker-controlled '*'.
    segments = pattern.split("*")
    if len(segments) == 1:
        return path == pattern if terminal else path.startswith(pattern)
    if not path.startswith(segments[0]):
        return False
    position = len(segments[0])
    for segment in segments[1:-1]:
        found = path.find(segment, position)
        if found < 0:
            return False
        position = found + len(segment)
    last = segments[-1]
    if terminal:
        return path.endswith(last) and len(path) - len(last) >= position
    return path.find(last, position) >= 0
