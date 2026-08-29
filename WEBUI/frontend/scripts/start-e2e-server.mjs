/* global console */

import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import process from "node:process";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(frontendRoot, "../..");
const apiRoot = join(repositoryRoot, "API");
const distRoot = join(frontendRoot, "dist");
const port = parsePort(process.env.NOVEL_E2E_PORT ?? "18765");
const dataRoot = await mkdtemp(join(tmpdir(), "novelproduction-e2e-"));
let child;
let stopping = false;

try {
  await assertPortAvailable(port);
  await readFile(join(distRoot, "index.html"), "utf8");

  const environment = { ...process.env };
  delete environment.NOVEL_DATA_ROOT;
  delete environment.NOVEL_WEBUI_DIST;
  delete environment.NOVEL_API_HOST;
  delete environment.NOVEL_API_PORT;

  child = spawn(
    process.platform === "win32" ? "uv.exe" : "uv",
    [
      "run",
      "--no-sync",
      "novel-api",
      "--data-root",
      dataRoot,
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--webui-dist",
      distRoot,
    ],
    { cwd: apiRoot, env: environment, stdio: "inherit", windowsHide: true },
  );

  child.once("error", (error) => {
    console.error("Unable to start the E2E API:", error);
    void stop(1);
  });
  child.once("exit", (code, signal) => {
    if (!stopping) void stop(code ?? (signal ? 1 : 0));
  });
  process.once("SIGINT", () => void stop(130));
  process.once("SIGTERM", () => void stop(143));
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  await stop(1);
}

function parsePort(value) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
    throw new Error("NOVEL_E2E_PORT must be an integer between 1 and 65535");
  }
  return parsed;
}

function assertPortAvailable(requestedPort) {
  return new Promise((resolvePromise, reject) => {
    const probe = createServer();
    probe.once("error", () => {
      probe.close();
      reject(new Error(`E2E port ${requestedPort} is already in use`));
    });
    probe.listen(requestedPort, "127.0.0.1", () => {
      probe.close((closeError) => {
        if (closeError) reject(closeError);
        else resolvePromise();
      });
    });
  });
}

async function stop(code) {
  if (stopping) return;
  stopping = true;
  if (child && child.exitCode === null) {
    child.kill("SIGTERM");
    await new Promise((resolvePromise) => child.once("exit", resolvePromise));
  }
  await rm(dataRoot, { recursive: true, force: true });
  process.exitCode = code;
}
