from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(24), default="upload")  # upload | public
    source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_page: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="uploaded", index=True)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)
    current_frame: Mapped[int] = mapped_column(Integer, default=0)
    processed_frames: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_frame_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_vehicle_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    processed_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    spaces: Mapped[list["ParkingSpace"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    samples: Mapped[list["DetectionSample"]] = relationship(back_populates="video", cascade="all, delete-orphan")


class ParkingSpace(Base):
    __tablename__ = "parking_spaces"
    __table_args__ = (Index("ix_parking_spaces_video", "video_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("video_jobs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    polygon_json: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), default="unknown")  # unknown | occupied | free
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    video: Mapped[VideoJob] = relationship(back_populates="spaces")


class DetectionSample(Base):
    __tablename__ = "detection_samples"
    __table_args__ = (Index("ix_detection_samples_video_time", "video_id", "timestamp_seconds"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("video_jobs.id", ondelete="CASCADE"), index=True)
    frame_number: Mapped[int] = mapped_column(Integer)
    timestamp_seconds: Mapped[float] = mapped_column(Float)
    vehicle_count: Mapped[int] = mapped_column(Integer)
    tracked_vehicle_count: Mapped[int] = mapped_column(Integer)
    mean_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    video: Mapped[VideoJob] = relationship(back_populates="samples")


class OccupancySample(Base):
    __tablename__ = "occupancy_samples"
    __table_args__ = (Index("ix_occupancy_samples_video_time", "video_id", "timestamp_seconds"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("video_jobs.id", ondelete="CASCADE"), index=True)
    space_id: Mapped[str] = mapped_column(ForeignKey("parking_spaces.id", ondelete="CASCADE"), index=True)
    timestamp_seconds: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class Stream(Base):
    """A live source: an RTSP/HTTP camera URL or an uploaded video played back in realtime."""

    __tablename__ = "streams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default="url")  # url | video
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_id: Mapped[str | None] = mapped_column(
        ForeignKey("video_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="idle")  # idle | starting | live | error
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    spaces_json: Mapped[str] = mapped_column(Text, default="[]")  # [{name, polygon}, ...]
    snapshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_fps: Mapped[int] = mapped_column(Integer, default=4)
    subscriber_count: Mapped[int] = mapped_column(Integer, default=0)
    frames_delivered: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_frame_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSetting(Base):
    """Persistent key/value settings that override env defaults (model config, plan, integrations)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base):
    """Operator identity. api_key_hash stores sha256(raw key); the raw key is returned once."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(24), default="operator")  # admin | operator | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActivityEvent(Base):
    """Audit/activity trail: what users have been doing (uploads, runs, edits, admin changes)."""

    __tablename__ = "activity_events"
    __table_args__ = (Index("ix_activity_events_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    action: Mapped[str] = mapped_column(String(48), index=True)
    object_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
