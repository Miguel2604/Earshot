<script lang="ts">
  // Kasama agent screen: live transcript | knowledge-base suggestions | after-call notes.
  // Talks only to the local engine (127.0.0.1:8765), never the internet.
  const ENGINE = "127.0.0.1:8765";
  const CHUNK_SECONDS = 5;

  type Suggestion = { score: number; text: string };
  type Notes = { issue?: string; resolution?: string; disposition?: string; follow_up?: string; raw?: string };

  let engineUp = $state(false);
  let live = $state(false);
  let lines = $state<string[]>([]);
  let suggestions = $state<Suggestion[]>([]);
  let notes = $state<Notes | null>(null);
  let writingNotes = $state(false);

  let ws: WebSocket | null = null;
  let stopAudio: (() => void) | null = null;

  async function checkEngine() {
    try {
      engineUp = (await fetch(`http://${ENGINE}/health`)).ok;
    } catch {
      engineUp = false;
    }
    if (!engineUp) setTimeout(checkEngine, 2000); // engine takes ~20s to load models on first launch
  }
  checkEngine();

  async function startCall() {
    lines = [];
    suggestions = [];
    notes = null;
    ws = new WebSocket(`ws://${ENGINE}/ws/call`);
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === "transcript") lines = [...lines, m.text];
      if (m.type === "suggestions") suggestions = m.items;
    };
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
    const ctx = new AudioContext({ sampleRate: 16000 });
    const src = ctx.createMediaStreamSource(stream);
    // ponytail: ScriptProcessorNode is deprecated but works in WKWebView/WebView2; move to AudioWorklet if it glitches.
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    let buf: Float32Array[] = [];
    let n = 0;
    proc.onaudioprocess = (e) => {
      buf.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      n += 4096;
      if (n >= 16000 * CHUNK_SECONDS) {
        const chunk = new Float32Array(n);
        let o = 0;
        for (const b of buf) chunk.set(b, (o += b.length) - b.length);
        if (ws?.readyState === WebSocket.OPEN) ws.send(chunk.buffer);
        buf = [];
        n = 0;
      }
    };
    src.connect(proc);
    proc.connect(ctx.destination);
    stopAudio = () => {
      proc.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      ctx.close();
    };
    live = true;
  }

  async function endCall() {
    stopAudio?.();
    ws?.close();
    live = false;
    if (!lines.length) return;
    writingNotes = true;
    const r = await fetch(`http://${ENGINE}/notes`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ transcript: lines.join("\n") }),
    });
    notes = await r.json();
    writingNotes = false;
  }
</script>

<header>
  <strong>Kasama</strong>
  <span class="badge">{engineUp ? "On-device · offline ready" : "Loading local models…"}</span>
  <span class="spacer"></span>
  {#if live}
    <button class="primary" onclick={endCall}>End call</button>
  {:else}
    <button class="primary" disabled={!engineUp} onclick={startCall}>Start call</button>
  {/if}
</header>

<main>
  <section class="card">
    <h2>Live transcript</h2>
    {#each lines as line}<p>{line}</p>{:else}<p class="muted">Start a call to see the transcript.</p>{/each}
  </section>

  <section class="card">
    <h2><span class="ai">AI</span> Suggested procedure</h2>
    {#each suggestions as s, i}
      <article class:top={i === 0}>
        <small>{Math.round(s.score * 100)}% match</small>
        <p>{s.text}</p>
      </article>
    {:else}<p class="muted">Matching procedures appear here as the customer talks.</p>{/each}
  </section>

  <section class="card">
    <h2><span class="ai">AI</span> Call notes</h2>
    {#if writingNotes}<p class="muted">Writing notes…</p>
    {:else if notes}
      <dl>
        {#each Object.entries(notes) as [k, v]}<dt>{k.replace("_", " ")}</dt><dd>{v}</dd>{/each}
      </dl>
    {:else}<p class="muted">Notes are drafted when the call ends.</p>{/if}
  </section>
</main>

<style>
  /* Tokens from DESIGN.md (Airtable analysis): white canvas, hairline cards, near-black ink + primary,
     signature coral reserved for AI elements. No web fonts: the app must work offline. */
  :global(:root) {
    --canvas: #ffffff;
    --surface: #ffffff;
    --surface-soft: #f8fafc;
    --hairline: #dddddd;
    --ink: #181d26;
    --body: #333840;
    --muted: #41454d;
    --primary: #181d26;
    --primary-active: #0d1218;
    --ai: #aa2d00; /* signature coral */
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--body);
    background: var(--canvas);
  }
  :global(body) { margin: 0; }
  header { display: flex; align-items: center; gap: 12px; height: 64px; padding: 0 24px; border-bottom: 1px solid var(--hairline); color: var(--ink); }
  header strong { font-weight: 500; font-size: 18px; }
  .spacer { flex: 1; }
  .badge { font-weight: 500; font-size: 14px; line-height: 1.35; letter-spacing: 0.16px; color: var(--muted); background: var(--surface-soft); border: 1px solid var(--hairline); padding: 4px 10px; border-radius: 6px; }
  button { font-family: inherit; font-weight: 500; font-size: 16px; line-height: 1.4; padding: 10px 20px; border-radius: 12px; border: 0; cursor: pointer; }
  button.primary { background: var(--primary); color: #fff; }
  button.primary:active { background: var(--primary-active); }
  button:disabled { opacity: 0.4; cursor: default; }
  main { display: grid; grid-template-columns: 1fr 1.2fr 1fr; gap: 24px; padding: 24px; height: calc(100vh - 65px - 48px); background: var(--surface-soft); }
  .card { background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 24px; overflow-y: auto; }
  h2 { font-weight: 400; font-size: 20px; line-height: 1.5; color: var(--ink); margin: 0 0 16px; display: flex; align-items: center; gap: 8px; }
  .ai { font-weight: 500; font-size: 12px; line-height: 1.4; color: #fff; background: var(--ai); padding: 2px 8px; border-radius: 6px; }
  p { font-size: 14px; line-height: 1.5; margin: 0 0 12px; white-space: pre-line; }
  .muted { color: var(--muted); }
  article { border: 1px solid var(--hairline); border-radius: 10px; padding: 12px 16px; margin-bottom: 12px; }
  article.top { border-color: var(--ai); }
  small { font-weight: 500; font-size: 14px; line-height: 1.35; letter-spacing: 0.16px; color: var(--muted); }
  dt { font-weight: 500; font-size: 14px; line-height: 1.35; color: var(--muted); text-transform: capitalize; margin-top: 12px; }
  dd { margin: 4px 0 0; font-size: 14px; color: var(--ink); }
</style>
