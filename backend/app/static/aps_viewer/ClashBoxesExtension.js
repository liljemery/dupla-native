function create2DBoxGeometry(bbox, z = 0) {
  const points = [
    new THREE.Vector3(bbox.min_x, bbox.min_y, z),
    new THREE.Vector3(bbox.max_x, bbox.min_y, z),
    new THREE.Vector3(bbox.max_x, bbox.max_y, z),
    new THREE.Vector3(bbox.min_x, bbox.max_y, z),
    new THREE.Vector3(bbox.min_x, bbox.min_y, z),
  ];
  return new THREE.BufferGeometry().setFromPoints(points);
}

function create3DBoxLines(bbox) {
  const min = new THREE.Vector3(bbox.min_x, bbox.min_y, bbox.min_z || 0);
  const max = new THREE.Vector3(bbox.max_x, bbox.max_y, bbox.max_z || 0);
  return new THREE.Box3Helper(new THREE.Box3(min, max));
}

class ClashBoxesExtension extends Autodesk.Viewing.Extension {
  constructor(viewer, options) {
    super(viewer, options);
    this.overlayName = "dupla-clash-boxes-overlay";
    this.clashesUrl = options.clashesUrl;
    this.clashes = [];
    this.visible = true;
    this.selectedClashId = null;
    this.clashIdToObject = new Map();
    this.activeSeverities = new Set(["critical", "high", "medium", "low"]);
    this.activeDisciplines = new Set(["architecture", "structure", "plumbing", "mechanical", "electrical"]);
    this.coordinateSpace = options.coordinateSpace || "world";
    this.temporarySettings = null;
    this.showCentroids = false;
    this.showLabels = false;
  }
  load() { this.viewer.impl.createOverlayScene(this.overlayName); return true; }
  unload() { this.clearClashes(); this.viewer.impl.removeOverlayScene(this.overlayName); return true; }
  async loadClashes() {
    const data = await fetch(this.clashesUrl, { headers: window.DuplaApiClient.authHeaders() }).then((r) => r.json());
    this.clashes = data.clashes || [];
    this.coordinateSettings = data.coordinate_settings_applied || null;
    window.dispatchEvent(new CustomEvent("clashes:loaded", { detail: data }));
    this.drawClashes();
    return data;
  }
  drawClashes() {
    this.clearClashes();
    if (!this.visible) return;
    for (const clash of this.clashes) {
      if (!this._passesFilters(clash)) continue;
      const object = this._createObject(clash);
      object.userData.clashId = clash.id;
      object.userData.severity = clash.severity;
      this.clashIdToObject.set(clash.id, object);
      this.viewer.impl.addOverlay(this.overlayName, object);
    }
    this.viewer.impl.invalidate(true, true, true);
  }
  clearClashes() {
    for (const object of this.clashIdToObject.values()) {
      this.viewer.impl.removeOverlay(this.overlayName, object);
      object.traverse((child) => {
        if (child.geometry) child.geometry.dispose();
        if (child.material) {
          if (child.material.map) child.material.map.dispose();
          child.material.dispose();
        }
      });
    }
    this.clashIdToObject.clear();
    this.viewer.impl.invalidate(true, true, true);
  }
  setVisible(visible) { this.visible = visible; this.drawClashes(); }
  filterBySeverity(severities) { this.activeSeverities = new Set(severities); this.drawClashes(); }
  filterByDiscipline(disciplines) { this.activeDisciplines = new Set(disciplines); this.drawClashes(); }
  applyTemporaryCoordinateSettings(settings) { this.temporarySettings = settings; this.drawClashes(); }
  setCalibrationDisplay(options = {}) {
    if (typeof options.showCentroids === "boolean") this.showCentroids = options.showCentroids;
    if (typeof options.showLabels === "boolean") this.showLabels = options.showLabels;
    this.drawClashes();
  }
  reloadWithCoordinateSpace(coordinateSpace) {
    this.coordinateSpace = coordinateSpace === "model" ? "model" : "world";
    const url = new URL(this.clashesUrl, window.location.origin);
    url.searchParams.set("coordinate_space", this.coordinateSpace);
    this.clashesUrl = `${url.pathname}${url.search}`;
    return this.loadClashes();
  }
  selectClash(clashId) {
    if (this.selectedClashId && this.clashIdToObject.has(this.selectedClashId)) {
      const prev = this.clashIdToObject.get(this.selectedClashId);
      this._setObjectColor(prev, this._colorFor(prev.userData.severity));
    }
    this.selectedClashId = clashId;
    const object = this.clashIdToObject.get(clashId);
    const clash = this.clashes.find((item) => item.id === clashId);
    if (object) this._setObjectColor(object, 0x1f6feb);
    this.viewer.impl.invalidate(true, true, true);
    if (clash) window.dispatchEvent(new CustomEvent("clash:selected", { detail: clash }));
  }
  focusClash(clashId) {
    const clash = this.clashes.find((item) => item.id === clashId);
    if (!clash) return;
    const b = this._effectiveBbox(clash);
    const box3 = new THREE.Box3(new THREE.Vector3(b.min_x, b.min_y, b.min_z || 0), new THREE.Vector3(b.max_x, b.max_y, b.max_z || 0));
    try { this.viewer.navigation.fitBounds(false, box3); } catch (_) { this.viewer.navigation.setTarget(box3.getCenter(new THREE.Vector3())); }
  }
  refresh() { return this.loadClashes(); }
  _createObject(clash) {
    const b = this._effectiveBbox(clash);
    const group = new THREE.Group();
    const material = new THREE.LineBasicMaterial({ color: this._colorFor(clash.severity), depthTest: false });
    if ((this.viewer.model && this.viewer.model.is2d && this.viewer.model.is2d()) || (b.min_z || 0) === (b.max_z || 0)) {
      group.add(new THREE.Line(create2DBoxGeometry(b, b.min_z || 0), material));
    } else {
      const helper = create3DBoxLines(b);
      helper.material.color.set(this._colorFor(clash.severity));
      group.add(helper);
    }
    if (this.showCentroids) group.add(this._crosshair(clash, b));
    if (this.showLabels) group.add(this._label(clash.id, b));
    return group;
  }
  _passesFilters(clash) {
    return this.activeSeverities.has(clash.severity) && (this.activeDisciplines.has(clash.discipline_a) || this.activeDisciplines.has(clash.discipline_b));
  }
  _colorFor(severity) {
    return { critical: 0xdc2626, high: 0xf97316, medium: 0xfacc15, low: 0x38bdf8 }[severity] || 0xfacc15;
  }
  _effectiveBbox(clash) {
    if (!this.temporarySettings) return clash.viewer_bbox;
    const raw = this.coordinateSpace === "model" ? (clash.raw_model_bbox_mm || clash.model_bbox_mm) : (clash.raw_world_bbox_mm || clash.world_bbox_mm);
    return mapBboxWithSettings(raw, this.temporarySettings);
  }
  _setObjectColor(object, color) {
    object.traverse((child) => { if (child.material && child.material.color) child.material.color.set(color); });
  }
  _crosshair(clash, bbox) {
    const c = centerOfBbox(bbox);
    const size = Math.max(bbox.max_x - bbox.min_x, bbox.max_y - bbox.min_y, 100) * 0.18;
    const geometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(c.x - size, c.y, c.z), new THREE.Vector3(c.x + size, c.y, c.z),
      new THREE.Vector3(c.x, c.y - size, c.z), new THREE.Vector3(c.x, c.y + size, c.z),
    ]);
    return new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: 0x111827, depthTest: false }));
  }
  _label(text, bbox) {
    const canvas = document.createElement("canvas");
    canvas.width = 256; canvas.height = 64;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "rgba(255,255,255,.88)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#111827";
    ctx.font = "28px sans-serif";
    ctx.fillText(text, 14, 40);
    const texture = new THREE.CanvasTexture(canvas);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false }));
    const width = Math.max(bbox.max_x - bbox.min_x, 250);
    sprite.scale.set(width, width / 4, 1);
    sprite.position.set(bbox.min_x + width / 2, bbox.max_y + width / 8, bbox.max_z || 0);
    return sprite;
  }
}

