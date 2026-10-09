// Draws compose.html frame by frame in headless Chrome and encodes docs/demo-video.mp4 with the demo call's audio.
// Usage: NODE_PATH=<dir with puppeteer-core> node render.cjs <workdir> --backdrop   (writes <workdir>/backdrop.png)
//        NODE_PATH=... node render.cjs <workdir> [out.mp4] [--stills t1,t2,...]   (after capture.cjs)
const fs = require("fs"), path = require("path"), { spawn } = require("child_process"), puppeteer = require("puppeteer-core");
const ROOT = path.resolve(__dirname, "../.."), W = path.resolve(process.argv[2]), FPS = 30;
const arg = (k) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : null; };
const OUT = process.argv[3] && !process.argv[3].startsWith("--") ? path.resolve(process.argv[3]) : path.join(ROOT, "docs/demo-video.mp4");

(async () => {
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true,
    args: ["--allow-file-access-from-files"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto("file://" + path.join(__dirname, "compose.html"));
  if (process.argv.includes("--backdrop")) {
    await page.evaluate(() => document.querySelectorAll(".layer").forEach((e) => (e.style.display = "none")));
    await page.screenshot({ path: path.join(W, "backdrop.png") });
    return browser.close();
  }
  const D = JSON.parse(fs.readFileSync(path.join(W, "panel.json")));
  D.frames.forEach((f) => (f.f = "file://" + path.join(W, f.f)));
  const T = await page.evaluate((D) => window.setup(D), D);
  console.log("timeline", JSON.stringify({ ...T, caps: T.caps.map((c) => [c[0].toFixed(1), c[1].toFixed(1), c[3]]) }));

  if (arg("--stills")) { // check frames: <workdir>/still-<t>.png
    for (const t of arg("--stills").split(",").map(Number)) {
      await page.evaluate((t) => window.seek(t), t);
      await page.screenshot({ path: path.join(W, `still-${t}.png`) });
    }
    return browser.close();
  }

  const d = T.duration.toFixed(2), music = (len, fi, fo) => // soft A-major pad for the title and end cards
    `aevalsrc='0.07*(sin(2*PI*220*t)+sin(2*PI*277.18*t)+sin(2*PI*329.63*t)+0.6*sin(2*PI*440.7*t)+0.4*sin(2*PI*110*t))*(0.75+0.25*sin(2*PI*0.2*t))':s=48000:d=${len},` +
    `lowpass=f=1400,aecho=0.8:0.6:180|320:0.25|0.15,afade=t=in:d=${fi},afade=t=out:st=${len - fo}:d=${fo}`;
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", FPS, "-i", "-",
    "-i", path.join(ROOT, "engine/demo/call.wav"), "-filter_complex",
    `[1:a]aresample=48000,adelay=${Math.round(T.click * 1000)}[call];` +
    `${music(T.click + 1.5, 0.6, 2.2)}[m1];${music(T.outro[1] - T.outro[0], 1.2, 1.8)},adelay=${Math.round(T.outro[0] * 1000)}[m2];` +
    `[call][m1][m2]amix=inputs=3:normalize=0:duration=longest,alimiter=limit=0.95,atrim=0:${d},pan=stereo|c0=c0|c1=c0[a]`,
    "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", FPS,
    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", d, OUT], { stdio: ["pipe", "inherit", "inherit"] });
  const n = Math.round(T.duration * FPS);
  for (let i = 0; i < n; i++) {
    await page.evaluate((t) => window.seek(t), i / FPS);
    const buf = await page.screenshot({ type: "jpeg", quality: 94 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    if (i % 300 === 0) console.log(`frame ${i}/${n}`);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
  await browser.close();
  console.log("wrote", OUT);
})();
