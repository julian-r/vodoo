import assert from "node:assert/strict";
import { spawn } from "node:child_process";

const port = 18799;
const child = spawn(
  "./node_modules/.bin/wrangler",
  [
    "dev",
    "--config",
    "test/worker/wrangler.jsonc",
    "--local",
    "--port",
    String(port),
    "--log-level",
    "error",
    "--show-interactive-dev-session=false",
    "--var",
    "ODOO_URL:https://odoo.example.test/",
    "--var",
    "ODOO_DATABASE:fixture",
    "--var",
    "ODOO_USERNAME:worker",
    "--var",
    "ODOO_PASSWORD:unused",
  ],
  { detached: true, stdio: ["ignore", "pipe", "pipe"] },
);
let output = "";
child.stdout.on("data", (chunk) => {
  output += String(chunk);
});
child.stderr.on("data", (chunk) => {
  output += String(chunk);
});

try {
  let response;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`wrangler exited before the smoke request:\n${output}`);
    }
    try {
      response = await fetch(`http://127.0.0.1:${port}/`);
      break;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  assert.ok(response, `workerd did not become ready:\n${output}`);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    url: "https://odoo.example.test/odoo/project.project/7",
    command: [6, 0, [2, 3]],
    date: "2026-09-20",
  });
} finally {
  const killGroup = (signal) => {
    if (child.pid === undefined) return;
    try {
      process.kill(-child.pid, signal);
    } catch (error) {
      if (error?.code !== "ESRCH") throw error;
    }
  };
  killGroup("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 2_000)),
  ]);
  if (child.exitCode === null) killGroup("SIGKILL");
}
