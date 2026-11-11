/* End-to-end test of the TITAN shell against a real TITAN Core.
 *
 *   TITAN_E2E_URL   shell URL (default http://127.0.0.1:5173)
 *   TITAN_E2E_HOME  the TITAN_HOME that core is serving (a scratch directory!)
 *   TITAN_E2E_SHOTS optional directory for screenshots
 *
 * Run with: node e2e/shell.e2e.cjs      (see TESTING.md for starting core)
 */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const URL = process.env.TITAN_E2E_URL || "http://127.0.0.1:5173";
const HOME = process.env.TITAN_E2E_HOME;
const SHOTS = process.env.TITAN_E2E_SHOTS;
if (!HOME) throw new Error("Set TITAN_E2E_HOME to the scratch home directory core is using");

const results = [];
async function step(name, fn) {
  try { await fn(); results.push(["PASS", name]); console.log("PASS", name); }
  catch (e) { results.push(["FAIL", name]); console.log("FAIL", name, "\n   ", String(e.message).split("\n").slice(0, 4).join("\n    ")); }
}
const exists = (p) => fs.existsSync(path.join(HOME, p));
async function until(fn, ms = 4000) { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await new Promise((r) => setTimeout(r, 80)); } return false; }

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: SHOTS ? 2 : 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !/50[23]|Failed to load resource/.test(m.text())) errors.push(m.text()); });
  const shot = async (n) => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, n + ".png") }); };
  const win = (title) => page.getByRole("dialog", { name: title, exact: true });
  const dock = (label) => page.getByRole("navigation", { name: "Dock" }).getByRole("button", { name: label, exact: true });
  const approval = () => page.getByRole("alertdialog", { name: "Approval required" });

  page.setDefaultTimeout(5000);
  await page.goto(URL);

  await step("connects to core and opens the startup app with live data", async () => {
    await page.getByRole("status", { name: "Core live" }).waitFor({ timeout: 8000 });
    await win("Home").waitFor();
    await win("Home").getByText(/\d+ cores · load/).waitFor({ timeout: 6000 });
    await win("Home").getByText("No API key set").waitFor();
    await shot("01-home");
  });

  await step("launcher searches installed applications and launches one", async () => {
    await page.keyboard.press("Control+k");
    const l = page.getByRole("dialog", { name: "Application launcher" });
    await l.getByRole("textbox").fill("fire");
    await l.getByText("Firefox Web Browser").waitFor();
    await shot("02-launcher");
    await page.keyboard.press("Enter");
    assert(await until(() => fs.existsSync(path.join(HOME, "..", "launched"))), "application Exec line did not run");
    await l.waitFor({ state: "hidden" });
  });

  await step("files: browse, preview, create folder", async () => {
    await dock("Files").click();
    const f = win("Files");
    await f.getByRole("button", { name: "Documents" }).click();
    await f.getByRole("button", { name: "notes.txt" }).click();
    await f.getByText("hello from titan").waitFor();
    page.once("dialog", (d) => d.accept("Projects"));
    await f.getByRole("button", { name: "New folder" }).click();
    await f.getByRole("button", { name: "Projects" }).waitFor();
    assert(exists("Documents/Projects"));
  });

  await step("files: permanent delete asks first; Deny keeps the file, Approve removes it", async () => {
    const f = win("Files");
    await f.getByRole("checkbox", { name: "Select notes.txt" }).check();
    await f.getByRole("button", { name: "Delete permanently" }).click();
    await approval().getByText("high risk").waitFor();
    await shot("03-approval");
    assert(exists("Documents/notes.txt"), "file was deleted before approval");
    await approval().getByRole("button", { name: "Deny" }).click();
    await approval().waitFor({ state: "hidden" });
    assert(exists("Documents/notes.txt"), "file was deleted after Deny");
    await f.getByRole("checkbox", { name: "Select notes.txt" }).check();
    await f.getByRole("button", { name: "Delete permanently" }).click();
    await approval().getByRole("button", { name: "Approve" }).click();
    await f.getByRole("button", { name: "notes.txt" }).waitFor({ state: "hidden" });
    assert(!exists("Documents/notes.txt"));
  });

  await step("terminal: read-only runs directly, writes wait for approval and report the real result", async () => {
    await dock("Terminal").click();
    const t = win("Terminal");
    const cmd = t.getByRole("textbox", { name: "Command" });
    await cmd.fill("echo titan-$((6*7))"); await cmd.press("Enter");
    await approval().waitFor({ timeout: 3000 });  // arithmetic expansion is not on the read-only allowlist
    await approval().getByRole("button", { name: "Deny" }).click();
    await t.getByText("You declined this command. It did not run.").waitFor();
    await cmd.fill("echo plain-output && pwd"); await cmd.press("Enter");
    await t.getByText("plain-output").nth(1).waitFor();
    await t.getByText("exit 0").waitFor();
    await cmd.fill("touch made-by-terminal.txt"); await cmd.press("Enter");
    await approval().getByText("touch made-by-terminal.txt").first().waitFor();
    assert(!exists("made-by-terminal.txt"));
    await approval().getByRole("button", { name: "Approve" }).click();
    await t.getByText("exit 0").nth(1).waitFor();
    assert(exists("made-by-terminal.txt"));
    await cmd.fill("ls /definitely-missing"); await cmd.press("Enter");
    await t.getByRole("button", { name: "Explain this error" }).waitFor();
    await shot("04-terminal");
  });

  await step("windows: focus, move, resize, maximize, minimize, restore, close", async () => {
    const t = win("Terminal");
    const before = await t.boundingBox();
    const bar = t.locator("header").first();
    const b = await bar.boundingBox();
    await page.mouse.move(b.x + 120, b.y + 15); await page.mouse.down(); await page.mouse.move(b.x + 220, b.y + 95, { steps: 5 }); await page.mouse.up();
    const moved = await t.boundingBox();
    assert(Math.abs(moved.x - before.x - 100) < 3 && Math.abs(moved.y - before.y - 80) < 3, `did not move: ${JSON.stringify([before, moved])}`);
    const h = await t.getByTestId("resize-se").boundingBox();
    await page.mouse.move(h.x + 5, h.y + 5); await page.mouse.down(); await page.mouse.move(h.x + 65, h.y + 45, { steps: 5 }); await page.mouse.up();
    const sized = await t.boundingBox();
    assert(Math.abs(sized.width - moved.width - 60) < 3 && Math.abs(sized.height - moved.height - 40) < 3, "did not resize");
    await t.getByRole("button", { name: "Maximize" }).click();
    assert((await t.boundingBox()).width > 1400, "did not maximize");
    await t.getByRole("button", { name: "Restore" }).click();
    assert(Math.abs((await t.boundingBox()).width - sized.width) < 3, "did not restore size");
    await win("Files").locator("header").first().click({ position: { x: 100, y: 10 } });
    assert.equal(await win("Files").getAttribute("data-focused"), "true");
    assert.equal(await t.getAttribute("data-focused"), "false");
    await dock("Terminal").click();  // clicking a background app's dock icon brings it to the front
    assert.equal(await t.getAttribute("data-focused"), "true");
    await t.getByRole("button", { name: "Minimize" }).click();
    await t.waitFor({ state: "hidden" });
    await dock("Terminal").click();
    await t.waitFor();
    await t.getByText("plain-output").first().waitFor();  // state survived minimize
    await page.keyboard.press("Alt+w");
    await t.waitFor({ state: "hidden" });
  });

  await step("workspaces: windows stay on their workspace", async () => {
    const current = async () => page.locator('nav[aria-label="Workspaces"] [aria-current="true"]').innerText();
    await page.keyboard.press("Alt+2");
    assert(await until(async () => (await current()).trim() === "2"), "Alt+2 did not switch workspace");
    assert.equal(await page.getByRole("dialog").count(), 0);
    await dock("System Monitor").click();
    await win("System Monitor").getByText("Processes").waitFor();
    await win("System Monitor").getByText(/CPU 0/).waitFor({ timeout: 6000 });
    await shot("05-monitor");
    await page.getByRole("button", { name: "Workspace 1" }).click();
    await win("Files").waitFor();
    assert.equal(await win("System Monitor").count(), 0);
    await dock("System Monitor").click();  // clicking a running app jumps to its workspace
    assert(await until(async () => (await current()).trim() === "2"));
    await win("System Monitor").waitFor();
    await page.keyboard.press("Alt+w");
    await page.keyboard.press("Alt+1");
  });

  await step("assistant reports honestly when no API key is configured", async () => {
    await page.keyboard.press("Control+j");
    const a = win("Assistant");
    await a.getByRole("textbox", { name: "Message" }).fill("Create a folder called FromAI");
    await a.getByRole("button", { name: "Send" }).click();
    await a.getByRole("alert").waitFor({ timeout: 20000 });
    const msg = await a.getByRole("alert").innerText();
    assert(/credential|API key|ANTHROPIC/i.test(msg), `unexpected error text: ${msg}`);
    assert(!exists("FromAI"), "folder was created without the model");
    await shot("06-assistant");
    await page.keyboard.press("Alt+w");
  });

  await step("memory: add, search, delete", async () => {
    await page.keyboard.press("Control+k");
    await page.getByRole("dialog", { name: "Application launcher" }).getByRole("textbox").fill("memory");
    await page.keyboard.press("Enter");
    const m = win("Memory");
    await m.getByRole("textbox", { name: "New memory" }).fill("Prefers dark mode");
    await m.getByRole("button", { name: "Add" }).first().click();
    await m.getByText("Prefers dark mode").waitFor();
    await m.getByRole("textbox", { name: "Search memory" }).fill("zzz");
    await m.getByText("Nothing matches.").waitFor();
    await m.getByRole("textbox", { name: "Search memory" }).fill("");
    await m.getByRole("button", { name: /Delete memory/ }).click();
    await m.getByText("Nothing stored yet.").waitFor();
    await page.keyboard.press("Alt+w");
  });

  await step("security centre: overview, permissions, audit log of what just happened", async () => {
    await dock("Security Centre").click();
    const s = win("Security Centre");
    await s.getByText("Alerts").waitFor({ timeout: 30000 });
    await s.getByRole("tab", { name: "Audit log" }).click();
    await s.getByRole("cell", { name: "fs.delete" }).first().waitFor();
    await s.getByRole("cell", { name: "approval.deny" }).first().waitFor();
    await s.getByRole("tab", { name: "permissions" }).click();
    await s.getByLabel("Terminal commands permission").selectOption("deny");
    await shot("07-security");
    await dock("Terminal").click();
    const cmd = win("Terminal").getByRole("textbox", { name: "Command" });
    await cmd.fill("echo should-not-run"); await cmd.press("Enter");
    await win("Terminal").getByText("permission is set to deny").waitFor();
    await page.keyboard.press("Alt+w");
    await s.getByLabel("Terminal commands permission").selectOption("default");
    await page.keyboard.press("Alt+w");
  });

  await step("settings: theme and accent apply and persist across reload", async () => {
    await dock("Settings").click();
    const s = win("Settings");
    await s.getByRole("button", { name: "light", exact: true }).click();
    assert(await until(async () => (await page.evaluate(() => document.documentElement.dataset.theme)) === "light"));
    await s.getByRole("button", { name: "Accent #3b9dff" }).click();
    await shot("08-settings-light");
    await s.getByRole("tab", { name: "Voice" }).click();
    await s.getByText("Speech-to-text").waitFor();
    await s.getByRole("tab", { name: "System" }).click();
    await s.getByText("Storage").waitFor();
    await page.waitForTimeout(400);
    await page.reload();
    await page.getByRole("status", { name: "Core live" }).waitFor({ timeout: 8000 });
    assert(await until(async () => (await page.evaluate(() => document.documentElement.dataset.theme)) === "light"), "theme not persisted");
    assert.equal(await page.evaluate(() => document.documentElement.style.getPropertyValue("--color-accent")), "#3b9dff");
    await dock("Settings").click();
    await win("Settings").getByRole("button", { name: "dark", exact: true }).click();
    await win("Settings").getByRole("button", { name: "Accent #8b5cf6" }).click();
    await page.waitForTimeout(300);
  });

  await step("notifications arrive live and can be read", async () => {
    await page.evaluate(() => fetch("/api/actions/notify.send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ params: { title: "Build finished", body: "All green" } }) }));
    await page.getByText("Build finished").first().waitFor();
    await page.getByRole("button", { name: /Notifications, 1 unread/ }).click();
    await page.getByRole("complementary", { name: "Notifications" }).getByText("All green").waitFor();
    await page.getByRole("button", { name: "Mark read" }).click();
    await page.getByRole("button", { name: /Notifications, 0 unread/ }).waitFor();
    await page.keyboard.press("Escape");
  });

  await step("no unexpected browser errors", async () => { assert.deepEqual(errors, []); });

  await shot("09-final");
  await browser.close();
  const failed = results.filter((r) => r[0] === "FAIL").length;
  console.log(`\n${results.length - failed}/${results.length} steps passed`);
  process.exit(failed ? 1 : 0);
})();
