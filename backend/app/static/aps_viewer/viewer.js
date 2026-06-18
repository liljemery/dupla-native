(async function boot() {
  const api = window.DuplaApiClient;
  const projectId = api.projectIdFromPath();
  const coordinateSpace = api.coordinateSpaceFromUrl();
  const debug = new URLSearchParams(window.location.search).get("debug") === "true";
  const calibrate = new URLSearchParams(window.location.search).get("calibrate") === "true";
  const debugPanel = document.getElementById("debugPanel");
  let config;
  try {
    config = await api.getViewerConfig(projectId, coordinateSpace);
  } catch (error) {
    if (projectId !== "demo") throw error;
    config = { project_id: "demo", urn: "demo", clashes_url: `/api/projects/demo/viewer/clashes?coordinate_space=${coordinateSpace}` };
  }
  if (debug) {
    debugPanel.classList.add("visible");
    debugPanel.innerHTML = `Estás viendo coordinate_space=${coordinateSpace}<br>URN: ${config.urn}<br>${(config.warnings || []).join("<br>")}`;
  }
  if (projectId === "demo" || config.urn === "demo") {
    await bootDemo(projectId, coordinateSpace, debugPanel, debug, calibrate);
    return;
  }
  Autodesk.Viewing.Initializer({
    env: "AutodeskProduction",
    getAccessToken: async (onTokenReady) => {
      const token = await api.getApsToken();
      onTokenReady(token.access_token, token.expires_in || 1800);
    },
  }, () => {
    const viewer = new Autodesk.Viewing.GuiViewer3D(document.getElementById("viewer"));
    viewer.start();
    Autodesk.Viewing.Document.load(`urn:${config.urn}`, (doc) => {
      const viewables = doc.getRoot().search({ type: "geometry" });
      const configured = viewables.find((item) => item.data && item.data.guid === config.default_viewable_guid);
      const target = (configured && is2DViewable(configured)) || viewables.find(is2DViewable) || configured || viewables[0];
      viewer.loadDocumentNode(doc, target).then(async () => {
        const extension = await viewer.loadExtension("Dupla.ClashBoxesExtension", { clashesUrl: config.clashes_url, coordinateSpace });
        const sidebar = new window.ClashSidebar(document.getElementById("clashSidebar"), extension, projectId, coordinateSpace);
        const loadClashesOnce = async () => {
          await extension.loadClashes();
          sidebar.render();
          viewer.removeEventListener(Autodesk.Viewing.GEOMETRY_LOADED_EVENT, loadClashesOnce);
        };
        viewer.addEventListener(Autodesk.Viewing.GEOMETRY_LOADED_EVENT, loadClashesOnce);
        await loadClashesOnce();
        setupCalibrationPanel(projectId, extension, coordinateSpace, calibrate);
      });
    });
  });
})();

function is2DViewable(item) {
  const data = item && item.data ? item.data : {};
  const role = String(data.role || "").toLowerCase();
  const name = String(data.name || "").toLowerCase();
  return role === "2d" || role === "sheet" || name.includes("sheet") || name.includes("layout");
}

