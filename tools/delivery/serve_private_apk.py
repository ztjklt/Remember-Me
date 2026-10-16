"""Temporary LAN download of one explicitly selected APK; no directory browsing."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import time
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=8878)
    parser.add_argument('--token', required=True)
    parser.add_argument('--hours', type=float, default=8)
    args = parser.parse_args()
    apk = args.apk.resolve()
    assert apk.is_file() and apk.suffix == '.apk'
    assert re.fullmatch('[a-f0-9]{32}', args.token)
    assert args.host.startswith(('10.', '192.168.', '172.16.'))
    route = '/' + args.token + '/app.apk'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass
        def do_HEAD(self): self.send_file(False)
        def do_GET(self): self.send_file(True)
        def send_file(self, body):
            if urlsplit(self.path).path != route:
                self.send_error(404); return
            size = apk.stat().st_size; start = 0; end = size - 1; status = 200
            if self.headers.get('Range'):
                match = re.fullmatch(r'bytes=(\d+)-(\d*)', self.headers['Range'])
                if not match: self.send_error(416); return
                start = int(match[1]); end = int(match[2]) if match[2] else end
                if not 0 <= start <= end < size: self.send_error(416); return
                status = 206
            self.send_response(status)
            self.send_header('Content-Type', 'application/vnd.android.package-archive')
            self.send_header('Content-Disposition', 'attachment; filename="' + apk.name + '"')
            self.send_header('Content-Length', str(end - start + 1))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-store')
            if status == 206: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if body:
                try:
                    with apk.open('rb') as source:
                        source.seek(start); remaining = end - start + 1
                        while remaining:
                            chunk = source.read(min(1024 * 1024, remaining))
                            if not chunk: break
                            self.wfile.write(chunk); remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError): pass

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.timeout = 1
    deadline = time.monotonic() + min(args.hours, 24) * 3600
    try:
        while time.monotonic() < deadline: server.handle_request()
    finally: server.server_close()


if __name__ == '__main__': main()
