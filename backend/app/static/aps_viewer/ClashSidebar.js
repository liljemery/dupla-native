class ClashSidebar {
  constructor(container, extension, projectId, coordinateSpace) {
    this.container = container;
    this.extension = extension;
    this.projectId = projectId;
    this.coordinateSpace = coordinateSpace;
    this.clashes = [];
    this.selected = null;
    this.severities = new Set(["critical", "high", "medium", "low"]);
    this.disciplines = new Set(["architecture", "structure", "plumbing", "mechanical", "electrical"]);
    window.addEventListener("clashes:loaded", (event) => { this.clashes = event.detail.clashes || []; this.render(event.detail.summary || {}); });
    window.addEventListener("clash:selected", (event) => { this.selected = event.detail.id; this.render(); });
  }
  render(summary = null) {
    const counts = summary || this._summary();
    const filtered = this.clashes.filter((clash) => this._passesFilters(clash));
    this.container.innerHTML = `
      <h1>Clashes APS</h1><div class="clash-meta">coordinate_space=${this.coordinateSpace}</div>
      <div class="toolbar"><button data-action="toggle">Boxes</button><button data-action="refresh">Refrescar</button><button data-action="export">JSON</button></div>
      <h2>Resumen</h2><div class="clash-meta">Total ${counts.total || filtered.length} · C ${counts.critical || 0} · H ${counts.high || 0} · M ${counts.medium || 0} · L ${counts.low || 0}</div>
      <h2>Severidad</h2><div class="filters">${["critical","high","medium","low"].map((v) => this._checkbox("severity", v, this.severities.has(v))).join("")}</div>
      <h2>Disciplina</h2><div class="filters">${["architecture","structure","plumbing","mechanical","electrical"].map((v) => this._checkbox("discipline", v, this.disciplines.has(v))).join("")}</div>
      <h2>Resultados</h2><div class="clash-list">${filtered.map((clash) => this._item(clash)).join("")}</div>`;
    this._bind();
  }
  _checkbox(kind, value, checked) { return `<label class="filter"><input type="checkbox" data-filter="${kind}" value="${value}" ${checked ? "checked" : ""}>${value}</label>`; }
  _item(clash) {
    return `<button class="clash-item ${this.selected === clash.id ? "selected" : ""}" data-clash-id="${clash.id}">
      <span class="clash-title">${clash.id} · ${clash.severity}</span>
      <span class="clash-meta">${clash.discipline_a} vs ${clash.discipline_b}<br>${clash.layer_a} / ${clash.layer_b}<br>${clash.clash_type}</span>
      <span class="clash-meta">${clash.description || ""}</span></button>`;
  }
  _bind() {
    this.container.querySelectorAll("[data-clash-id]").forEach((button) => button.addEventListener("click", () => {
      this.extension.selectClash(button.dataset.clashId);
      this.extension.focusClash(button.dataset.clashId);
    }));
    this.container.querySelectorAll("[data-filter]").forEach((input) => input.addEventListener("change", () => {
      const set = input.dataset.filter === "severity" ? this.severities : this.disciplines;
      input.checked ? set.add(input.value) : set.delete(input.value);
      this.extension.filterBySeverity(this.severities);
      this.extension.filterByDiscipline(this.disciplines);
      this.render();
    }));
    const toggle = this.container.querySelector('[data-action="toggle"]');
    if (toggle) toggle.addEventListener("click", () => this.extension.setVisible(!this.extension.visible));
    const refresh = this.container.querySelector('[data-action="refresh"]');
    if (refresh) refresh.addEventListener("click", () => this.extension.refresh());
    const exportButton = this.container.querySelector('[data-action="export"]');
    if (exportButton) exportButton.addEventListener("click", () => this._exportJson());
  }
  _passesFilters(clash) { return this.severities.has(clash.severity) && (this.disciplines.has(clash.discipline_a) || this.disciplines.has(clash.discipline_b)); }
  _summary() {
    const out = { total: this.clashes.length, critical: 0, high: 0, medium: 0, low: 0 };
    this.clashes.forEach((clash) => { out[clash.severity] = (out[clash.severity] || 0) + 1; });
    return out;
  }
  _exportJson() {
    const blob = new Blob([JSON.stringify(this.clashes, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${this.projectId}-clashes.json`; a.click();
    URL.revokeObjectURL(url);
  }
}
window.ClashSidebar = ClashSidebar;