async function bootDemo(projectId, coordinateSpace, debugPanel, debug, calibrate) {
  document.getElementById("viewer").hidden = true;
  const svg = document.getElementById("demoViewer");
  svg.hidden = false;
  const data = await window.DuplaApiClient.getClashes(projectId, coordinateSpace);
  const extension = {
    visible: true, clashes: data.clashes, selected: null, coordinateSpace, temporarySettings: null, showCentroids: true, showLabels: true,
    loadClashes: async () => data,
    setVisible(visible) { this.visible = visible; render(); },
    filterBySeverity(severities) { this.severities = severities; render(); },
    filterByDiscipline(disciplines) { this.disciplines = disciplines; render(); },
    applyTemporaryCoordinateSettings(settings) { this.temporarySettings = settings; render(); },
    setCalibrationDisplay(options) {
      if (typeof options.showCentroids === "boolean") this.showCentroids = options.showCentroids;
      if (typeof options.showLabels === "boolean") this.showLabels = options.showLabels;
      render();
    },
    async reloadWithCoordinateSpace(nextSpace) {
      this.coordinateSpace = nextSpace === "model" ? "model" : "world";
      const next = await window.DuplaApiClient.getClashes(projectId, this.coordinateSpace);
      this.clashes = next.clashes || [];
      render();
      return next;
    },
    selectClash(clashId) {
      this.selected = clashId;
      const clash = this.clashes.find((item) => item.id === clashId);
      window.dispatchEvent(new CustomEvent("clash:selected", { detail: clash }));
      render();
    },
    focusClash(clashId) {
      const clash = this.clashes.find((item) => item.id === clashId);
      if (!clash) return;
      const b = effectiveDemoBbox(clash, extension);
      svg.setAttribute("viewBox", `${b.min_x - 800} ${b.min_y - 800} ${(b.max_x - b.min_x) + 1600} ${(b.max_y - b.min_y) + 1600}`);
    },
    refresh: async () => render(),
  };
  const sidebar = new window.ClashSidebar(document.getElementById("clashSidebar"), extension, projectId, coordinateSpace);
  window.dispatchEvent(new CustomEvent("clashes:loaded", { detail: data }));
  render();
  setupCalibrationPanel(projectId, extension, coordinateSpace, calibrate);
  function render() {
    const colors = { critical: "#dc2626", high: "#f97316", medium: "#facc15", low: "#38bdf8" };
    svg.innerHTML = '<rect x="0" y="0" width="5200" height="4200" fill="#fbfcfe"></rect>';
    for (const clash of extension.clashes) {
      const b = effectiveDemoBbox(clash, extension);
      const selected = extension.selected === clash.id;
      const c = centerOfBbox(b);
      svg.insertAdjacentHTML("beforeend", `<rect class="demo-box ${selected ? "selected" : ""}" x="${b.min_x}" y="${b.min_y}" width="${b.max_x - b.min_x}" height="${b.max_y - b.min_y}" stroke="${colors[clash.severity]}"></rect>${extension.showCentroids ? `<line class="demo-crosshair" x1="${c.x - 80}" y1="${c.y}" x2="${c.x + 80}" y2="${c.y}"></line><line class="demo-crosshair" x1="${c.x}" y1="${c.y - 80}" x2="${c.x}" y2="${c.y + 80}"></line>` : ""}${extension.showLabels ? `<text class="demo-label" x="${b.min_x}" y="${b.min_y - 40}">${clash.id}</text>` : ""}`);
    }
    if (debug) debugPanel.innerHTML = `Estás viendo coordinate_space=${coordinateSpace}<br>Demo SVG sin APS real<br>Valores grandes en mm son esperados en proyectos reales.`;
  }
}

function setupCalibrationPanel(projectId, extension, initialCoordinateSpace, enabled) {
  const panel = document.getElementById("calibrationPanel");
  if (!enabled || !panel) return;
  panel.hidden = false;
  const fields = {
    coordinate_space: document.getElementById("calCoordinateSpace"),
    scale: document.getElementById("calScale"),
    offset_x: document.getElementById("calOffsetX"),
    offset_y: document.getElementById("calOffsetY"),
    offset_z: document.getElementById("calOffsetZ"),
    invert_y: document.getElementById("calInvertY"),
    rotation_degrees: document.getElementById("calRotation"),
    unit_factor: document.getElementById("calUnitFactor"),
  };
  const readout = document.getElementById("calReadout");
  let showRaw = false;
  let showTransformed = true;
  let selectedClash = null;
  window.addEventListener("clash:selected", (event) => { selectedClash = event.detail; updateReadout(); });
  window.addEventListener("clashes:loaded", (event) => {
    const settings = event.detail.coordinate_settings_applied || defaultSettings(initialCoordinateSpace);
    fillFields(settings);
    updateReadout();
  });
  window.DuplaApiClient.getCoordinateSettings(projectId, initialCoordinateSpace).then(fillFields).catch(() => fillFields(defaultSettings(initialCoordinateSpace)));
  document.getElementById("calApply").addEventListener("click", () => {
    extension.coordinateSpace = fields.coordinate_space.value;
    extension.applyTemporaryCoordinateSettings(readFields());
    updateReadout();
  });
  document.getElementById("calSave").addEventListener("click", async () => {
    const settings = readFields();
    await window.DuplaApiClient.saveCoordinateSettings(projectId, settings);
    await extension.reloadWithCoordinateSpace(settings.coordinate_space);
    extension.temporarySettings = null;
    updateReadout();
  });
  document.getElementById("calReset").addEventListener("click", async () => {
    const settings = await window.DuplaApiClient.resetCoordinateSettings(projectId, fields.coordinate_space.value);
    fillFields(settings);
    extension.temporarySettings = null;
    await extension.reloadWithCoordinateSpace(settings.coordinate_space);
    updateReadout();
  });
  document.getElementById("calToggleSpace").addEventListener("click", async () => {
    fields.coordinate_space.value = fields.coordinate_space.value === "world" ? "model" : "world";
    await extension.reloadWithCoordinateSpace(fields.coordinate_space.value);
    updateReadout();
  });
  document.getElementById("calCentroids").addEventListener("click", (event) => {
    extension.showCentroids = !extension.showCentroids;
    extension.setCalibrationDisplay({ showCentroids: extension.showCentroids });
    event.target.textContent = extension.showCentroids ? "Ocultar centroides" : "Mostrar centroides";
  });
  document.getElementById("calLabels").addEventListener("click", (event) => {
    extension.showLabels = !extension.showLabels;
    extension.setCalibrationDisplay({ showLabels: extension.showLabels });
    event.target.textContent = extension.showLabels ? "Ocultar labels" : "Mostrar labels";
  });
  document.getElementById("calRaw").addEventListener("click", () => { showRaw = !showRaw; updateReadout(); });
  document.getElementById("calTransformed").addEventListener("click", () => { showTransformed = !showTransformed; updateReadout(); });

  function fillFields(settings) {
    fields.coordinate_space.value = settings.coordinate_space || initialCoordinateSpace || "world";
    fields.scale.value = settings.scale ?? 1;
    fields.offset_x.value = settings.offset_x ?? 0;
    fields.offset_y.value = settings.offset_y ?? 0;
    fields.offset_z.value = settings.offset_z ?? 0;
    fields.invert_y.checked = Boolean(settings.invert_y);
    fields.rotation_degrees.value = settings.rotation_degrees ?? 0;
    fields.unit_factor.value = settings.unit_factor ?? 1;
  }
  function readFields() {
    return {
      coordinate_space: fields.coordinate_space.value,
      scale: Number(fields.scale.value || 1),
      offset_x: Number(fields.offset_x.value || 0),
      offset_y: Number(fields.offset_y.value || 0),
      offset_z: Number(fields.offset_z.value || 0),
      invert_y: fields.invert_y.checked,
      rotation_degrees: Number(fields.rotation_degrees.value || 0),
      unit_factor: Number(fields.unit_factor.value || 1),
      notes: "Calibrado desde Autodesk Viewer",
    };
  }
  function updateReadout() {
    const total = extension.clashes ? extension.clashes.length : 0;
    const payload = { coordinate_space: fields.coordinate_space.value, total_clashes: total };
    if (selectedClash) {
      payload.selected = selectedClash.id;
      payload.center = selectedClash.center;
      if (showRaw) {
        payload.raw_model_bbox_mm = selectedClash.raw_model_bbox_mm || selectedClash.model_bbox_mm;
        payload.raw_world_bbox_mm = selectedClash.raw_world_bbox_mm || selectedClash.world_bbox_mm;
      }
      if (showTransformed) payload.viewer_bbox = effectiveDemoBbox(selectedClash, extension);
    }
    readout.textContent = JSON.stringify(payload, null, 2);
  }
}

