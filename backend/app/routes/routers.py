from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.integrations.mikrotik.registry import iter_routers
from app.schemas.routers import RouterSummary

router = APIRouter(prefix="/api/routers", tags=["routers"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=list[RouterSummary])
def list_routers(session: SessionDependency) -> list[RouterSummary]:
    return [
        RouterSummary(
            router_id=item.router_id,
            name=item.name,
            hotspot_network=item.hotspot_network,
        )
        for item in iter_routers(session)
    ]
