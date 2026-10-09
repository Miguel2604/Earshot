// Records a real "Demo call" run of the Earshot UI (http://localhost:1420, engine on :8765) in headless Chrome.
// Usage: NODE_PATH=<dir with puppeteer-core> node capture.cjs <workdir>
// Needs <workdir>/backdrop.png (from render.cjs --backdrop). Writes <workdir>/panel/*.jpg + panel.json (frame times, click time, beats).
const fs = require("fs"), path = require("path"), puppeteer = require("puppeteer-core");
const W = process.argv[2], PANEL = { x: 1240, y: 60, s: 960 / 720 }; // where compose.html puts the 420x720 panel on the 1920x1080 canvas
fs.mkdirSync(path.join(W, "panel"), { recursive: true });

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: true, args: ["--mute-audio", "--autoplay-policy=no-user-gesture-required"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 420, height: 720, deviceScaleFactor: 2 });
  await page.goto("http://localhost:1420", { waitUntil: "networkidle0" });
  await page.waitForSelector("button.secondary:not([disabled])", { timeout: 120000 }); // engine up
  // Put the exact slice of the video backdrop behind the glass panel, so its backdrop-filter frosts the same image.
  const bg = "data:image/png;base64," + fs.readFileSync(path.join(W, "backdrop.png")).toString("base64");
  await page.evaluate((bg, p) => {
    const s = document.createElement("style");
    s.textContent = `html,body{background:url(${bg}) ${-p.x / p.s}px ${-p.y / p.s}px / ${1920 / p.s}px ${1080 / p.s}px no-repeat !important}`;
    document.head.append(s);
  }, bg, PANEL);
  await new Promise((r) => setTimeout(r, 3000)); // egress meter's first reading

  const cdp = await page.createCDPSession(), frames = [];
  cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
    const f = `panel/${String(frames.length).padStart(5, "0")}.jpg`;
    fs.writeFileSync(path.join(W, f), Buffer.from(data, "base64"));
    frames.push({ t: metadata.timestamp, f });
    await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 95, everyNthFrame: 1 });
  await new Promise((r) => setTimeout(r, 2000));

  // Boxes (panel CSS px) of the elements the video rings and zooms, sampled through the call (things scroll).
  const rectsOf = () => {
    const box = (el) => el && el.offsetParent && (({ x, y, width: w, height: h }) => ({ x, y, w, h }))(el.getBoundingClientRect());
    const line = (re) => [...document.querySelectorAll(".transcript p")].reverse().find((p) => re.test(p.textContent));
    const $ = (s) => document.querySelector(s), esc = [...document.querySelectorAll(".escalate")].find((e) => /escalating/.test(e.textContent));
    const mood = box($(".signals")), e = box(esc);
    return { pills: box($(".models")), footer: box($("footer")), suggest: box($(".suggest")), alert: box($(".alert")),
      cvv: box(line(/CVV/)), card: box(line(/4821/)), notes: box($(".notes")),
      mood: mood && e ? { x: mood.x, y: mood.y, w: mood.w, h: e.y + e.h - mood.y } : null };
  };
  const track = [];
  const demoBtn = await page.evaluate(() => (({ x, y, width: w, height: h }) => ({ x, y, w, h }))(document.querySelector("button.secondary").getBoundingClientRect()));
  const beats = {}, click = Date.now() / 1000;
  await page.click("button.secondary"); // "Demo call"
  const checks = {
    subtitle: () => !!document.querySelector(".transcript .en"),
    billing: () => /Billing/.test(document.querySelector(".signals")?.textContent || ""),
    reply: () => !!document.querySelector(".reply"),
    cvv: () => !!document.querySelector(".alert"),
    card: () => /4821/.test(document.querySelector(".transcript")?.textContent || ""),
    escalate: () => /escalating/.test(document.body.textContent),
    notes: () => !!document.querySelector(".picks"),
    qa: () => /QA \d/.test(document.body.textContent),
  };
  while (!beats.qa || Date.now() / 1000 - click < beats.qa + 4) {
    for (const [k, fn] of Object.entries(checks))
      if (!beats[k] && (await page.evaluate(fn))) {
        beats[k] = +(Date.now() / 1000 - click).toFixed(1);
      }
    track.push({ t: Date.now() / 1000 - click, r: await page.evaluate(rectsOf) });
    if (beats.escalate && !beats.cleared && !(await page.evaluate(checks.escalate))) beats.cleared = +(Date.now() / 1000 - click).toFixed(1);
    if (Date.now() / 1000 - click > 110) break;
    await new Promise((r) => setTimeout(r, 150));
  }
  await cdp.send("Page.stopScreencast");
  fs.writeFileSync(path.join(W, "panel.json"), JSON.stringify({ click, beats, demoBtn, track, frames }, null, 1));
  console.log("beats", beats, "frames", frames.length);
  await browser.close();
})();
