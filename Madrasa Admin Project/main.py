"""Start the Madrasa & School Admin System:  py main.py  (Windows)  or  python3 main.py"""

import uvicorn

from app.config import settings
from app.main import app

if __name__ == "__main__":
    shown_host = "localhost" if settings.host in ("127.0.0.1", "0.0.0.0") else settings.host
    url = f"http://{shown_host}:{settings.port}"
    print(f"Server is running. Open {url} in your browser (Ctrl+C to stop).", flush=True)
    uvicorn.run(app, host=settings.host, port=settings.port)