function defaultSettings(coordinateSpace) {
  return { coordinate_space: coordinateSpace || "world", scale: 1, offset_x: 0, offset_y: 0, offset_z: 0, invert_y: false, rotation_degrees: 0, unit_factor: 1 };
}

function effectiveDemoBbox(clash, extension) {
  if (!extension.temporarySettings) return clash.viewer_bbox;
  const raw = extension.coordinateSpace === "model" ? (clash.raw_model_bbox_mm || clash.model_bbox_mm) : (clash.raw_world_bbox_mm || clash.world_bbox_mm);
  return mapBboxWithSettings(raw, extension.temporarySettings);
}

function mapBboxWithSettings(bbox, settings) {
  const pts = [
    mapPoint(bbox.min_x, bbox.min_y, bbox.min_z || 0, settings),
    mapPoint(bbox.min_x, bbox.max_y, bbox.min_z || 0, settings),
    mapPoint(bbox.max_x, bbox.min_y, bbox.max_z || 0, settings),
    mapPoint(bbox.max_x, bbox.max_y, bbox.max_z || 0, settings),
  ];
  return { min_x: Math.min(...pts.map((p) => p.x)), min_y: Math.min(...pts.map((p) => p.y)), min_z: Math.min(...pts.map((p) => p.z)), max_x: Math.max(...pts.map((p) => p.x)), max_y: Math.max(...pts.map((p) => p.y)), max_z: Math.max(...pts.map((p) => p.z)) };
}

function mapPoint(x, y, z, settings) {
  let nx = Number(x) * Number(settings.unit_factor || 1) * Number(settings.scale || 1);
  let ny = Number(y) * Number(settings.unit_factor || 1) * Number(settings.scale || 1);
  const nz = Number(z || 0) * Number(settings.unit_factor || 1) * Number(settings.scale || 1);
  if (settings.invert_y) ny = -ny;
  const a = Number(settings.rotation_degrees || 0) * Math.PI / 180;
  return { x: nx * Math.cos(a) - ny * Math.sin(a) + Number(settings.offset_x || 0), y: nx * Math.sin(a) + ny * Math.cos(a) + Number(settings.offset_y || 0), z: nz + Number(settings.offset_z || 0) };
}

function centerOfBbox(bbox) {
  return { x: (bbox.min_x + bbox.max_x) / 2, y: (bbox.min_y + bbox.max_y) / 2, z: ((bbox.min_z || 0) + (bbox.max_z || 0)) / 2 };
}
