import time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent/'.env')
from leadpilot import db, pipeline
if __name__=='__main__':
    db.init(); print('Worker running. Ctrl+C stops safely between stages. Secrets are never logged.')
    try:
        while True:
            try: pipeline.tick()
            except Exception as exc: print('Worker error:',type(exc).__name__)
            time.sleep(2)
    except KeyboardInterrupt: print('\nWorker stopped. Progress is saved.')
