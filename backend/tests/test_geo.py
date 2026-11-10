"""Reprojection through the vectorised Shapely 2 API."""

from __future__ import annotations

import pytest
from shapely.geometry import MultiPolygon, Point, Polygon

from app.geo import UTM33, WGS84, reproject_geometry, utm33_to_wgs84

# A parcel-sized square near Leipzig, with a hole, in EPSG:25833.
SQUARE = Polygon(
    [(323000, 5690000), (323050, 5690000), (323050, 5690040), (323000, 5690040)],
    [[(323010, 5690010), (323020, 5690010), (323020, 5690020)]],
)


def test_every_vertex_lands_where_the_point_transform_puts_it():
    projected = reproject_geometry(SQUARE, UTM33, WGS84)

    assert len(projected.interiors) == 1
    for before, after in zip(SQUARE.exterior.coords, projected.exterior.coords):
        assert after == pytest.approx(utm33_to_wgs84(*before), abs=1e-12)
    # always_xy: longitude first, so Saxony reads (12.x, 51.x).
    lon, lat = projected.exterior.coords[0]
    assert 11.8 < lon < 15.1 and 50.1 < lat < 51.7


def test_a_round_trip_returns_the_same_parcel():
    multi = MultiPolygon([SQUARE, Polygon([(324000, 5691000), (324010, 5691000), (324010, 5691010)])])
    back = reproject_geometry(reproject_geometry(multi, UTM33, WGS84), WGS84, UTM33)

    assert back.geom_type == "MultiPolygon"
    assert back.equals_exact(multi, 1e-6)


def test_a_height_is_carried_through_rather_than_dropped():
    projected = reproject_geometry(Point(323000, 5690000, 120.5), UTM33, WGS84)

    assert projected.has_z
    assert projected.z == 120.5


def test_an_empty_geometry_stays_empty():
    assert reproject_geometry(Polygon(), UTM33, WGS84).is_empty
