from __future__ import annotations

from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Request


API = "http://api:8080"

app = FastAPI(title="Local Router (LB Simulation)", version="1.0.0")


def _upstream(method: str, path: str, *, params=None, json=None) -> Any:
    r = requests.request(method, f"{API}{path}", params=params, json=json, timeout=3)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    if "application/json" in (r.headers.get("content-type") or ""):
        return r.json()
    return {"raw": r.text}


@app.get("/status")
def status() -> Any:
    return _upstream("GET", "/status")


@app.get("/dashboard")
def dashboard(limit: int = 20) -> Any:
    return _upstream("GET", "/dashboard", params={"limit": limit})


@app.get("/decision")
def decision() -> Any:
    return _upstream("GET", "/decision")


@app.post("/write")
async def write(req: Request) -> Any:
    body = await req.json()
    return _upstream("POST", "/write", json=body)


@app.get("/read")
def read(key: str) -> Any:
    return _upstream("GET", "/read", params={"key": key})


@app.post("/admin/switch")
def switch(region: str) -> Any:
    return _upstream("POST", "/admin/switch", params={"region": region})


@app.get("/admin/kv")
def admin_kv(region: str, limit: int = 100) -> Any:
    return _upstream("GET", "/admin/kv", params={"region": region, "limit": limit})


@app.get("/admin/read")
def admin_read(region: str, key: str) -> Any:
    return _upstream("GET", "/admin/read", params={"region": region, "key": key})

