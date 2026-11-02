import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app as flask_app


class KeepPath:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or "/"
        script = environ.get("SCRIPT_NAME") or ""
        environ["VERCEL_ORIGINAL_PATH"] = path
        for prefix in ("/api/index", "/api"):
            if path == prefix:
                script += prefix
                path = "/"
                break
            if path.startswith(prefix + "/"):
                script += prefix
                path = path[len(prefix):] or "/"
                break
        environ["SCRIPT_NAME"] = script
        environ["PATH_INFO"] = path or "/"
        return self.wsgi_app(environ, start_response)


app = KeepPath(flask_app)
