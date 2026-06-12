"""SignFinder Agent — FastAPI :9000 + background poll-loop. v1.18.0"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import load_mail_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _poll_loop() -> None:
    cfg = load_mail_config()
    if not cfg["imap_host"]:
        logger.warning("IMAP не настроен — poll loop отключён")
        return
    logger.info("Poll loop started, interval=%ds", cfg["poll_interval_sec"])
    while True:
        try:
            from app.poller import run_one_poll
            result = await asyncio.get_event_loop().run_in_executor(None, run_one_poll)
            if result.get("processed") or result.get("errors"):
                logger.info("poll done: processed=%d errors=%d",
                            result["processed"], result["errors"])
        except Exception as e:
            logger.exception("poll loop error: %s", e)
        cfg = load_mail_config()
        await asyncio.sleep(cfg["poll_interval_sec"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_poll_loop())
    logger.info("SignFinder Agent v1.18.0 starting on :9000")
    yield
    task.cancel()
    logger.info("Agent shutting down")


app = FastAPI(title="SignFinder Agent", version="1.17.14", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ResolveRequest(BaseModel):
    uid: str
    action: str
    anchors: list | None = None


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/status")
def status():
    from app.poller import get_poller_state
    state = get_poller_state()
    return {
        "running": state.get("running", False),
        "last_poll": state.get("last_poll"),
        "last_poll_count": state.get("last_poll_count", 0),
        "queue_count": state.get("queue_count", 0),
        "error": state.get("error"),
        "imap_configured": bool(load_mail_config()["imap_host"]),
    }


@app.post("/poll-now")
async def poll_now():
    if not load_mail_config()["imap_host"]:
        raise HTTPException(status_code=503, detail="IMAP не настроен")
    from app.poller import get_poller_state, run_one_poll
    if get_poller_state().get("running"):
        return {"status": "already_running"}
    # Запустить опрос в фоне, не ждать завершения (иначе таймаут прокси 30с)
    asyncio.get_event_loop().run_in_executor(None, run_one_poll)
    return {"status": "started"}


@app.get("/queue")
def get_queue():
    from app.queue_index import load_queue
    return load_queue()


@app.get("/queue/{uid}")
def get_queue_item(uid: str):
    from app.queue_index import get_item, get_original_pdfs, get_signed_pdfs
    item = get_item(uid)
    if not item:
        raise HTTPException(status_code=404, detail=f"UID {uid} не найден")
    return {"item": item, "signed_pdfs": get_signed_pdfs(uid),
            "original_pdfs": get_original_pdfs(uid)}


@app.post("/resolve")
async def resolve(req: ResolveRequest):
    if not load_mail_config()["imap_host"]:
        raise HTTPException(status_code=503, detail="IMAP не настроен")
    try:
        from app.mailbox import do_resolve
        result = await asyncio.get_event_loop().run_in_executor(
            None, do_resolve, req.uid, req.action, req.anchors
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("resolve error")
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.get("/log")
def get_log(n: int = 50, light: str | None = None):
    from app.activity_log import read_last_n
    filt = None
    if light:
        def filt(entry):
            return any(p.get("light") == light for p in entry.get("pdfs", []))
    return {"entries": read_last_n(n=n, filter_fn=filt)}
