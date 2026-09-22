"""TRENCHNET read-only HTTP service. No private keys or trading endpoints."""
ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def valid_address(value):
    if not isinstance(value, str) or not 32 <= len(value) <= 44:
        return False
    n = 0
    for c in value:
        if c not in ALPHABET:
            return False
        n = n * 58 + ALPHABET.index(c)
    zeros = len(value) - len(value.lstrip('1'))
    return zeros + (n.bit_length() + 7) // 8 == 32

import collections
import datetime as dt
import http.server
import ipaddress
import json
import logging
import mimetypes
import os
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
VERSION = 'trenchnet-v1'
COVERAGE = 'Bounded public-chain sample, not a complete wallet history. Missing trades do not mean no activity.'


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def empty_snapshot(message='Waiting for the first public-data collection.'):
    return {'version': VERSION, 'updatedAt': None,
            'status': {'collector': 'starting', 'message': message, 'coverage': COVERAGE,
                       'models': {'astra': 'not_connected', 'jev': 'not_connected'}},
            'markets': [], 'trades': [], 'traders': [], 'graph': {'nodes': [], 'edges': []}, 'decisions': []}


def load_snapshot(db_path):
    try:
        from analytics import snapshot
        return snapshot(str(db_path))
    except Exception:
        logging.exception('Snapshot unavailable')
        return empty_snapshot('Public observations are temporarily unavailable. Please retry.')


def client_identity(peer, forwarded, trust_cloudflare=False):
    if trust_cloudflare and peer in {'127.0.0.1', '::1'} and forwarded:
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return peer


class MarketLookup:
    """Fixed-host public lookup: bounded concurrency, TTL, total egress budget."""
    def __init__(self):
        self.lock = threading.Lock()
        self.cache = collections.OrderedDict()
        self.calls = collections.deque()
        self.inflight = threading.BoundedSemaphore(3)

    def get(self, address):
        with self.lock:
            now = time.monotonic()
            cached = self.cache.get(address)
            if cached and cached[0] > now:
                return cached[1]
            while self.calls and self.calls[0] < now - 60:
                self.calls.popleft()
            if len(self.calls) >= 15 or not self.inflight.acquire(blocking=False):
                return None, 'Lookup busy. Please try again in a minute.'
            self.calls.append(now)
        try:
            url = 'https://api.dexscreener.com/token-pairs/v1/solana/' + address
            req = urllib.request.Request(url, headers={'User-Agent': 'Trenchnet/1.0'})
            with urllib.request.urlopen(req, timeout=8) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError('Response too large')
                rows = json.loads(raw)
            pairs = [p for p in rows if p.get('chainId') == 'solana' and p.get('baseToken', {}).get('address') == address]
            if not pairs:
                result = (None, 'No indexed Solana base-token market found for this address.')
            else:
                p = max(pairs, key=lambda x: (x.get('liquidity') or {}).get('usd') or 0)
                def number(x):
                    import math
                    try:
                        v = float(x)
                        return v if math.isfinite(v) else None
                    except (TypeError, ValueError):
                        return None
                created = p.get('pairCreatedAt')
                result = ({'address': address, 'symbol': p['baseToken'].get('symbol', '?'),
                           'name': p['baseToken'].get('name', 'Unknown token'), 'priceUsd': number(p.get('priceUsd')),
                           'marketCap': number(p.get('marketCap')), 'liquidityUsd': number((p.get('liquidity') or {}).get('usd')),
                           'volume24h': number((p.get('volume') or {}).get('h24')), 'change24h': number((p.get('priceChange') or {}).get('h24')),
                           'pairUrl': p.get('url'), 'imageUrl': (p.get('info') or {}).get('imageUrl'),
                           'createdAt': dt.datetime.fromtimestamp(created / 1000, dt.timezone.utc).isoformat() if created else None,
                           'source': 'DexScreener', 'fetchedAt': utc_now()}, None)
            with self.lock:
                self.cache[address] = (time.monotonic() + 120, result)
                while len(self.cache) > 256:
                    self.cache.popitem(last=False)
            return result
        except Exception:
            logging.warning('DexScreener lookup unavailable', exc_info=True)
            return None, 'Market provider unavailable. Saved observations are still shown.'
        finally:
            self.inflight.release()


class AppServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32


