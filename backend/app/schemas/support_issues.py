import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IssueCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=3, max_length=5000)
    room_number: str | None = Field(default=None, max_length=40)


class IssueUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    status: Literal["open", "attended"] | None = None
    reply: str | None = Field(default=None, min_length=1, max_length=5000)

    @model_validator(mode="after")
    def require_action(self):
        if self.status is None and self.reply is None:
            raise ValueError("Choose a status or write a reply.")
        return self


class IssueReplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message: str
    created_at: datetime


class IssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    router_id: str | None
    hostel_name: str
    room_number: str | None
    subject: str
    message: str
    status: Literal["open", "attended"]
    created_at: datetime
    attended_at: datetime | None
    replies: list[IssueReplyResponse]


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    total: int
    open_count: int


class IssueNotificationResponse(BaseModel):
    count: int
    items: list[IssueResponse]