function mapPointWithSettings(x, y, z, settings) {
  const unit = Number(settings.unit_factor ?? 1);
  const scale = Number(settings.scale ?? 1);
  let nx = Number(x) * unit * scale;
  let ny = Number(y) * unit * scale;
  const nz = Number(z || 0) * unit * scale;
  if (settings.invert_y) ny = -ny;
  const angle = Number(settings.rotation_degrees || 0) * Math.PI / 180;
  const rx = nx * Math.cos(angle) - ny * Math.sin(angle);
  const ry = nx * Math.sin(angle) + ny * Math.cos(angle);
  return {
    x: rx + Number(settings.offset_x || 0),
    y: ry + Number(settings.offset_y || 0),
    z: nz + Number(settings.offset_z || 0),
  };
}

function mapBboxWithSettings(bbox, settings) {
  const minZ = Number(bbox.min_z || 0);
  const maxZ = Number(bbox.max_z ?? minZ);
  const points = [
    mapPointWithSettings(bbox.min_x, bbox.min_y, minZ, settings),
    mapPointWithSettings(bbox.min_x, bbox.max_y, minZ, settings),
    mapPointWithSettings(bbox.max_x, bbox.min_y, maxZ, settings),
    mapPointWithSettings(bbox.max_x, bbox.max_y, maxZ, settings),
  ];
  return {
    min_x: Math.min(...points.map((p) => p.x)),
    min_y: Math.min(...points.map((p) => p.y)),
    min_z: Math.min(...points.map((p) => p.z)),
    max_x: Math.max(...points.map((p) => p.x)),
    max_y: Math.max(...points.map((p) => p.y)),
    max_z: Math.max(...points.map((p) => p.z)),
  };
}

function centerOfBbox(bbox) {
  return {
    x: (bbox.min_x + bbox.max_x) / 2,
    y: (bbox.min_y + bbox.max_y) / 2,
    z: ((bbox.min_z || 0) + (bbox.max_z || 0)) / 2,
  };
}
Autodesk.Viewing.theExtensionManager.registerExtension("Dupla.ClashBoxesExtension", ClashBoxesExtension);
