import threading
from flask import current_app

def run_in_background(fn, *args, **kwargs):
    def _target():
        try:
            fn(*args, **kwargs)
        except Exception:
            current_app.logger.exception("❌ Background task failed")
    t = threading.Thread(target=_target, daemon=True)
    t.start()
