"""Process-scoped OS lock, released automatically on exit/crash; works on Windows."""
from contextlib import contextmanager
from . import db
@contextmanager
def pipeline_lock():
    p=db.DB_PATH.parent/'worker.lock'; p.parent.mkdir(parents=True,exist_ok=True)
    f=open(p,'a+b'); f.seek(0,2)
    if f.tell()==0: f.write(b'0'); f.flush()
    f.seek(0)
    locked=False
    try:
        try:
            if __import__('os').name=='nt':
                import msvcrt; msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl; fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
        except (OSError,BlockingIOError): pass
        yield locked
    finally:
        if locked:
            f.seek(0)
            if __import__('os').name=='nt':
                import msvcrt; msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl; fcntl.flock(f,fcntl.LOCK_UN)
        f.close()
