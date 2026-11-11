# app/routers/system.py
import time
from fastapi import APIRouter, status

system_router = APIRouter(tags=["System / Operations"])

# Track startup time to calculate uptime
START_TIME = time.time()

@system_router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Liveness probe for Kubernetes, AWS ALBs, or Docker healthchecks.
    Ensures the application process is running and responding to HTTP traffic.
    """
    return {"status": "healthy"}

@system_router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """
    Readiness probe. Checks downstream dependencies like databases or caches.
    Returns 503 if a core dependency is down so traffic stops routing here.
    """
    # Example logic:
    # is_db_up = await check_database_connection()
    # if not is_db_up:
    #     raise HTTPException(status_code=503, detail="Database unreachable")

    return {"status": "ready"}

@system_router.get("/metrics")
async def app_metrics():
    """
    Basic internal telemetry or stats (uptime, version data).
    Can also be swapped out later for Prometheus or OpenTelemetry hooks.
    """
    return {
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "environment": "production"
    }
