// Open one page in headless Chrome with Playwright and keep it open until told to stop (story S-232, tools/test_models.py).
//
//   node tools/chrome_page.mjs --url http://127.0.0.1:PORT/tests/runner/models.html --hf-dir DIR [--flag --use-fake-device-for-media-stream ...]
//
// Why Playwright and not a command line to chrome.exe: it starts Chrome with its own temporary profile, and ends it cleanly
// when this script ends, which it does when its standard input is closed (the Python test closes it) or after --timeout seconds.
//
// The page can ask for two things through functions this script adds to it:
//   setHuggingFace(mode)   "files" (default): requests to huggingface.co are answered from --hf-dir, by file name, with the
//                          headers the real site sends (so the page's own checks run); "offline": they fail as if there
//                          were no connection; "corrupt": the right size, wrong bytes; "live": they go to the real site
//   requestsSoFar()        every request the page and its workers made so far, as [{url, status}], in order
// Nothing else is changed: the page runs as a visitor's would, with the CDN and our own server reached for real.
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";

const PLAYWRIGHT = process.env.PLAYWRIGHT_CORE ?? "file:///C:/Projects/funground-hq.github.io/tools/codemirror/node_modules/playwright-core/index.mjs";
const CHROME = process.env.CHROME ?? "C:/Users/samirj/AppData/Local/Google/Chrome/Application/chrome.exe";
const { chromium } = await import(PLAYWRIGHT);

const argument = (name, fallback = null) => (process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : fallback);
const flags = process.argv.flatMap((value, i) => (process.argv[i - 1] === "--flag" ? [value] : []));
const url = argument("--url");
const hfDir = argument("--hf-dir");
const timeoutSeconds = Number(argument("--timeout", "900"));

const browser = await chromium.launch({
  executablePath: CHROME, headless: true,
  args: ["--headless=new", "--no-first-run", "--no-default-browser-check", "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows", ...flags],
});
const context = await browser.newContext({ viewport: { width: 800, height: 600 } });
let mode = "files";
const requests = [];

await context.route("https://huggingface.co/**", async (route) => {
  const address = route.request().url();
  const entry = { url: address, status: null };
  requests.push(entry);
  const headers = { "access-control-allow-origin": "*", "content-type": "application/octet-stream" };
  if (mode === "offline") { entry.status = "failed"; return route.abort("internetdisconnected"); }
  if (mode === "live") { const response = await route.fetch(); entry.status = response.status(); return route.fulfill({ response }); }
  const file = path.join(hfDir, path.basename(new URL(address).pathname));
  if (!existsSync(file)) { entry.status = 404; return route.fulfill({ status: 404, headers, body: "" }); }
  const body = readFileSync(file);
  if (mode === "corrupt") body.fill(7, 100, 200);                      // the right size, not the right bytes
  entry.status = 200;
  return route.fulfill({ status: 200, headers, body });
});
context.on("request", (request) => {
  if (!request.url().startsWith("https://huggingface.co/")) requests.push({ url: request.url(), status: null });
});
context.on("response", (response) => {
  const entry = requests.findLast((r) => r.url === response.url() && r.status === null);
  if (entry) entry.status = response.status();
});

await context.grantPermissions(["camera"], { origin: new URL(url).origin });     // Chrome's fake camera, as its flag supplies
const page = await context.newPage();
await page.exposeFunction("setHuggingFace", (value) => { mode = value; });
await page.exposeFunction("requestsSoFar", () => requests);
page.on("console", (message) => { if (message.type() === "error") console.error(`page: ${message.text()}`.slice(0, 300)); });
await page.goto(url);

const finish = async () => { await browser.close(); process.exit(0); };
process.stdin.on("end", finish);
process.stdin.resume();
setTimeout(finish, timeoutSeconds * 1000);