def create_server(host='127.0.0.1', port=8787, db_path=None, web_path=None, snapshot_fn=load_snapshot):
    db_path = Path(db_path or ROOT / 'data' / 'trenchnet.sqlite')
    web_path = Path(web_path or ROOT / 'web').resolve()
    lookup = MarketLookup()
    trust_cloudflare = os.environ.get('TRUST_CLOUDFLARE') == '1'
    if trust_cloudflare and host not in {'127.0.0.1', '::1', 'localhost'}:
        raise ValueError('Trusted local Cloudflare proxy requires loopback binding')
    rate_lock = threading.Lock()
    clients = collections.OrderedDict()

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = 'TRENCHNET'
        sys_version = ''

        def setup(self):
            super().setup()
            self.connection.settimeout(12)

        def log_message(self, fmt, *args):
            # Avoid recording arbitrary search strings or control characters.
            logging.info('%s %s', self.command, str(args[1]) if len(args) > 1 else '-')

        def allowed(self):
            with rate_lock:
                now = time.monotonic()
                ip = client_identity(self.client_address[0], self.headers.get('CF-Connecting-IP'), trust_cloudflare)
                timestamps = clients.setdefault(ip, collections.deque())
                while timestamps and timestamps[0] < now - 60:
                    timestamps.popleft()
                if len(timestamps) >= 150:
                    return False
                timestamps.append(now)
                clients.move_to_end(ip)
                while len(clients) > 2048:
                    clients.popitem(last=False)
                return True

        def send(self, code, body, mime='application/json; charset=utf-8', download=False):
            if not isinstance(body, bytes):
                body = json.dumps(body, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Cache-Control', 'no-store' if 'json' in mime or 'html' in mime else 'public, max-age=300')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if download:
                self.send_header('Content-Disposition', 'attachment; filename="trenchnet-public-observations.json"')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def do_POST(self):
            self.send(405, {'error': 'Read-only service. No transaction or mutation endpoint.'})

        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST
        do_OPTIONS = do_POST

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            try:
                self.route()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                return
            except Exception:
                logging.exception('Request failed')
                self.send(500, {'error': 'Unable to read observations. Please retry.'})

        def route(self):
            if len(self.path) > 2048:
                return self.send(414, {'error': 'Request too long'})
            if not self.allowed():
                return self.send(429, {'error': 'Too many requests. Retry in one minute.'})
            parsed = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parsed.path)
            if path == '/api/health':
                return self.send(200, {'status': 'ok', 'version': VERSION, 'time': utc_now(), 'readOnly': True})
            if path in ('/api/snapshot', '/api/export'):
                return self.send(200, snapshot_fn(db_path), download=path == '/api/export')
            if path in ('/api/token', '/api/wallet'):
                address = urllib.parse.parse_qs(parsed.query).get('address', [''])[0]
                if not valid_address(address):
                    return self.send(400, {'error': 'Enter a valid 32-byte Solana address (base58).'})
                snap = snapshot_fn(db_path)
                if path == '/api/wallet':
                    return self.send(200, {'address': address,
                        'trades': [t for t in snap['trades'] if t['wallet'] == address],
                        'profile': next((t for t in snap['traders'] if t['address'] == address), None),
                        'coverage': COVERAGE})
                market = next((m for m in snap['markets'] if m['address'] == address), None)
                error = None
                if market is None:
                    market, error = lookup.get(address)
                trades = [t for t in snap['trades'] if t['mint'] == address]
                wallets = {t['wallet'] for t in trades}
                result = {'address': address, 'market': market, 'trades': trades,
                    'traders': [t for t in snap['traders'] if t['address'] in wallets],
                    'decisions': [d for d in snap['decisions'] if d['mint'] == address],
                    'coverage': COVERAGE}
                if error:
                    result['error'] = error
                return self.send(200, result)
            if path.startswith('/api/'):
                return self.send(404, {'error': 'Endpoint not found'})
            # Only web assets, no runtime DB, receipts, source or dotenv.
            relative = path.lstrip('/') or 'index.html'
            if any(x.startswith('.') for x in Path(relative).parts):
                return self.send(404, {'error': 'Not found'})
            target = (web_path / relative).resolve()
            if not target.is_relative_to(web_path) or not target.is_file() or target.suffix not in {'.html', '.css', '.js', '.mjs', '.svg', '.png', '.ico', '.webp', '.woff2'}:
                return self.send(404, {'error': 'Not found'})
            mime = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
            if target.suffix in {'.html', '.css', '.js'}:
                mime += '; charset=utf-8'
            return self.send(200, target.read_bytes(), mime)

    return AppServer((host, int(port)), Handler)


def collect_loop(db_path, stop):
    from collector import collect_once
    interval = max(90, int(os.environ.get('COLLECT_INTERVAL', '90')))
    while not stop.is_set():
        try:
            summary = collect_once(str(db_path))
            logging.info('Collection: %s', summary)
        except Exception:
            logging.exception('Collection failed; previous observations preserved')
        stop.wait(interval)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    db_path = Path(os.environ.get('DB_PATH', ROOT / 'data' / 'trenchnet.sqlite'))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    if os.environ.get('COLLECT_ENABLED', '1') == '1':
        threading.Thread(target=collect_loop, args=(db_path, stop), daemon=True).start()
    server = create_server(os.environ.get('HOST', '127.0.0.1'), os.environ.get('PORT', '8787'), db_path)
    logging.info('TRENCHNET %s serving on %s:%s', VERSION, *server.server_address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
