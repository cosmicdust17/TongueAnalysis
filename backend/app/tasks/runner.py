import asyncio
import logging
from app.services.analysis_service import process_one

async def run_worker(stop):
    while not stop.is_set():
        try:
            worked = await asyncio.to_thread(process_one)
        except Exception:
            logging.exception('Worker database poll failed')
            worked = False
        if not worked:
            try:
                await asyncio.wait_for(stop.wait(), timeout=.5)
            except asyncio.TimeoutError:
                pass
