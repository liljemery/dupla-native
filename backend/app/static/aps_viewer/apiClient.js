window.DuplaApiClient = (() => {
  function projectIdFromPath() {
    const match = window.location.pathname.match(/\/api\/projects\/([^/]+)\/viewer/);
    return match ? match[1] : "demo";
  }
  function coordinateSpaceFromUrl() {
    return new URLSearchParams(window.location.search).get("coordinate_space") || "world";
  }
  function authHeaders() {
    const token = window.localStorage.getItem("access_token") || window.localStorage.getItem("token") || window.sessionStorage.getItem("access_token") || "";
    return token ? { Authorization: token.startsWith("Bearer ") ? token : `Bearer ${token}` } : {};
  }
  async function requestJson(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { ...authHeaders(), ...(options.headers || {}) } });
    if (!response.ok) throw new Error(`${url}: ${response.status} ${await response.text()}`);
    return response.json();
  }
  function getViewerConfig(projectId, coordinateSpace = coordinateSpaceFromUrl()) {
    return requestJson(`/api/projects/${projectId}/viewer/config?coordinate_space=${coordinateSpace}`);
  }
  function getApsToken() { return requestJson("/api/aps/token"); }
  function getClashes(projectId, coordinateSpace = coordinateSpaceFromUrl()) {
    return requestJson(`/api/projects/${projectId}/viewer/clashes?coordinate_space=${coordinateSpace}`);
  }
  function getCoordinateSettings(projectId, coordinateSpace = coordinateSpaceFromUrl()) {
    return requestJson(`/api/projects/${projectId}/viewer/coordinate-settings?coordinate_space=${coordinateSpace}`);
  }
  function saveCoordinateSettings(projectId, settings) {
    return requestJson(`/api/projects/${projectId}/viewer/coordinate-settings`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings),
    });
  }
  function resetCoordinateSettings(projectId, coordinateSpace = coordinateSpaceFromUrl()) {
    return requestJson(`/api/projects/${projectId}/viewer/coordinate-settings/reset?coordinate_space=${coordinateSpace}`, { method: "POST" });
  }
  function updateClashStatus(projectId, clashId, status, comment = "") {
    return requestJson(`/api/projects/${projectId}/viewer/clashes/${clashId}/status`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status, comment }),
    });
  }
  function getMappingCandidates(projectId, clashId) {
    return requestJson(`/api/projects/${projectId}/viewer/clashes/${clashId}/mapping-candidates`);
  }
  return {
    projectIdFromPath, coordinateSpaceFromUrl, authHeaders, getViewerConfig, getApsToken, getClashes,
    getCoordinateSettings, saveCoordinateSettings, resetCoordinateSettings, updateClashStatus, getMappingCandidates,
  };
})();
