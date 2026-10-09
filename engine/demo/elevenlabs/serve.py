# Serves gen.html and saves POSTed clip bytes to clips/<NN>.mp3. Phase 11 build-time only.
import http.server, pathlib, re, sys
HERE = pathlib.Path(__file__).parent
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else HERE / "clips"); OUT.mkdir(exist_ok=True)
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=str(HERE), **k)
    def do_POST(s):
        m = re.fullmatch(r"/save/(\d\d)", s.path)
        if not m: return s.send_error(404)
        (OUT / f"{m[1]}.mp3").write_bytes(s.rfile.read(int(s.headers["Content-Length"])))
        s.send_response(204); s.end_headers()
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
