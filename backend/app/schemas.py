from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator
import json


class VideoJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    original_name: str
    source_type: str
    source_id: str | None
    source_title: str | None
    source_page: str | None
    status: str
    progress_percent: float
    current_frame: int
    processed_frames: int
    width: int | None
    height: int | None
    fps: float | None
    source_frame_count: int | None
    duration_seconds: float | None
    max_vehicle_count: int | None
    avg_confidence: float | None
    error_message: str | None
    model_name: str | None
    created_at: datetime
    completed_at: datetime | None
    preview_url: str | None = None
    original_url: str | None = None
    annotated_url: str | None = None
    configured_spaces: int = 0


class SpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    polygon: list[list[float]] = Field(min_length=3, max_length=30)

    @field_validator("polygon")
    @classmethod
    def validate_polygon(cls, points: list[list[float]]) -> list[list[float]]:
        if any(len(point) != 2 for point in points):
            raise ValueError("Each polygon point must contain x and y")
        if any(not (0 <= float(v) <= 1) for point in points for v in point):
            raise ValueError("Normalized polygon coordinates must be between 0 and 1")
        if len({(round(float(p[0]), 6), round(float(p[1]), 6)) for p in points}) < 3:
            raise ValueError("Polygon must have at least three unique points")
        return points


class SpaceOut(BaseModel):
    id: str
    video_id: str
    name: str
    polygon: list[list[float]]
    state: str
    confidence: float | None
    last_seen_seconds: float | None


class SourceOut(BaseModel):
    id: str
    title: str
    creator: str
    landing_page: str
    description: str
    duration_seconds: int
    resolution: str
    license_label: str


class PublicSourceList(BaseModel):
    items: list[SourceOut]
    note: str


class DetectionPoint(BaseModel):
    timestamp_seconds: float
    frame_number: int
    vehicle_count: int
    tracked_vehicle_count: int
    mean_confidence: float | None


class OccupancyPoint(BaseModel):
    space_id: str
    space_name: str
    timestamp_seconds: float
    state: str
    confidence: float | None


class OccupancySeries(BaseModel):
    items: list[OccupancyPoint]


class DashboardSummary(BaseModel):
    total_videos: int
    completed_videos: int
    processing_videos: int
    latest_video_id: str | None
    latest_video_name: str | None
    latest_status: str | None
    vehicles_in_latest_sample: int | None
    peak_vehicles_observed: int | None
    configured_spaces: int
    occupied_spaces: int
    free_spaces: int
    unknown_spaces: int
    occupancy_percent: float | None
    latest_confidence: float | None
    has_data: bool


class StreamSpace(BaseModel):
    """A calibrated bay on a live stream (same normalised polygon rules as video spaces)."""

    name: str = Field(min_length=1, max_length=80)
    polygon: list[list[float]] = Field(min_length=3, max_length=30)

    @field_validator("polygon")
    @classmethod
    def validate_polygon(cls, points: list[list[float]]) -> list[list[float]]:
        if any(len(point) != 2 for point in points):
            raise ValueError("Each polygon point must contain x and y")
        if any(not (0 <= float(v) <= 1) for point in points for v in point):
            raise ValueError("Normalized polygon coordinates must be between 0 and 1")
        if len({(round(float(p[0]), 6), round(float(p[1]), 6)) for p in points}) < 3:
            raise ValueError("Polygon must have at least three unique points")
        return points


class StreamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="url", pattern="^(url|video)$")
    url: str | None = None
    video_id: str | None = None
    target_fps: int = Field(default=4, ge=1, le=15)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class StreamPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = None
    video_id: str | None = None
    enabled: bool | None = None
    target_fps: int | None = Field(default=None, ge=1, le=15)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class StreamSpacesSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spaces: list[StreamSpace] = Field(min_length=1, max_length=64)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="operator", pattern="^(admin|operator|viewer)$")


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, pattern="^(admin|operator|viewer)$")
    is_active: bool | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str
    role: str
    is_active: bool
    has_api_key: bool = False
    created_at: datetime
    last_login_at: datetime | None
