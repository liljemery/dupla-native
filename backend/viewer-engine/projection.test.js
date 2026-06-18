const assert = require("node:assert/strict");
const test = require("node:test");

const {
  oldBboxAffineProjection,
  projectClashesToBoxes,
} = require("./projection");

const SHOT_W = 3000;
const SHOT_H = 2200;
const CLASH = {
  bounds_mm: [669910, 479910, 670090, 480090],
  centroid_mm: [670000, 480000],
  clash_type: "HARD",
};

class Vector3 {
  constructor(x, y, z) {
    this.x = x;
    this.y = y;
    this.z = z;
  }
}

function modelSpaceWorldToClient(point) {
  const pxPerMm = 59 / 180;
  return {
    x: SHOT_W / 2 + (point.x - 670000) * pxPerMm,
    y: SHOT_H / 2 - (point.y - 480000) * pxPerMm,
  };
}

function paperSpaceWorldToClient(point) {
  return {
    x: 150 + (point.x / 36.27) * (SHOT_W * 0.90),
    y: 196 + (1 - point.y / 24.28) * (SHOT_H * 0.82),
  };
}

function boxSize(box) {
  return {
    width: Math.abs(box.x1 - box.x0),
    height: Math.abs(box.y1 - box.y0),
  };
}

test("projects measured clash as a small in-bounds model-space marker", () => {
  const [box] = projectClashesToBoxes([CLASH], {
    THREE: { Vector3 },
    unitFactorMm: 1,
    worldToClient: modelSpaceWorldToClient,
  });

  const size = boxSize(box);
  assert.ok(size.width < SHOT_W * 0.10, `width ${size.width} should be < 10% viewport`);
  assert.ok(size.height < SHOT_H * 0.10, `height ${size.height} should be < 10% viewport`);
  assert.ok(box.cx >= 0 && box.cx <= SHOT_W, `cx ${box.cx} should be in bounds`);
  assert.ok(box.cy >= 0 && box.cy <= SHOT_H, `cy ${box.cy} should be in bounds`);
});

test("old bbox affine reproduces the oversized paper-space marker failure", () => {
  const paperSpaceModelBBox = {
    min: { x: 0, y: 0 },
    max: { x: 36.27, y: 24.28 },
  };

  const [oldBox] = oldBboxAffineProjection([CLASH], paperSpaceModelBBox, paperSpaceWorldToClient);
  const size = boxSize(oldBox);

  assert.ok(size.width > SHOT_W * 0.80, `old width ${size.width} should span the viewport`);
  assert.ok(size.height > SHOT_H * 0.70, `old height ${size.height} should span the viewport`);
  assert.ok(oldBox.cx >= 0 && oldBox.cx <= SHOT_W, `old cx ${oldBox.cx} should be in bounds`);
  assert.ok(oldBox.cy >= 0 && oldBox.cy <= SHOT_H, `old cy ${oldBox.cy} should be in bounds`);
});
