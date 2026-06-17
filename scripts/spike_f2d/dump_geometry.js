// Volcado de geometría 2D real desde APS Viewer headless (Puppeteer).
//
// Uso:
//   APS_TOKEN=<token> node dump_geometry.js [--svf1] [--urn-file path] [--out path]
//     [--max-views N] [--view-names "A-1.5.4,ES-05"] [--dump-timeout-ms N]

const fs = require("fs");
const http = require("http");
const path = require("path");
const os = require("os");
const puppeteer = require("puppeteer");

const DIR = __dirname;

function parseArgs() {
  const args = process.argv.slice(2);
  let svf1 = true;
  let urnFile = path.join(DIR, "urn_svf1.json");
  let outFile = path.join(DIR, "dump_svf1.json");
  let maxViews = parseInt(process.env.APS_VIEWER_MAX_VIEWS || "4", 10);
  let viewNames = process.env.APS_VIEWER_VIEW_NAMES || "";
  let dumpTimeoutMs = parseInt(process.env.APS_VIEWER_GEOMETRY_TIMEOUT || "300", 10) * 1000;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--svf2") svf1 = false;
    if (args[i] === "--svf1") svf1 = true;
    if (args[i] === "--urn-file" && args[i + 1]) urnFile = args[++i];
    if (args[i] === "--out" && args[i + 1]) outFile = args[++i];
    if (args[i] === "--max-views" && args[i + 1]) maxViews = parseInt(args[++i], 10);
    if (args[i] === "--view-names" && args[i + 1]) viewNames = args[++i];
    if (args[i] === "--dump-timeout-ms" && args[i + 1]) dumpTimeoutMs = parseInt(args[++i], 10);
  }
  if (!svf1 && urnFile === path.join(DIR, "urn_svf1.json")) {
    urnFile = path.join(DIR, "urn.json");
    outFile = path.join(DIR, "dump.json");
  }
  return { svf1, urnFile, outFile, maxViews, viewNames, dumpTimeoutMs };
}

function loadUrn(urnFile) {
  const data = JSON.parse(fs.readFileSync(urnFile, "utf-8"));
  if (!data.urn) throw new Error(`${urnFile} no tiene 'urn'`);
  return data.urn;
}

function startStaticServer() {
  const server = http.createServer((req, res) => {
    const file = path.join(DIR, "viewer.html");
    fs.readFile(file, (err, buf) => {
      if (err) {
        res.writeHead(404);
        res.end("not found");
        return;
      }
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(buf);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function chromeExecutable() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) return process.env.PUPPETEER_EXECUTABLE_PATH;
  if (os.platform() === "darwin") {
    const candidates = [
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ];
    for (const p of candidates) if (fs.existsSync(p)) return p;
  }
  return undefined;
}

async function main() {
  const { svf1, urnFile, outFile, maxViews, viewNames, dumpTimeoutMs } = parseArgs();
  const token = process.env.APS_TOKEN;
  if (!token) throw new Error("Falta APS_TOKEN en el entorno");
  const urn = loadUrn(urnFile);
  const format = svf1 ? "svf1" : "svf2";

  console.log("[dump] format=", format, "maxViews=", maxViews, "viewNames=", viewNames || "(auto)");

  const server = await startStaticServer();
  const port = server.address().port;
  let url =
    `http://127.0.0.1:${port}/viewer.html?urn=${encodeURIComponent(urn)}` +
    `&token=${encodeURIComponent(token)}&format=${format}&maxViews=${maxViews}`;
  if (viewNames) {
    url += `&viewNames=${encodeURIComponent(viewNames)}`;
  }

  const browser = await puppeteer.launch({
    headless: true,
    executablePath: chromeExecutable(),
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--ignore-gpu-blocklist",
      "--use-gl=angle",
      "--enable-webgl",
      "--disable-dev-shm-usage",
    ],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  page.on("console", (msg) => console.log("[page]", msg.text()));
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));

  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 120000 });

  const TIMEOUT_MS = Math.max(300000, dumpTimeoutMs);
  const t0 = Date.now();
  let result = null;
  while (Date.now() - t0 < TIMEOUT_MS) {
    const status = await page.evaluate(() => window.__DUMP__ && window.__DUMP__.status);
    if (status === "done" || status === "error") {
      result = await page.evaluate(() => window.__DUMP__);
      break;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }

  if (!result) {
    result = await page.evaluate(() => window.__DUMP__);
    console.log("[dump] TIMEOUT, último estado:", result && result.status);
  }

  fs.writeFileSync(outFile, JSON.stringify(result, null, 2));

  const views = (result && result.views) || [];
  let totalSegs = 0;
  let totalObjs = 0;
  for (const v of views) {
    totalSegs += (v.meta && v.meta.segmentCount) || 0;
    totalObjs += (v.objects && v.objects.length) || 0;
  }

  console.log("=== RESULTADO DUMP ===");
  console.log("status:", result && result.status);
  if (result && result.error) console.log("error:", result.error);
  console.log("format:", result && result.format);
  console.log("views:", views.length, "| objects:", totalObjs, "| segments:", totalSegs);
  for (const v of views.slice(0, 8)) {
    console.log("  -", v.name, "objs=", (v.objects || []).length, "segs=", (v.meta && v.meta.segmentCount) || 0);
  }
  console.log("salida:", outFile);

  await browser.close();
  server.close();

  if (!result || result.status !== "done" || totalSegs === 0) {
    process.exit(2);
  }
}

main().catch((e) => {
  console.error("FATAL:", e);
  process.exit(1);
});
