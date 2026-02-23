"""
Options Bot — Entry Point
Starts the FastAPI backend server.
Trading strategies will be added in later prompts.
"""

import logging
import uvicorn
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from config import API_HOST, API_PORT, LOG_LEVEL, LOG_FORMAT

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("options-bot")


def main():
    logger.info("Options Bot — Starting backend server...")
    logger.info(f"API will be available at http://{API_HOST}:{API_PORT}")
    logger.info(f"Swagger docs at http://{API_HOST}:{API_PORT}/docs")

    uvicorn.run(
        "backend.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
