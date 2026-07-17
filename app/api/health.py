from fastapi import APIRouter
from app.core import health as core_health

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness():
    return core_health.get_liveness()


@router.get("/ready")
async def readiness():
    return core_health.get_readiness_status()


@router.get("/startup")
async def startup_status():
    return core_health.get_startup_status()


@router.get("/")
async def health_check():
    liveness = core_health.get_liveness()
    readiness = core_health.get_readiness_status()
    startup = core_health.get_startup_status()
    return {
        "alive": liveness["status"] == "alive",
        "ready": readiness["ready"],
        "startup_elapsed_s": startup.get("elapsed_s", 0),
        "models_loaded": startup.get("models_loaded", 0),
        "phases_completed": sum(1 for p in startup.get("phases", []) if p.get("status") == "passed"),
        "phases_total": len(startup.get("phases", [])),
        "errors": startup.get("errors", [])[:5],
        "timestamp": liveness["timestamp"],
    }


@router.get("/dependencies")
async def dependency_health():
    return core_health.get_dependency_health()


@router.get("/models")
async def model_status():
    return core_health.get_model_status()
