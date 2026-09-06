from pydantic import BaseModel


class RouterSummary(BaseModel):
    router_id: str
    name: str
    hotspot_network: str
