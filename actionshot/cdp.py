"""Chrome DevTools Protocol integration for web-native selectors.

Connects to Chrome (or Edge/Brave) via the CDP debugging port to extract
DOM-level selectors for elements at screen coordinates.  This enables
ActionShot to generate stable CSS / XPath / ARIA selectors for Brazilian
legal web systems (PJe, Projudi, e-SAJ, eproc) that run inside a browser.

Only uses stdlib (``urllib.request``, ``json``, ``socket``) -- no extra
dependencies.
"""

from __future__ import annotations

import json
import socket
import struct
import hashlib
import base64
import os
import urllib.request
import urllib.error
from typing import Any


# ---------------------------------------------------------------------------
# Low-level WebSocket (RFC 6455) client -- minimal, send/recv text only
# ---------------------------------------------------------------------------

class _SimpleWebSocket:
    """Bare-bones WebSocket client sufficient for CDP JSON-RPC."""

    def __init__(self, url: str, timeout: float = 5.0):
        # Parse ws://host:port/path
        assert url.startswith("ws://"), f"Only ws:// supported, got {url}"
        rest = url[len("ws://"):]
        slash = rest.find("/")
        if slash == -1:
            hostport, path = rest, "/"
        else:
            hostport, path = rest[:slash], rest[slash:]
        if ":" in hostport:
            host, port_s = hostport.rsplit(":", 1)
            port = int(port_s)
        else:
            host, port = hostport, 80

        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)

        # WebSocket handshake
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        self._sock.sendall(handshake.encode())

        # Read response headers (we just need to see "101")
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket handshake failed: connection closed")
            response += chunk

        status_line = response.split(b"\r\n")[0]
        if b"101" not in status_line:
            raise ConnectionError(f"WebSocket handshake failed: {status_line.decode(errors='replace')}")

    def send(self, text: str) -> None:
        """Send a text frame."""
        payload = text.encode("utf-8")
        frame = bytearray()
        frame.append(0x81)  # FIN + text opcode

        length = len(payload)
        if length < 126:
            frame.append(0x80 | length)  # masked
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack("!Q", length))

        mask = os.urandom(4)
        frame.extend(mask)
        for i, b in enumerate(payload):
            frame.append(b ^ mask[i % 4])

        self._sock.sendall(bytes(frame))

    def recv(self) -> str:
        """Receive one text frame (blocking)."""
        data = self._recvn(2)
        opcode = data[0] & 0x0F
        masked = bool(data[1] & 0x80)
        length = data[1] & 0x7F

        if length == 126:
            length = struct.unpack("!H", self._recvn(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recvn(8))[0]

        if masked:
            mask = self._recvn(4)
            raw = self._recvn(length)
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(raw))
        else:
            payload = self._recvn(length)

        if opcode == 0x08:  # close
            raise ConnectionError("WebSocket closed by server")
        if opcode == 0x09:  # ping -> pong
            self._send_pong(payload)
            return self.recv()

        return payload.decode("utf-8", errors="replace")

    def _send_pong(self, payload: bytes) -> None:
        frame = bytearray()
        frame.append(0x8A)  # FIN + pong
        length = len(payload)
        frame.append(0x80 | length)
        mask = os.urandom(4)
        frame.extend(mask)
        for i, b in enumerate(payload):
            frame.append(b ^ mask[i % 4])
        self._sock.sendall(bytes(frame))

    def _recvn(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("WebSocket connection closed")
            buf.extend(chunk)
        return bytes(buf)

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CDP JSON-RPC helper
# ---------------------------------------------------------------------------

class _CDPSession:
    """Send CDP commands over a WebSocket and collect responses."""

    def __init__(self, ws_url: str, timeout: float = 5.0):
        self._ws = _SimpleWebSocket(ws_url, timeout=timeout)
        self._id = 0
        self._timeout = timeout

    def send(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"id": self._id, "method": method}
        if params:
            msg["params"] = params
        self._ws.send(json.dumps(msg))

        # Read until we get the matching response (skip events)
        while True:
            raw = self._ws.recv()
            resp = json.loads(raw)
            if resp.get("id") == self._id:
                if "error" in resp:
                    err = resp["error"]
                    raise RuntimeError(f"CDP error {err.get('code')}: {err.get('message')}")
                return resp.get("result", {})
            # else: it's an event, skip

    def close(self) -> None:
        self._ws.close()


# ---------------------------------------------------------------------------
# CSS selector builder
# ---------------------------------------------------------------------------

def _build_css_selector(node_info: dict, outer_html: str) -> str:
    """Build a CSS selector for a node, preferring ID > unique class > tag+attrs.

    *node_info* comes from ``DOM.describeNode``.
    """
    attrs = _attrs_dict(node_info)
    tag = node_info.get("nodeName", "").lower()

    # 1. ID
    elem_id = attrs.get("id", "")
    if elem_id and " " not in elem_id:
        return f"#{elem_id}"

    # 2. data-testid / data-cy (common in modern apps)
    for attr_name in ("data-testid", "data-cy", "data-test"):
        if attr_name in attrs:
            return f'{tag}[{attr_name}="{attrs[attr_name]}"]'

    # 3. name attribute (very common in legal forms)
    if "name" in attrs and tag in ("input", "select", "textarea", "button"):
        return f'{tag}[name="{attrs["name"]}"]'

    # 4. Unique class
    classes = attrs.get("class", "").split()
    meaningful = [c for c in classes if not c.startswith(("ng-", "v-", "jsx-", "css-"))]
    if meaningful:
        cls_selector = "." + ".".join(meaningful[:2])
        return f"{tag}{cls_selector}" if tag else cls_selector

    # 5. Tag + type (for inputs)
    if tag == "input" and "type" in attrs:
        return f'input[type="{attrs["type"]}"]'

    # 6. Tag + text content hint via aria-label
    if "aria-label" in attrs:
        return f'{tag}[aria-label="{attrs["aria-label"]}"]'

    # 7. Bare tag (will need nth-child in real usage)
    return tag or "*"


def _build_xpath(node_info: dict) -> str:
    """Build an XPath expression for the node."""
    attrs = _attrs_dict(node_info)
    tag = node_info.get("nodeName", "").lower() or "*"

    # ID
    elem_id = attrs.get("id", "")
    if elem_id and " " not in elem_id:
        return f'//*[@id="{elem_id}"]'

    # name attribute
    if "name" in attrs:
        return f'//{tag}[@name="{attrs["name"]}"]'

    # text content via aria-label or visible text
    aria_label = attrs.get("aria-label", "")
    if aria_label:
        return f'//{tag}[@aria-label="{aria_label}"]'

    # data-testid
    for attr_name in ("data-testid", "data-cy"):
        if attr_name in attrs:
            return f'//{tag}[@{attr_name}="{attrs[attr_name]}"]'

    # Class-based
    classes = attrs.get("class", "").split()
    meaningful = [c for c in classes if not c.startswith(("ng-", "v-", "jsx-", "css-"))]
    if meaningful:
        return f'//{tag}[contains(@class, "{meaningful[0]}")]'

    return f"//{tag}"


def _get_accessible_info(node_info: dict) -> dict | None:
    """Extract ARIA role and accessible name from node attributes."""
    attrs = _attrs_dict(node_info)
    tag = node_info.get("nodeName", "").lower()

    # Determine role
    role = attrs.get("role", "")
    if not role:
        # Implicit roles
        _implicit_roles = {
            "button": "button",
            "a": "link",
            "input": "textbox",
            "select": "combobox",
            "textarea": "textbox",
            "img": "img",
            "nav": "navigation",
            "main": "main",
            "header": "banner",
            "footer": "contentinfo",
            "form": "form",
            "table": "table",
            "dialog": "dialog",
        }
        input_type_roles = {
            "checkbox": "checkbox",
            "radio": "radio",
            "submit": "button",
            "button": "button",
            "range": "slider",
        }
        if tag == "input" and attrs.get("type", "text") in input_type_roles:
            role = input_type_roles[attrs["type"]]
        elif tag in _implicit_roles:
            role = _implicit_roles[tag]

    # Determine accessible name
    name = (
        attrs.get("aria-label", "")
        or attrs.get("title", "")
        or attrs.get("alt", "")
        or attrs.get("placeholder", "")
        or attrs.get("value", "")
    )

    if role or name:
        result: dict[str, str] = {"method": "accessible_name"}
        if role:
            result["role"] = role
        if name:
            result["name"] = name
        return result
    return None


def _attrs_dict(node_info: dict) -> dict[str, str]:
    """Convert CDP ``attributes`` list ``[k, v, k, v, ...]`` to a dict."""
    raw = node_info.get("attributes", [])
    d: dict[str, str] = {}
    for i in range(0, len(raw) - 1, 2):
        d[raw[i]] = raw[i + 1]
    return d


# ---------------------------------------------------------------------------
# Coordinate conversion helpers
# ---------------------------------------------------------------------------

def _get_chrome_window_offset() -> tuple[int, int]:
    """Get Chrome window position to convert screen coords to page coords.

    Uses Win32 API to find the Chrome content area offset.
    Returns (offset_x, offset_y).
    """
    try:
        import ctypes
        import ctypes.wintypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect.left, rect.top
    except Exception:
        return 0, 0


# ---------------------------------------------------------------------------
# ChromeCDP public class
# ---------------------------------------------------------------------------

_BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "brave.exe"}


