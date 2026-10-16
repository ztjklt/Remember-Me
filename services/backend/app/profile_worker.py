"""Recover automatic jobs with bounded retries; explicit jobs require retry."""
import time
from sqlalchemy import select
from .config import get_settings
from .db import Database
from .models import ProfileRefresh, utcnow
from .profiles import ProfileClient, run_profile_once

def main():
    settings=get_settings(); db=Database(settings.database_url)
    with db.session() as session:
        from .automatic_profiles import automatic_retry
        for job in session.scalars(select(ProfileRefresh).where(ProfileRefresh.status=='running')):
            if not automatic_retry(job, RuntimeError('interrupted'), interrupted=True):
                job.status, job.error, job.updated_at = 'failed', '处理已中断，请重试。', utcnow()
        session.commit()
    client=ProfileClient(settings.ai_core_url,settings.ai_timeout_seconds)
    try:
        while True:
            if run_profile_once(db,client) is None: time.sleep(1)
    finally: db.dispose()

if __name__=='__main__': main()
