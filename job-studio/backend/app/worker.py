from __future__ import annotations

import logging
import time

from app.config import get_settings
from app.db import SessionLocal
from app.services.deployment_reconciler import process_outbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("studio.worker")


def main() -> None:
    get_settings()
    logger.info("Studio reconciler started")
    while True:
        db = SessionLocal()
        try:
            process_outbox(db)
        except Exception:
            logger.exception("Reconciler loop failed")
            db.rollback()
        finally:
            db.close()
        time.sleep(5)


if __name__ == "__main__":
    main()
