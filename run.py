"""Start the ForgeAI web app: python run.py [--port 8000]"""
import argparse

import uvicorn

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    print(f"ForgeAI on http://{a.host}:{a.port}")
    uvicorn.run("server.app:app", host=a.host, port=a.port)
