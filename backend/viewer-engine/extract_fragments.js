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
  const allViewables = args["all-viewables"] !== "0";
  const timeoutMs = Number(args.timeout || 180000);

  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch (error) {
    throw new Error("Missing Node dependency 'playwright'. Install it for backend/viewer-engine before running fragment extraction.");
  }

  fs.mkdirSync(path.dirname(output), { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-gpu", "--no-sandbox"],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    page.on("console", (message) => {
      console.log(`[browser:${message.type()}] ${message.text()}`);
    });
    page.on("pageerror", (error) => {
      console.error(`[browser:pageerror] ${error.stack || error}`);
    });

    const viewerUrl = pathToFileURL(path.join(__dirname, "viewer.html")).href;
    await page.goto(viewerUrl, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    await page.waitForFunction(() => window.DuplaFragmentExtractor && window.Autodesk && window.THREE, null, { timeout: timeoutMs });
    const payload = await page.evaluate(
      ({ urn, accessToken, viewableGuid, allViewables }) => window.DuplaFragmentExtractor.extract({ urn, accessToken, viewableGuid, allViewables }),
      { urn, accessToken: token, viewableGuid, allViewables }
    );
    const enriched = {
      ...payload,
      cache_metadata: {
        urn,
        viewable_guid: viewableGuid || null,
        extracted_at: new Date().toISOString(),
      },
    };
    fs.writeFileSync(output, `${JSON.stringify(enriched, null, 2)}\n`, "utf8");
    const objectCount = (enriched.views || []).reduce((total, view) => total + ((view.objects || []).length), 0);
    console.log(`[COORD] Wrote ${output} views=${(enriched.views || []).length} objects=${objectCount}`);
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
  console.error(`[COORD] Fragment extraction failed: ${error.stack || error}`);
  process.exit(1);
});
