"""One local background profile worker. Recovery never resends a crashed call."""
import time
from sqlalchemy import update
from .config import get_settings
from .db import Database
from .models import ProfileRefresh, utcnow
from .profiles import ProfileClient, run_profile_once

def main():
    settings=get_settings(); db=Database(settings.database_url)
    with db.session() as session:
        session.execute(update(ProfileRefresh).where(ProfileRefresh.status=='running').values(
            status='failed', error='处理已中断，请明确重试。', updated_at=utcnow()))
        session.commit()
    client=ProfileClient(settings.ai_core_url,settings.ai_timeout_seconds)
    try:
        while True:
            if run_profile_once(db,client) is None: time.sleep(1)
    finally: db.dispose()

if __name__=='__main__': main()
