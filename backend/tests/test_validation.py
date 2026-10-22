import pytest
from pydantic import ValidationError
from app.schemas import SpaceCreate


def test_valid_normalized_polygon():
    polygon = SpaceCreate(name="A-01", polygon=[[0.1, 0.1], [0.2, 0.1], [0.2, 0.3], [0.1, 0.3]])
    assert len(polygon.polygon) == 4


def test_polygon_coordinates_outside_frame_are_rejected():
    with pytest.raises(ValidationError):
        SpaceCreate(name="A-01", polygon=[[0.1, 0.1], [1.2, 0.1], [0.2, 0.3]])


def test_polygon_requires_three_unique_points():
    with pytest.raises(ValidationError):
        SpaceCreate(name="A-01", polygon=[[0.1, 0.1], [0.1, 0.1], [0.1, 0.1]])
