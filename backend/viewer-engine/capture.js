#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const urn = required(args, "urn");
  const token = required(args, "token");
  const output = required(args, "output");
  const viewableGuid = args["viewable-guid"] || "";
  const timeoutMs = Number(args.timeout || 180000);
  const width = Number(args.width || 3000);
  const height = Number(args.height || 2200);
  const clashesFile = args["clashes-file"] || "";
  const sheet = args.sheet || "";
  const view = args.view || "";

  let playwright;
  try {
    ({ chromium: playwright } = require("playwright"));
  } catch (error) {
    throw new Error("Missing Node dependency 'playwright'. Install it for backend/viewer-engine before running screenshots.");
  }

  let clashesJson = "[]";
  if (clashesFile && fs.existsSync(clashesFile)) clashesJson = fs.readFileSync(clashesFile, "utf8");

  fs.mkdirSync(path.dirname(output), { recursive: true });
  const browser = await playwright.launch({
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-webgl",
      "--ignore-gpu-blacklist",
      "--disable-web-security",
      `--window-size=${width},${height}`,
    ],
  });

  try {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    page.on("console", (message) => {
      const text = message.text();
      if (text.includes("[poc]") || text.includes("PAGEERR") || text.includes("COORD_")) {
        console.log(text);
      }
    });
    page.on("pageerror", (error) => console.log("PAGEERR:", error.message));

    await page.addInitScript(`window.__CLASHES__ = ${clashesJson};`);

    const viewerHtml = pathToFileURL(path.join(__dirname, "capture.html")).href;
    const url = `${viewerHtml}?urn=${encodeURIComponent(urn)}`
      + `&token=${encodeURIComponent(token)}`
      + `&w=${width}&h=${height}`
      + `&view=${encodeURIComponent(view)}`
      + `&sheet=${encodeURIComponent(sheet)}`
      + `&viewable-guid=${encodeURIComponent(viewableGuid)}`;

    await page.goto(url, { waitUntil: "networkidle", timeout: timeoutMs });
    await page.waitForFunction("window.__SHOT__ || window.__ERR__", { timeout: timeoutMs });

    const err = await page.evaluate("window.__ERR__");
    if (err) {
      console.error("VIEWER_ERR:", err);
      process.exitCode = 1;
      return;
    }

    const dataUrl = await page.evaluate("window.__SHOT__");
    const b64 = String(dataUrl || "").split(",")[1] || "";
    fs.writeFileSync(output, Buffer.from(b64, "base64"));

    const boxes = await page.evaluate("window.__BOXES__ || []");
    fs.writeFileSync(output + ".boxes.json", JSON.stringify(boxes, null, 2));
    const diag = await page.evaluate("window.__DIAG__ || {}");
    fs.writeFileSync(output + ".diag.json", JSON.stringify(diag, null, 2));

    console.log("SAVED", output, fs.statSync(output).size, "bytes; boxes=", boxes.length);
  } finally {
    await browser.close();
  }
}

function parseArgs(argv) {
  const out = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!key.startsWith("--")) throw new Error(`Unexpected argument ${key}`);
    const name = key.slice(2);
    const value = argv[index + 1];
    if (value == null || value.startsWith("--")) throw new Error(`Missing value for ${key}`);
    out[name] = value;
    index += 1;
  }
  return out;
}

function required(args, name) {
  if (!args[name]) throw new Error(`Missing --${name}`);
  return args[name];
}

main().catch((error) => {
  console.error(`[COORD] Viewer screenshot failed: ${error.stack || error}`);
  process.exit(1);
});
