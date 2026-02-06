from __future__ import annotations

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = "sqlite:///./yt_analytics.db"
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def _ensure_column(table_name: str, column_name: str, column_sql: str) -> None:
    inspector = inspect(engine)
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    if column_name in existing:
        return
    with engine.begin() as conn:
        conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_column("channel", "avatar_url", "TEXT")
    _ensure_column("channel", "subscriber_count", "INTEGER")
    _ensure_column("channel", "delta_total_views", "INTEGER")
    _ensure_column("channel", "delta_avg_views", "INTEGER")
    _ensure_column("channel", "delta_median_views", "INTEGER")
    _ensure_column("channel", "delta_top_video_views", "INTEGER")
    _ensure_column("channel", "delta_total_likes", "INTEGER")
    _ensure_column("channel", "delta_total_comments", "INTEGER")
    _ensure_column("video", "thumbnail_url", "TEXT")
    _ensure_column("video", "comment_count", "INTEGER")
    _ensure_column("video", "view_delta", "INTEGER")
    _ensure_column("video", "like_delta", "INTEGER")
    _ensure_column("video", "comment_delta", "INTEGER")


def get_session():
    with Session(engine) as session:
        yield session
