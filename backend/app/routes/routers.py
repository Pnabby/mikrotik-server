from fastapi import APIRouter

from app.integrations.mikrotik.registry import iter_routers
from app.schemas.routers import RouterSummary


router = APIRouter(prefix="/api/routers", tags=["routers"])


@router.get("", response_model=list[RouterSummary])
def list_routers() -> list[RouterSummary]:
    return [
        RouterSummary(
            router_id=item.router_id,
            name=item.name,
            hotspot_network=item.hotspot_network,
        )
        for item in iter_routers()
    ]
