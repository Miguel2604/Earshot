<script lang="ts">
  // Earshot overlay: one floating glass panel. Suggestion card, then live transcript, then after-call notes.
  // Talks only to the local engine (127.0.0.1:8765), never the internet.
  const ENGINE = "127.0.0.1:8765";
  const CHUNK_SECONDS = 5;

  type Suggestion = { score: number; text: string };
  type Line = { id: number; text: string; en?: string };
  type Signals = { intent: string | null; intent_p: number; mood: number; escalate: boolean };
  type Pick = { value: string; confidence: number; options: string[] };
  type Notes = { category: Pick; priority: Pick; disposition: Pick; summary: string; follow_up: string };
  type Step = { label: string; done: boolean; quote: string };
  type Alert = { rule: string; text: string; hidden?: boolean };
  const PICKS = ["category", "priority", "disposition"] as const;
  const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
  // Model strip: engine `busy` steps -> pill labels; `timings` keys (ms) -> pill (Gemma shows its last job, reply or translate).
  const MODELS = [["whisper", "Whisper"], ["gemma", "Gemma"], ["laya", "Laya"], ["embed", "EmbedGemma"]] as const; // EmbeddingGemma 2; short so 4 timed pills fit 420 px
  const bytes = (b: number) => (b < 1e3 ? `${b} B` : b < 1e6 ? `${(b / 1e3).toFixed(1)} KB` : `${(b / 1e6).toFixed(1)} MB`);

  let engineUp = $state(false);
  let live = $state(false);
  let lines = $state<Line[]>([]);
  let signals = $state<Signals | null>(null);
  let reply = $state("");
  let flagged = $state(false);
  let suggestions = $state<Suggestion[]>([]);
  let notes = $state<Notes | null>(null);
  let writingNotes = $state(false);
  let qa = $state<Step[] | null>(null);
  let alerts = $state<Alert[]>([]); // compliance: agent asked for a CVV/OTP/PIN/password
  let micError = $state("");
  let copied = $state(false);
  let online = $state(true); // navigator.onLine, bound below: shows the demo still works with Wi-Fi off
  let busy = $state<string | null>(null); // model running right now (its pill pulses)
  let times = $state<Record<string, number>>({}); // pill -> last time in ms
  type Egress = { engine_bytes_out: number; engine_remote_conns: number; mac_bytes_out: number };
  let egress = $state<Egress | null>(null);
  let macBase = $state(0); // Mac's bytes out when the call (or the panel) started

  let transcriptEl: HTMLElement;
  $effect(() => {
    lines.length;
    transcriptEl.scrollTop = transcriptEl.scrollHeight; // keep the newest line in view
  });

  let ws: WebSocket | null = null;
  let stopAudio: (() => void) | null = null;

  async function checkEngine() {
    try {
      engineUp = (await fetch(`http://${ENGINE}/health`)).ok;
    } catch {
      engineUp = false;
    }
    if (!engineUp) setTimeout(checkEngine, 2000); // engine takes ~20s to load models on first launch
    else pollEgress();
  }

  // Real egress meter: the engine counts its own non-loopback sockets (nettop) and the Mac's bytes out (netstat).
  async function pollEgress() {
    try {
      egress = await (await fetch(`http://${ENGINE}/egress`)).json();
      if (!macBase) macBase = egress!.mac_bytes_out;
    } catch {}
    setTimeout(pollEgress, 2000);
  }
  checkEngine();

  function openCall(path: string) {
    lines = [];
    signals = null;
    reply = "";
    flagged = false;
    suggestions = [];
    notes = null;
    qa = null;
    alerts = [];
    copied = false;
    busy = null;
    times = {};
    if (egress) macBase = egress.mac_bytes_out;
    ws = new WebSocket(`ws://${ENGINE}${path}`);
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      // Every text field here was PII-masked in the engine before it was sent.
      if (m.type === "transcript") lines = [...lines, { id: m.id, text: m.text }];
      if (m.type === "translation") lines = lines.map((l) => (l.id === m.id ? { ...l, en: m.text } : l));
      if (m.type === "signals") signals = m;
      if (m.type === "reply") reply = m.text;
      if (m.type === "alert") alerts = [...alerts, m];
      if (m.type === "suggestions") suggestions = m.items;
      if (m.type === "busy") busy = m.step;
      if (m.type === "timings")
        times = { ...times, whisper: m.ms.whisper, gemma: m.ms.reply ?? m.ms.translate ?? times.gemma, laya: m.ms.laya ?? times.laya, embed: m.ms.kb ?? times.embed };
      if (m.type === "end") endCall(); // demo call finished
    };
    live = true;
  }

  // Demo-call mode: the engine streams engine/demo/call.wav through the pipeline at real-time pace; we play the audio.
  function playDemo() {
    openCall("/ws/demo");
    const audio = new Audio(`http://${ENGINE}/demo/call.wav`);
    audio.play().catch(() => {}); // transcript still streams if playback is blocked
    stopAudio = () => audio.pause();
  }

  async function startCall() {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
    } catch (e) {
      micError = `Microphone unavailable (${(e as Error).name}). Use Demo call.`;
      return;
    }
    micError = "";
    openCall("/ws/call");
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
  }

  async function endCall() {
    stopAudio?.();
    stopAudio = null;
    ws?.close();
    ws = null;
    live = false;
    busy = null;
    if (!lines.length) return;
    writingNotes = true;
    const post = (path: string) => fetch(`http://${ENGINE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ transcript: lines.map((l) => l.text).join("\n") }),
    }).then((r) => r.json());
    notes = await post("/notes");
    writingNotes = false;
    // Each compliance alert is a failed QA step, on top of Gemma's checklist.
    qa = [...alerts.map((a) => ({ label: `No ${a.rule} ask`, done: false, quote: a.text })), ...(await post("/qa")).steps]; // after notes, so the notes still land in ~2 s; the checklist ~3 s later
  }

  // "Copy to CRM": plain text the agent pastes into the CRM's notes field (includes their edits).
  async function copyNotes() {
    if (!notes) return;
    const n = notes;
    const text = [...PICKS.map((k) => `${cap(k)}: ${cap(n[k].value)}`), `Summary: ${n.summary}`, `Follow-up: ${n.follow_up}`,
      ...(qa ? [`QA: ${qa.filter((q) => q.done).length}/${qa.length}`, ...qa.map((q) => `[${q.done ? "x" : " "}] ${q.label}`)] : [])].join("\n");
    // execCommand runs synchronously inside the click, so it needs no clipboard permission (the browser pane denies
    // navigator.clipboard); navigator.clipboard is the fallback.
    const ta = Object.assign(document.createElement("textarea"), { value: text });
    document.body.append(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    copied = ok || (await navigator.clipboard.writeText(text).then(() => true, () => false));
  }
</script>

<svelte:window bind:online />

<div class="panel" class:done={notes}>
  <header data-tauri-drag-region>
    <strong data-tauri-drag-region>Earshot</strong>
    <span class="badge" data-tauri-drag-region>{engineUp ? "On-device · offline" : "Loading models…"}</span>
    <span class="spacer" data-tauri-drag-region></span>
    {#if live}
      <button class="primary" onclick={endCall}>End call</button>
    {:else}
      <button class="secondary" disabled={!engineUp} onclick={playDemo}>Demo call</button>
      <button class="primary" disabled={!engineUp} onclick={startCall}>Start call</button>
    {/if}
  </header>

  <!-- Which local model is working right now, and how long each took on the last chunk. -->
  <div class="models">
    {#each MODELS as [k, label]}
      <span class="model" class:busy={busy === k} title={k === "embed" ? "EmbeddingGemma 2 (KB search)" : undefined}>{label} <b>{times[k] != null ? `${(times[k] / 1000).toFixed(2)}s` : "–"}</b></span>
    {/each}
  </div>

  <section class="card suggest">
    <h2><span class="ai">AI</span> Say this</h2>
    {#if reply}<p class="reply">{reply}</p>{/if}
    {#each suggestions as s, i}
      <article class:top={i === 0}>
        <small>{Math.round(s.score * 100)}% match</small>
        <p>{s.text}</p>
      </article>
    {:else}<p class="muted">Suggested replies and procedures appear here as the customer talks.</p>{/each}
  </section>

  {#each alerts as a}
    {#if !a.hidden}
      <div class="escalate alert" role="alert">
        <span>{a.text}</span>
        <button class="secondary" onclick={() => (a.hidden = true)}>Dismiss</button>
      </div>
    {/if}
  {/each}

  {#if signals}
    <!-- Laya's live read of the call: a hint for the agent, never an action. -->
    <div class="signals">
      {#if signals.intent}<span class="chip">{signals.intent[0].toUpperCase() + signals.intent.slice(1)} · {signals.intent_p.toFixed(2)}</span>{/if}
      <span class="mood-label">Mood</span>
      <span class="meter" title="Smoothed over the last 3 chunks"><span style="width: {Math.round(signals.mood * 100)}%"></span></span>
      <span class="mood-label">{signals.mood >= 0.5 ? "Upset" : signals.mood >= 0.25 ? "Tense" : "Calm"}</span>
    </div>
    {#if signals.escalate}
      <div class="escalate">
        <span>Customer escalating. De-escalation script pinned.</span>
        <button class="secondary" disabled={flagged} onclick={() => (flagged = true)}>{flagged ? "Supervisor flagged" : "Flag supervisor"}</button>
      </div>
    {/if}
  {/if}

  <section class="card transcript" bind:this={transcriptEl}>
    <h2>Live transcript</h2>
    {#each lines.slice(-6) as line}<p>{line.text}{#if line.en}<span class="en">{line.en}</span>{/if}</p>{:else}<p class="muted">{micError || "Start a call to see the transcript."}</p>{/each}
  </section>

  {#if writingNotes || notes}
    <section class="card notes">
      <h2><span class="ai">AI</span> Call notes</h2>
      {#if writingNotes}<p class="muted">Writing notes…</p>
      {:else if notes}
        <!-- Dropdowns: Laya's pick from a fixed list (with confidence). Text: Gemma's draft. All editable. -->
        <div class="picks">
          {#each PICKS as k}
            <label>{cap(k)} <small>{notes[k].confidence.toFixed(2)}</small>
              <select bind:value={notes[k].value} onchange={() => (copied = false)}>
                {#each notes[k].options as o}<option value={o}>{cap(o)}</option>{/each}
              </select>
            </label>
          {/each}
        </div>
        <!-- QA checklist: Gemma ticks a step only with a quote from the call (hover it); click to correct. -->
        <div class="qa">
          <span class="qa-title">QA {qa ? `${qa.filter((q) => q.done).length}/${qa.length}` : "checking…"}</span>
          {#each qa ?? [] as q}
            <button class="step" class:done={q.done} title={q.quote || "Not found in the call"} onclick={() => { q.done = !q.done; copied = false; }}>{q.done ? "✓" : "–"} {q.label}</button>
          {/each}
        </div>
        <label>Summary <textarea rows="3" bind:value={notes.summary} oninput={() => (copied = false)}></textarea></label>
        <label>Follow-up <textarea rows="2" bind:value={notes.follow_up} oninput={() => (copied = false)}></textarea></label>
        <button class="primary copy" onclick={copyNotes}>{copied ? "Copied to clipboard" : "Copy to CRM"}</button>
      {/if}
    </section>
  {/if}

  <!-- Live egress: the Mac's counter moves (other apps), Earshot's engine stays at 0. PII is masked in the engine. -->
  <footer>
    <span class="egress" title="Bytes out since the call started (whole Mac) vs. the Earshot engine's non-local traffic">
      {#if egress}This Mac: {bytes(Math.max(0, egress.mac_bytes_out - macBase))} out · <b>Earshot: {bytes(egress.engine_bytes_out)}, {egress.engine_remote_conns} connections</b>{:else}Measuring network…{/if}
    </span>
    <span class="row"><span><span class="net" class:off={!online}></span>{online ? "Online" : "Offline"}</span><span>PII masked on-device</span></span>
  </footer>
</div>

<style>
  /* Cluely-style clear glass: no native vibrancy (every macOS material blurs the desktop away), an 8% wash plus a light
     6px backdrop-filter, which in the transparent Tauri window frosts the desktop itself. Text shadows, not a tint, carry legibility.
     Light coral only for AI elements, headings 400–500, no web fonts (the app must work offline). */
  :global(:root) {
    --canvas: rgba(255, 255, 255, 0.1);
    --surface: rgba(255, 255, 255, 0.05);
    --surface-soft: rgba(255, 255, 255, 0.1);
    --hairline: rgba(255, 255, 255, 0.14);
    --surface-strong: rgba(255, 255, 255, 0.18);
    --ink: #ffffff;
    --body: rgba(255, 255, 255, 0.9);
    --muted: rgba(255, 255, 255, 0.68);
    --primary: rgba(255, 255, 255, 0.94);
    --primary-active: rgba(255, 255, 255, 0.75);
    --ai: #ff9470; /* signature coral, lightened to read on dark glass */
    --ai-tint: rgba(255, 148, 112, 0.16);
    --ai-line: rgba(255, 148, 112, 0.55);
    --border-strong: rgba(255, 255, 255, 0.4);
    --success-border: #4ade80;
    color-scheme: dark;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--body);
    background: transparent;
  }
  :global(body) { margin: 0; background: transparent; overflow: hidden; }
  /* Fills the window. Almost clear (8% wash) like Cluely; the text shadow, not a tint, keeps text readable on light and busy backdrops. */
  .panel { box-sizing: border-box; height: 100vh; display: flex; flex-direction: column; gap: 10px; padding: 0 12px 12px;
    background: rgba(20, 20, 24, 0.08); backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
    border: 1px solid rgba(255, 255, 255, 0.22); border-radius: 16px; box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
    text-shadow: 0 0 1px rgba(0, 0, 0, 0.9), 0 1px 3px rgba(0, 0, 0, 0.75), 0 0 8px rgba(0, 0, 0, 0.45); overflow: hidden; }
  header { display: flex; align-items: center; gap: 6px; flex: none; height: 52px; margin: 0 -12px; padding: 0 12px 0 16px; border-bottom: 1px solid var(--hairline); color: var(--ink); cursor: grab; user-select: none; }
  header strong { font-weight: 500; font-size: 16px; }
  header button { padding: 6px 12px; } /* idle header (badge + 2 buttons) must fit a 420px window */
  .spacer { flex: 1; align-self: stretch; }
  .badge { font-weight: 500; font-size: 12px; line-height: 1.35; letter-spacing: 0.16px; color: var(--muted); background: var(--surface-soft); border: 1px solid var(--hairline); padding: 2px 9px; border-radius: 999px; white-space: nowrap; }
  button { font-family: inherit; font-weight: 500; font-size: 14px; line-height: 1.4; padding: 7px 14px; border-radius: 999px; border: 0; cursor: pointer; white-space: nowrap; text-shadow: none; }
  button.primary { background: var(--primary); color: #111317; }
  button.primary:active { background: var(--primary-active); }
  button.secondary { background: var(--canvas); color: var(--ink); border: 1px solid var(--hairline); }
  button.secondary:hover:not(:disabled) { background: var(--surface-strong); }
  button:disabled { opacity: 0.4; cursor: default; }
  .card { background: var(--surface); border: 1px solid var(--hairline); border-radius: 14px; padding: 14px 16px; overflow-y: auto; min-height: 0; }
  .suggest { flex: 0 1 auto; max-height: 45%; border-color: var(--ai-line); }
  .transcript { flex: 1 1 0; min-height: 96px; }
  .notes { flex: 2 1 0; min-height: 0; }
  .done .suggest { max-height: 22%; } /* call over: the notes are what the agent works on now */
  h2 { font-weight: 500; font-size: 13px; line-height: 1.5; letter-spacing: 0.2px; color: var(--muted); margin: 0 0 10px; display: flex; align-items: center; gap: 8px; }
  .ai { font-weight: 500; font-size: 11px; line-height: 1.4; color: var(--ai); background: var(--ai-tint); border: 1px solid var(--ai-line); padding: 1px 8px; border-radius: 999px; }
  p { font-size: 14px; line-height: 1.5; margin: 0 0 8px; white-space: pre-line; }
  .muted { color: var(--muted); }
  .reply { font-size: 16px; line-height: 1.45; color: var(--ink); margin-bottom: 12px; }
  .en { display: block; font-size: 13px; color: var(--muted); font-style: italic; }
  .signals { flex: none; display: flex; align-items: center; gap: 8px; padding: 0 4px; }
  .chip { font-weight: 500; font-size: 12px; line-height: 1.35; letter-spacing: 0.16px; color: var(--ai); background: var(--ai-tint); border: 1px solid var(--ai-line); padding: 2px 9px; border-radius: 999px; white-space: nowrap; }
  .mood-label { font-weight: 500; font-size: 12px; color: var(--muted); }
  .meter { flex: 1; height: 6px; border-radius: 3px; background: var(--surface-strong); overflow: hidden; }
  .meter span { display: block; height: 100%; background: var(--ai); transition: width 0.6s ease; }
  .escalate { flex: none; display: flex; align-items: center; gap: 8px; justify-content: space-between; padding: 7px 7px 7px 14px; border-radius: 14px; background: var(--ai-tint); border: 1px solid var(--ai-line); color: var(--ai); font-weight: 500; font-size: 13px; line-height: 1.35; }
  .alert { background: rgba(255, 90, 90, 0.18); border-color: rgba(255, 110, 110, 0.65); color: #ff8a8a; }
  .escalate button { padding: 5px 11px; font-size: 13px; }
  article { background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 10px 12px; margin-bottom: 8px; }
  article.top { border-color: var(--ai-line); }
  small { font-weight: 500; font-size: 12px; line-height: 1.35; letter-spacing: 0.16px; color: var(--muted); }
  .models { flex: none; display: flex; gap: 4px; margin-top: -2px; }
  .model { flex: 1 1 auto; text-align: center; font-weight: 500; font-size: 11px; line-height: 1.35; color: var(--muted); background: var(--surface); border: 1px solid var(--hairline); padding: 2px 6px; border-radius: 999px; white-space: nowrap; transition: color 0.2s, background 0.2s, border-color 0.2s; }
  .model b { font-weight: 500; color: var(--ink); font-variant-numeric: tabular-nums; }
  .model.busy { color: var(--ai); background: var(--ai-tint); border-color: var(--ai-line); box-shadow: 0 0 10px var(--ai-line); animation: pulse 0.6s ease-in-out infinite alternate; }
  .model.busy b { color: var(--ai); }
  /* opacity only: compositor-side, no per-frame repaint under the panel's backdrop-filter */
  @keyframes pulse { from { opacity: 1; } to { opacity: 0.7; } }
  .egress b { font-weight: 500; color: var(--ink); }
  footer .row { display: flex; justify-content: space-between; }
  footer { flex: none; display: flex; flex-direction: column; gap: 3px; font-weight: 500; font-size: 12px; line-height: 1.35; letter-spacing: 0.16px; color: var(--muted); padding: 0 4px; }
  .net { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; background: var(--border-strong); }
  .net.off { background: var(--success-border); }
  .picks { display: flex; gap: 8px; }
  .picks label { flex: 1; min-width: 0; }
  label { display: block; font-weight: 500; font-size: 12px; line-height: 1.35; color: var(--muted); margin-bottom: 10px; }
  select, textarea { display: block; box-sizing: border-box; width: 100%; margin-top: 4px; font: inherit; font-size: 14px; line-height: 1.4; color: var(--ink);
    background: rgba(0, 0, 0, 0.22); border: 1px solid var(--hairline); border-radius: 8px; padding: 6px 8px; }
  option { background: #1c1f24; color: #fff; }
  textarea { resize: vertical; }
  select:focus, textarea:focus { outline: 2px solid rgba(255, 255, 255, 0.45); outline-offset: -1px; }
  .copy { width: 100%; }
  .qa { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 12px; }
  .qa-title { font-weight: 500; font-size: 12px; color: var(--muted); margin-right: 2px; }
  .step { font-size: 12px; line-height: 1.35; padding: 3px 9px; background: var(--canvas); color: var(--muted); border: 1px solid var(--hairline); }
  .step.done { color: var(--ai); background: var(--ai-tint); border-color: var(--ai-line); }
</style>
