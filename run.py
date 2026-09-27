"""One-command local launcher: dashboard and durable worker in one process."""
import os, subprocess, sys, threading, time
from pathlib import Path
ROOT=Path(__file__).parent
os.chdir(ROOT)
if not (ROOT/'.env').exists():subprocess.run([sys.executable,'setup_local.py'],check=True)
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
from app import create_app
from leadpilot import pipeline
from waitress import serve
app=create_app()
def worker_loop():
    while True:
        try:pipeline.tick()
        except Exception as exc:print('Background task:',type(exc).__name__)
        time.sleep(2)
if __name__=='__main__':
    threading.Thread(target=worker_loop,daemon=True,name='leadpilot-worker').start()
    print('LeadPilot v2: http://127.0.0.1:'+os.getenv('PORT','8000'))
    print('The worker is included. Sign in with ADMIN_PASSWORD from .env.')
    serve(app,host=os.getenv('BIND_HOST','127.0.0.1'),port=int(os.getenv('PORT','8000')),threads=8)