class ChromeCDP:
    """Interface to Chrome DevTools Protocol for web-native selector extraction.

    Connects via the CDP debugging port (default 9222) and uses DOM/CSS
    commands to inspect elements at screen coordinates.
    """

    def __init__(self) -> None:
        self._session: _CDPSession | None = None
        self._port: int = 9222
        self._ws_url: str = ""

    # -- connection ----------------------------------------------------------

    def connect(self, port: int = 9222) -> None:
        """Connect to Chrome via CDP debugging port.

        Chrome must be launched with ``--remote-debugging-port=PORT``.
        """
        self._port = port
        self.disconnect()

        # Discover the first available page target
        url = f"http://localhost:{port}/json"
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                targets = json.loads(resp.read().decode())
        except Exception as exc:
            raise ConnectionError(
                f"Cannot reach Chrome CDP at localhost:{port}. "
                f"Launch Chrome with --remote-debugging-port={port}"
            ) from exc

        # Pick the first page-type target
        ws_url = ""
        for t in targets:
            if t.get("type") == "page":
                ws_url = t.get("webSocketDebuggerUrl", "")
                if ws_url:
                    break

        if not ws_url:
            raise ConnectionError("No page target found via CDP /json endpoint")

        self._ws_url = ws_url
        self._session = _CDPSession(ws_url, timeout=5.0)

        # Enable necessary domains
        self._session.send("DOM.enable")
        self._session.send("CSS.enable")

    def disconnect(self) -> None:
        """Close the CDP WebSocket connection."""
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def is_available(self) -> bool:
        """Return True if Chrome debugging port is reachable."""
        try:
            url = f"http://localhost:{self._port}/json/version"
            with urllib.request.urlopen(url, timeout=2) as resp:
                data = json.loads(resp.read().decode())
            return "Browser" in data or "webSocketDebuggerUrl" in data
        except Exception:
            return False

    # -- page info -----------------------------------------------------------

    def get_page_url(self) -> str:
        """Return the current page URL."""
        if not self._session:
            raise RuntimeError("Not connected to CDP")
        result = self._session.send(
            "Runtime.evaluate", {"expression": "window.location.href"}
        )
        return result.get("result", {}).get("value", "")

    def execute_js(self, expression: str) -> Any:
        """Evaluate a JavaScript expression in the page context.

        Returns the value for simple types, or a description for complex ones.
        """
        if not self._session:
            raise RuntimeError("Not connected to CDP")
        result = self._session.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        res_obj = result.get("result", {})
        if "value" in res_obj:
            return res_obj["value"]
        return res_obj.get("description", res_obj.get("type", ""))

    # -- element inspection --------------------------------------------------

    def get_element_at(self, x: int, y: int) -> dict[str, dict | None]:
        """Get web-native selectors for the DOM element at screen coordinates.

        Converts screen coordinates to page-relative coordinates (accounting
        for Chrome window chrome), then uses CDP to inspect the element.

        Returns a dict with keys:
          - ``primary_web``: CSS selector (most specific available)
          - ``primary_web_alt``: XPath expression
          - ``secondary_web``: ARIA accessible name + role
        """
        if not self._session:
            raise RuntimeError("Not connected to CDP")

        # Convert screen coords to page coords via JS
        page_x, page_y = self._screen_to_page(x, y)

        # Get the DOM node at those coordinates
        try:
            loc_result = self._session.send(
                "DOM.getNodeForLocation",
                {"x": page_x, "y": page_y, "includeUserAgentShadowDOM": False},
            )
        except RuntimeError:
            return {"primary_web": None, "primary_web_alt": None, "secondary_web": None}

        backend_node_id = loc_result.get("backendNodeId", 0)
        node_id = loc_result.get("nodeId", 0)

        if not backend_node_id and not node_id:
            return {"primary_web": None, "primary_web_alt": None, "secondary_web": None}

        # Describe the node to get attributes
        try:
            describe_result = self._session.send(
                "DOM.describeNode",
                {"backendNodeId": backend_node_id, "depth": 0},
            )
        except RuntimeError:
            return {"primary_web": None, "primary_web_alt": None, "secondary_web": None}

        node_info = describe_result.get("node", {})

        # If we hit a text node, go up to the parent element
        if node_info.get("nodeType") == 3:  # TEXT_NODE
            parent_id = node_info.get("parentId", 0)
            if parent_id:
                try:
                    describe_result = self._session.send(
                        "DOM.describeNode",
                        {"nodeId": parent_id, "depth": 0},
                    )
                    node_info = describe_result.get("node", {})
                except RuntimeError:
                    pass

        # Get outer HTML for context
        outer_html = ""
        try:
            html_result = self._session.send(
                "DOM.getOuterHTML",
                {"backendNodeId": backend_node_id},
            )
            outer_html = html_result.get("outerHTML", "")
        except RuntimeError:
            pass

        # Build selectors
        css_sel = _build_css_selector(node_info, outer_html)
        xpath_sel = _build_xpath(node_info)
        aria_info = _get_accessible_info(node_info)

        # Try to get text content for better XPath
        text_content = ""
        if outer_html:
            # Quick extraction of inner text from outer HTML
            import re
            text_match = re.search(r">([^<]+)<", outer_html)
            if text_match:
                text_content = text_match.group(1).strip()

        # Enhance XPath with text content if we got generic selectors
        tag = node_info.get("nodeName", "").lower() or "*"
        if text_content and xpath_sel == f"//{tag}":
            xpath_sel = f'//{tag}[contains(., "{text_content}")]'

        # Enhance ARIA name with text content
        if aria_info and not aria_info.get("name") and text_content:
            aria_info["name"] = text_content

        primary_web: dict | None = {"method": "css_selector", "value": css_sel}
        primary_web_alt: dict | None = {"method": "xpath", "value": xpath_sel}
        secondary_web = aria_info

        return {
            "primary_web": primary_web,
            "primary_web_alt": primary_web_alt,
            "secondary_web": secondary_web,
        }

    # -- internal helpers ----------------------------------------------------

    def _screen_to_page(self, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Convert screen coordinates to page-relative coordinates.

        Uses JavaScript to query the Chrome viewport offset, then subtracts
        the browser chrome (address bar, tabs, etc.).
        """
        try:
            # Ask the page for its viewport position relative to screen
            js = (
                "JSON.stringify({"
                "  screenX: window.screenX,"
                "  screenY: window.screenY,"
                "  outerW: window.outerWidth,"
                "  outerH: window.outerHeight,"
                "  innerW: window.innerWidth,"
                "  innerH: window.innerHeight,"
                "  devicePixelRatio: window.devicePixelRatio"
                "})"
            )
            result = self._session.send(
                "Runtime.evaluate", {"expression": js, "returnByValue": True}
            )
            info = json.loads(result.get("result", {}).get("value", "{}"))

            dpr = info.get("devicePixelRatio", 1)
            win_x = info.get("screenX", 0)
            win_y = info.get("screenY", 0)
            outer_h = info.get("outerH", 0)
            inner_h = info.get("innerH", 0)

            # Chrome offset = window position + browser chrome height
            chrome_top = outer_h - inner_h  # tabs + address bar height
            page_x = int((screen_x - win_x) / dpr)
            page_y = int((screen_y - win_y - chrome_top) / dpr)

            # Clamp to non-negative
            page_x = max(0, page_x)
            page_y = max(0, page_y)

            return page_x, page_y

        except Exception:
            # Fallback: use Win32 offset
            off_x, off_y = _get_chrome_window_offset()
            # Approximate Chrome toolbar height
            toolbar_h = 85
            return max(0, screen_x - off_x), max(0, screen_y - off_y - toolbar_h)
