import logging
import sys
from app.db import Base, engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

def init_db():
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized. No preloaded cases seeded.")

if __name__ == "__main__":
    init_db()
