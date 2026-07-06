import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.scan_cycles import bagfilter_cycle, gct_cycle, vrm_cycle
from app.scan_cycles.sensor_ingestion import sensor_vals


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        # Sensor ingestion
        asyncio.create_task(sensor_vals(), name="sensor_vals"),

        # Bagfilter cycle
        asyncio.create_task(bagfilter_cycle.running(), name="bagfilter_running"),
        asyncio.create_task(bagfilter_cycle.alarm(),   name="bagfilter_alarm"),

        # GCT cycle
        asyncio.create_task(gct_cycle.running(),    name="gct_running"),
        asyncio.create_task(gct_cycle.alarm(),      name="gct_alarm"),
        asyncio.create_task(gct_cycle.trip_reset(), name="gct_trip_reset"),

        # VRM cycle
        asyncio.create_task(vrm_cycle.run_sequence(), name="vrm_run_sequence"),
        asyncio.create_task(vrm_cycle.alarm(),        name="vrm_alarm"),
        asyncio.create_task(vrm_cycle.trip_reset(),   name="vrm_trip_reset"),
    ]

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="GCT SCADA Simulator", lifespan=lifespan)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}
