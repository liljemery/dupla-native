(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DuplaProjection = factory();
  }
})(typeof window !== "undefined" ? window : globalThis, function () {
  function finiteNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function clashMmToModel(xMm, yMm, unitFactorMm) {
    const factor = finiteNumber(unitFactorMm) && unitFactorMm > 0 ? unitFactorMm : 1.0;
    return { x: Number(xMm) / factor, y: Number(yMm) / factor, z: 0 };
  }

  function applyPlacement(point, placement) {
    if (!placement || typeof point.applyMatrix4 !== "function") {
      return point;
    }
    return point.applyMatrix4(placement);
  }

  function projectPointMm(xMm, yMm, options) {
    const modelPoint = clashMmToModel(xMm, yMm, options.unitFactorMm);
    const vector = new options.THREE.Vector3(modelPoint.x, modelPoint.y, modelPoint.z);
    const placed = applyPlacement(vector, options.placementTransform);
    const screen = options.worldToClient(placed);
    return {
      model: { x: placed.x, y: placed.y, z: placed.z || 0 },
      screen: { x: screen.x, y: screen.y },
    };
  }

  function projectClashesToBoxes(clashes, options) {
    const boxes = [];
    const log = typeof options.log === "function" ? options.log : function () {};
    const unitFactorMm = finiteNumber(options.unitFactorMm) && options.unitFactorMm > 0
      ? options.unitFactorMm
      : 1.0;

    log("COORD_MODEL_SPACE unitFactorMm=" + unitFactorMm);

    for (const clash of clashes || []) {
      const bounds = clash && clash.bounds_mm;
      if (!bounds || bounds.length < 4) {
        continue;
      }

      const p0 = projectPointMm(bounds[0], bounds[1], { ...options, unitFactorMm });
      const p1 = projectPointMm(bounds[2], bounds[3], { ...options, unitFactorMm });
      log("COORD_PROJECT bounds_mm=" + JSON.stringify(bounds)
        + " model0=" + JSON.stringify(p0.model)
        + " model1=" + JSON.stringify(p1.model)
        + " screen0=" + JSON.stringify(p0.screen)
        + " screen1=" + JSON.stringify(p1.screen));

      let cx = null;
      let cy = null;
      if (clash.centroid_mm && clash.centroid_mm.length === 2) {
        const pc = projectPointMm(clash.centroid_mm[0], clash.centroid_mm[1], { ...options, unitFactorMm });
        log("COORD_PROJECT_CENTROID centroid_mm=" + JSON.stringify(clash.centroid_mm)
          + " model=" + JSON.stringify(pc.model)
          + " screen=" + JSON.stringify(pc.screen));
        cx = pc.screen.x;
        cy = pc.screen.y;
      }

      boxes.push({
        x0: p0.screen.x,
        y0: p0.screen.y,
        x1: p1.screen.x,
        y1: p1.screen.y,
        cx,
        cy,
        type: clash.clash_type,
      });
    }

    return boxes;
  }

  function oldBboxAffineProjection(clashes, modelBBox, worldToClient) {
    const xs = [];
    const ys = [];
    for (const clash of clashes || []) {
      const bounds = clash && clash.bounds_mm;
      if (!bounds || bounds.length < 4) {
        continue;
      }
      xs.push(bounds[0], bounds[2]);
      ys.push(bounds[1], bounds[3]);
    }
    const cxMin = Math.min(...xs);
    const cxMax = Math.max(...xs);
    const cyMin = Math.min(...ys);
    const cyMax = Math.max(...ys);
    const scaleX = (modelBBox.max.x - modelBBox.min.x) / (cxMax - cxMin);
    const scaleY = (modelBBox.max.y - modelBBox.min.y) / (cyMax - cyMin);
    const offX = modelBBox.min.x - cxMin * scaleX;
    const offY = modelBBox.min.y - cyMin * scaleY;
    return (clashes || []).map((clash) => {
      const b = clash.bounds_mm;
      const m0 = { x: b[0] * scaleX + offX, y: b[1] * scaleY + offY };
      const m1 = { x: b[2] * scaleX + offX, y: b[3] * scaleY + offY };
      const s0 = worldToClient(m0);
      const s1 = worldToClient(m1);
      let cx = null;
      let cy = null;
      if (clash.centroid_mm && clash.centroid_mm.length === 2) {
        const mc = {
          x: clash.centroid_mm[0] * scaleX + offX,
          y: clash.centroid_mm[1] * scaleY + offY,
        };
        const sc = worldToClient(mc);
        cx = sc.x;
        cy = sc.y;
      }
      return { x0: s0.x, y0: s0.y, x1: s1.x, y1: s1.y, cx, cy, type: clash.clash_type };
    });
  }

  return {
    clashMmToModel,
    projectClashesToBoxes,
    oldBboxAffineProjection,
  };
});
