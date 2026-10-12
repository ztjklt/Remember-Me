"""Existing client API plus deployment-only, authenticated synchronous ticks."""
import hmac
import os
import threading
from fastapi import APIRouter, Header, HTTPException
from app.main import app
from app.worker import build_worker
from app.profiles import run_profile_once


def create_tick_router(database, settings, profile_client, token):
    if len(token) < 32:
        raise ValueError('A worker credential is required.')
    worker = build_worker(database, settings)
    lock = threading.Lock()
    router = APIRouter(prefix='/internal/jobs', include_in_schema=False)
    def authorize(authorization):
        if not hmac.compare_digest((authorization or '').encode(), ('Bearer ' + token).encode()):
            raise HTTPException(status_code=401, detail='Worker authorization required.')
        if not lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail='A tick is already running.')
    @router.post('/processing-tick')
    def processing_tick(authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            worker.run_once()
            return {'tick_completed': True}
        finally:
            lock.release()
    @router.post('/profile-tick')
    def profile_tick(authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            run_profile_once(database, profile_client)
            return {'tick_completed': True}
        finally:
            lock.release()
    return router


app.include_router(create_tick_router(app.state.database, app.state.settings,
    app.state.profile_client, os.environ.get('CLOUDBASE_WORKER_TOKEN', '')))
