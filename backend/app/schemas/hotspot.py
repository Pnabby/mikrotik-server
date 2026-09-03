from pydantic import BaseModel, SecretStr


class DeviceSession(BaseModel):
    session_id: str
    device_name: str
    device_type: str
    mac_address: str | None = None
    ip_address: str | None = None
    login_by: str | None = None
    uptime: str | None = None
    server: str | None = None
    bytes_in: int
    bytes_out: int
    bytes_total: int


class HotspotStatusResponse(BaseModel):
    router_id: str
    router_name: str
    username: str
    profile: str | None = None
    disabled: bool
    logged_in_date: str | None = None
    expiry_date: str | None = None
    total_data_used_bytes: int
    total_data_used: str
    total_data_left_bytes: int | None = None
    total_data_left: str
    data_limit_bytes: int | None = None
    connected_devices_count: int
    connected_devices: list[DeviceSession]


class HotspotLookupRequest(BaseModel):
    username: str
    password: SecretStr


class DeviceLogoutResponse(BaseModel):
    router_id: str
    router_name: str
    username: str
    session_id: str
    removed: bool
    detail: str
