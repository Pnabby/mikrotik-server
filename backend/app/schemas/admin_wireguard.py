import ipaddress
import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WireGuardInterface(BaseModel):
    name: str
    public_key: str
    listen_port: int
    mtu: int
    disabled: bool
    running: bool


class WireGuardPeer(BaseModel):
    id: str
    name: str
    interface: str
    public_key: str
    allowed_addresses: str
    endpoint: str
    current_endpoint: str
    last_handshake_seconds: int | None
    rx_bytes: int
    tx_bytes: int
    keepalive_seconds: int
    disabled: bool
    dynamic: bool
    managed_by: Literal["wireguard", "bth", "dynamic"]
    can_manage: bool
    can_export: bool = False
    allow_lan: bool | None = None
    expires: str | None = None
    bth_active: bool | None = None


class WireGuardCloud(BaseModel):
    vpn_status: str = "Unknown"
    vpn_dns_name: str = ""
    vpn_port: int = 0
    dns_name: str = ""
    public_address: str = ""
    relay_ipv4_status: str = ""
    relay_ipv6_status: str = ""


class WireGuardSnapshot(BaseModel):
    router_id: str
    router_name: str
    generated_at: datetime
    interfaces: list[WireGuardInterface]
    peers: list[WireGuardPeer]
    cloud: WireGuardCloud | None
    warnings: list[str]


class WireGuardPeerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["reset", "enable", "disable", "keepalive", "allow_lan"]
    keepalive_seconds: int | None = Field(default=None, ge=0, le=65535, strict=True)
    allow_lan: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_action_fields(self):
        if (self.action == "keepalive") != (self.keepalive_seconds is not None):
            raise ValueError("Keepalive actions require only a keepalive interval.")
        if (self.action == "allow_lan") != (self.allow_lan is not None):
            raise ValueError("LAN access actions require only an access value.")
        return self


class WireGuardActionResult(BaseModel):
    message: str
    queued: bool = False


def _single_line(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise ValueError("A single-line value is required.")
    value = value.strip()
    if not value:
        raise ValueError("A nonempty single-line value is required.")
    return value


def _networks(value: str) -> str:
    parts = [item.strip() for item in value.split(",")]
    if not 1 <= len(parts) <= 16 or any(not item for item in parts):
        raise ValueError("Enter one to sixteen CIDR addresses.")
    return ",".join(str(ipaddress.ip_network(item, strict=False)) for item in parts)


class ClientPeerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    client_allowed_addresses: str = Field(default="0.0.0.0/0,::/0", max_length=1024)
    client_dns: str = Field(default="", max_length=255)

    _name = field_validator("name")(_single_line)
    _allowed = field_validator("client_allowed_addresses")(_networks)

    @field_validator("client_dns")
    @classmethod
    def validate_dns(cls, value: str) -> str:
        if not value.strip():
            return ""
        parts = value.split(",")
        if len(parts) > 3:
            raise ValueError("Use up to three DNS server IP addresses.")
        return ",".join(str(ipaddress.ip_address(item.strip())) for item in parts)


class BthPeerCreate(ClientPeerCreate):
    kind: Literal["bth"]
    allow_lan: bool = Field(default=True, strict=True)
    expires_days: int | None = Field(default=None, ge=1, le=3650, strict=True)

    @model_validator(mode="after")
    def one_dns_server(self):
        if "," in self.client_dns:
            raise ValueError("Back to Home accepts one DNS server IP address.")
        return self


class StaticPeerCreate(ClientPeerCreate):
    kind: Literal["wireguard"]
    interface: str = Field(min_length=1, max_length=255)
    client_addresses: str = Field(min_length=1, max_length=255)
    client_endpoint: str = Field(min_length=1, max_length=255)
    client_keepalive: int = Field(default=25, ge=0, le=65535, strict=True)

    _interface = field_validator("interface")(_single_line)

    @field_validator("client_addresses")
    @classmethod
    def validate_client_addresses(cls, value: str) -> str:
        parts = [ipaddress.ip_network(item.strip(), strict=True) for item in value.split(",")]
        if not 1 <= len(parts) <= 2 or len({item.version for item in parts}) != len(parts):
            raise ValueError("Use one IPv4 address and/or one IPv6 address.")
        if any(
            item.prefixlen != item.max_prefixlen
            or item.network_address.is_unspecified
            or item.network_address.is_multicast
            for item in parts
        ):
            raise ValueError("Use individual client addresses with /32 or /128 masks.")
        return ",".join(str(item) for item in parts)

    @field_validator("client_endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        value = _single_line(value)
        try:
            address = ipaddress.ip_address(value.strip("[]"))
            if address.is_unspecified or address.is_multicast:
                raise ValueError("Enter a reachable endpoint.")
            return str(address)
        except ValueError:
            if not re.fullmatch(
                r"(?=.{1,253}\.?$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
                r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?",
                value,
            ) or re.fullmatch(r"[0-9.]+", value):
                raise ValueError("Enter an IP address or hostname without a port.") from None
            return value


WireGuardPeerCreate = Annotated[BthPeerCreate | StaticPeerCreate, Field(discriminator="kind")]


class WireGuardCreateResult(WireGuardActionResult):
    peer_id: str | None = None


class WireGuardClientConfig(BaseModel):
    peer_id: str
    name: str
    config: str = Field(repr=False)


class RouterRestartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(min_length=1, max_length=255)
