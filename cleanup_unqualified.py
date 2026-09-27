"""Remove old pre-research candidates that fail their discovery's basic rules.

Stop LeadPilot before running. Creates a SQLite backup before any deletion.
Research results and leads with any email history are preserved.
"""
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')
from leadpilot import db, excel, rules
from leadpilot.lock import pipeline_lock


def cleanup():
    if not db.DB_PATH.exists():
        raise ValueError('No existing database found. Run this from your installed project.')
    with pipeline_lock() as acquired:
        if not acquired:
            raise ValueError('Stop run.py and any worker.py process before cleanup.')
        with db.connect() as c:
            rows=c.execute("""SELECT l.*, r.config, r.created AS run_created
                FROM leads l JOIN runs r ON r.id=l.run_id
                WHERE l.status IN ('initial','rejected','research_pending')
                AND NOT EXISTS (SELECT 1 FROM emails e WHERE e.lead_id=l.id)""").fetchall()
            removals=[]
            for lead in rows:
                if json.loads(lead['research'] or '{}'): continue
                when=datetime.fromtimestamp(lead['run_created'],timezone.utc)
                if rules.basic(json.loads(lead['raw']),json.loads(lead['config']),now=when):
                    removals.append((lead['id'],lead['run_id']))
        if not removals:
            print('No old unqualified pre-research records to remove.')
            return 0
        folder=db.DB_PATH.parent/'backups';folder.mkdir(exist_ok=True)
        backup=folder/f'leadpilot-before-filter-{time.time_ns()}.sqlite3'
        with sqlite3.connect(str(db.DB_PATH)) as src, sqlite3.connect(str(backup)) as dst:
            src.backup(dst)
        with db.connect() as c:
            c.executemany('DELETE FROM leads WHERE id=?',[(lid,) for lid,_ in removals])
        for rid in sorted({rid for _,rid in removals}):
            excel.mark(rid)
            excel.save(rid)
        print(f'Removed {len(removals)} unqualified records. Backup: {backup}')
        print('Download Excel again for an updated copy. Research and email history were preserved.')
        return len(removals)


if __name__=='__main__':
    cleanup()
