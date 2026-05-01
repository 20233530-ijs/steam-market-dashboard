import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from run_analysis_pipeline import run_pipeline


scheduler = BlockingScheduler()


def shutdown_scheduler(signum=None, frame=None):
    print(f"Shutdown signal received at {datetime.now()}.")

    if scheduler.running:
        scheduler.shutdown(wait=False)

    sys.exit(0)


def collect_data():
    print(f"Scheduled pipeline started at {datetime.now()}.")
    try:
        run_pipeline(
            limit=None,
            max_pages=3,
            page_size=100,
            replace_existing=False,
        )
        print(f"Scheduled pipeline completed at {datetime.now()}.")
    except KeyboardInterrupt:
        print("Scheduled pipeline interrupted.")
        raise
    except Exception as exc:
        print(f"Scheduled pipeline failed: {exc}")


scheduler.add_job(collect_data, "cron", hour=0, minute=0)

signal.signal(signal.SIGINT, shutdown_scheduler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, shutdown_scheduler)

print("Scheduler started. The full Steam analysis pipeline runs every day at 00:00.")
print("Press Ctrl+C to stop.")

try:
    collect_data()
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    shutdown_scheduler()
