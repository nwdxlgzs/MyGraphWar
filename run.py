import argparse
import threading
import time
import urllib.request
import webbrowser
import uvicorn
from server.config import settings

def open_when_ready(url):
    health=f"http://127.0.0.1:{settings.port}/api/v1/health"
    for _ in range(100):
        try:
            with urllib.request.urlopen(health,timeout=.5):
                webbrowser.open(url)
                return
        except Exception:time.sleep(.1)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--open-browser",action="store_true")
    args=parser.parse_args()
    if args.open_browser:threading.Thread(target=open_when_ready,args=(f"http://127.0.0.1:{settings.port}",),daemon=True).start()
    uvicorn.run("server.main:app",host=settings.host,port=settings.port,reload=False)
