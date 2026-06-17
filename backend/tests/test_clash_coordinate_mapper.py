from app.services.clash_coordinate_mapper import CoordinateMapper


def test_identity_mapper() -> None:
    mapper = CoordinateMapper()
    assert mapper.map_point(1, 2, 3) == {"x": 1.0, "y": 2.0, "z": 3.0}


def test_scale_and_offset() -> None:
    mapper = CoordinateMapper(scale=2, offset_x=10, offset_y=-5, offset_z=3)
    assert mapper.map_point(1, 2, 4) == {"x": 12.0, "y": -1.0, "z": 11.0}


def test_unit_factor() -> None:
    mapper = CoordinateMapper(unit_factor=0.001)
    assert mapper.map_point(1000, 2000, 3000) == {"x": 1.0, "y": 2.0, "z": 3.0}


def test_invert_y() -> None:
    mapper = CoordinateMapper(invert_y=True)
    assert mapper.map_point(10, 20)["y"] == -20


def test_rotation_90_degrees() -> None:
    mapper = CoordinateMapper(rotation_degrees=90)
    mapped = mapper.map_point(1, 0)
    assert round(mapped["x"], 6) == 0
    assert round(mapped["y"], 6) == 1


def test_bbox_negative_coordinates_keeps_order() -> None:
    mapper = CoordinateMapper(offset_x=5, offset_y=5)
    bbox = mapper.map_bbox({"min_x": -10, "min_y": -5, "max_x": 2, "max_y": 3})
    assert bbox["min_x"] < bbox["max_x"]
    assert bbox["min_y"] < bbox["max_y"]


def test_bbox_after_rotation_keeps_min_less_than_max() -> None:
    mapper = CoordinateMapper(rotation_degrees=90)
    bbox = mapper.map_bbox({"min_x": 0, "min_y": 0, "max_x": 10, "max_y": 20})
    assert bbox["min_x"] < bbox["max_x"]
    assert bbox["min_y"] < bbox["max_y"]
