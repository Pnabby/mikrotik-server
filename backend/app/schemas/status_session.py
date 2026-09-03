from pydantic import BaseModel

from app.schemas.routers import RouterSummary


class StatusSessionResponse(BaseModel):
    username: str | None
    current_device_ip: str | None
    current_device_mac: str | None
    selected_router: RouterSummary
    routers: list[RouterSummary]
