from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Field, SQLModel


class Channel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    url: str = Field(index=True, unique=True)
    avatar_url: str | None = None
    subscriber_count: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_refreshed_at: datetime | None = None
    last_error: str | None = None
    delta_total_views: int | None = None
    delta_avg_views: int | None = None
    delta_median_views: int | None = None
    delta_top_video_views: int | None = None
    delta_total_likes: int | None = None
    delta_total_comments: int | None = None


class Video(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="channel.id", index=True)
    title: str
    url: str = Field(index=True)
    upload_date: date | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    view_delta: int | None = None
    like_delta: int | None = None
    comment_delta: int | None = None
    thumbnail_url: str | None = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class ChannelSnapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="channel.id", index=True)
    captured_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    total_views: int = 0
    total_likes: int = 0
    total_comments: int = 0
    subscriber_count: int | None = None
