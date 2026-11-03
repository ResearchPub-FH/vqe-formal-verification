/* Companion prototype: guided tour + logical explorer.
   Reads window.VQE_DATA (data.js, built by build_data.py from merged-model-01). No tool is run here. */
(function () {
  "use strict";
  const D = window.VQE_DATA;
  const $ = (id) => document.getElementById(id);
  const cfg = D.config;
  const TERMS = ["YZ", "ZI", "ZZ", "XX"];
  const SCALE = cfg.hamiltonian.coefficient_scale;
  const SHOTS = cfg.shots_per_group;
  const GROUPS = cfg.measurement_groups;
  const updates = D.run.updates;
  const N_UPD = updates.length;
  const SHOTS_PER_ITER = GROUPS.length * SHOTS * 3;

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fi = (n) => Number(n).toLocaleString("en-US");
  const f = (x, d = 3) => (x < 0 ? "−" : "") + Math.abs(x).toFixed(d);
  const pct = (x, d = 1) => (100 * x).toFixed(d) + "%";
  const badge = (text, kind) => `<span class="badge b-${kind}">${esc(text)}</span>`;
  const VERDICT_KIND = { AGREEMENT: "good", DISAGREEMENT: "bad", ASSUMPTION_MISMATCH: "warn", INCONCLUSIVE: "grey",
    PROVED: "good", ESTABLISHED_FOR_GAUSSIAN_MODEL: "good" };
  const vbadge = (v) => badge(v.replace(/_/g, " "), VERDICT_KIND[v] || "grey");

  /* ---------- theme ---------- */
  (function theme() {
    const root = document.documentElement;
    let saved = null;
    try { saved = localStorage.getItem("vqe-theme"); } catch (e) { /* storage unavailable */ }
    if (saved) root.setAttribute("data-theme", saved);
    $("themeBtn").addEventListener("click", () => {
      const dark = root.getAttribute("data-theme")
        ? root.getAttribute("data-theme") === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      const next = dark ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("vqe-theme", next); } catch (e) { /* ignore */ }
    });
  })();

  /* ---------- nav highlight ---------- */
  (function nav() {
    const links = [...document.querySelectorAll("#nav a")];
    const secs = links.map((a) => document.querySelector(a.getAttribute("href")));
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + e.target.id));
      });
    }, { rootMargin: "-30% 0px -60% 0px" });
    secs.forEach((s) => s && obs.observe(s));
  })();

  /* ---------- physics helpers on recorded counts ---------- */
  // Outcome k = (b1 b0), b1 is q1 (q1 ⊗ q0 order). ZI reads q1 only; ZZ, YZ, XX read the parity of both.
  const sign = (term, k) => (term === "ZI" ? ((k >> 1) & 1 ? -1 : 1) : (((k >> 1) ^ k) & 1 ? -1 : 1));
  const groupOf = (term) => GROUPS.findIndex((g) => g.includes(term));
  function expectationFraction(cand, term) {
    const counts = cand.groups[groupOf(term)];
    let num = 0;
    counts.forEach((c, k) => { num += sign(term, k) * c; });
    return { num, den: counts.reduce((a, b) => a + b, 0), counts };
  }

  /* ---------- generic SVG chart ---------- */
  function chart(o) {
    const W = o.w || 560, H = o.h || 250, m = Object.assign({ l: 50, r: 16, t: 14, b: 38 }, o.m || {});
    const [x0, x1] = o.x, [y0, y1] = o.y;
    const X = (v) => m.l + ((v - x0) / (x1 - x0)) * (W - m.l - m.r);
    const Y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.label || "")}">`;
    s += `<g class="grid">`;
    (o.yticks || []).forEach((t) => { s += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(t)}" y2="${Y(t)}"/>`; });
    s += `</g><g class="axis"><line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}"/></g>`;
    (o.yticks || []).forEach((t) => {
      s += `<text x="${m.l - 6}" y="${Y(t) + 4}" text-anchor="end">${o.yfmt ? o.yfmt(t) : t}</text>`;
    });
    (o.xticks || []).forEach((t) => {
      s += `<text x="${X(t)}" y="${H - m.b + 16}" text-anchor="middle">${t}</text>`;
    });
    if (o.xlabel) s += `<text x="${(m.l + W - m.r) / 2}" y="${H - 4}" text-anchor="middle">${esc(o.xlabel)}</text>`;
    if (o.ylabel) s += `<text transform="translate(12 ${(m.t + H - m.b) / 2}) rotate(-90)" text-anchor="middle">${esc(o.ylabel)}</text>`;
    (o.hlines || []).forEach((h) => {
      s += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(h.y)}" y2="${Y(h.y)}" style="stroke:${h.color || "var(--faint)"};stroke-dasharray:${h.dash || "4 4"}"/>`;
      if (h.label) s += `<text x="${h.left ? m.l + 6 : W - m.r}" y="${Y(h.y) + (h.left ? 14 : -5)}" text-anchor="${h.left ? "start" : "end"}" style="fill:${h.color || "var(--muted)"}">${esc(h.label)}</text>`;
    });
    (o.under || []).forEach((u) => { s += u(X, Y); });
    (o.series || []).forEach((sr) => {
      let d = "";
      sr.pts.forEach(([a, b], i) => {
        if (i === 0) d += `M${X(a)},${Y(b)}`;
        else if (sr.step) d += `H${X(a)}V${Y(b)}`;
        else d += `L${X(a)},${Y(b)}`;
      });
      s += `<path d="${d}" style="fill:none;stroke:${sr.color};stroke-width:${sr.width || 2};${sr.dash ? "stroke-dasharray:" + sr.dash : ""}"/>`;
      if (sr.dots) sr.pts.forEach(([a, b]) => { s += `<circle cx="${X(a)}" cy="${Y(b)}" r="2.6" style="fill:${sr.color}"/>`; });
    });
    (o.over || []).forEach((u) => { s += u(X, Y); });
    if (o.hover) {
      const step = (X(x0 + 1) - X(x0));
      o.hover.forEach((hv) => {
        s += `<rect x="${X(hv.x) - step / 2}" y="${m.t}" width="${step}" height="${H - m.t - m.b}" style="fill:transparent"><title>${esc(hv.text)}</title></rect>`;
      });
    }
    return s + "</svg>";
  }

  /* ---------- generic state diagram ---------- */
  let markerSeq = 0;
  function diagram(spec) {
    const id = "mk" + (markerSeq++);
    const mk = (name, color) =>
      `<marker id="${id}-${name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" style="fill:${color}"/></marker>`;
    let s = `<svg class="dg" viewBox="${spec.viewBox}" role="img" aria-label="${esc(spec.label)}"><defs>` +
      mk("n", "var(--faint)") + mk("on", "var(--accent)") + mk("bad", "var(--bad)") + `</defs>`;
    spec.edges.forEach((e) => {
      const cls = ["edge", e.cls || ""].join(" ");
      const m = e.cls && /new|changed/.test(e.cls) ? "bad" : (e.cls && /cut/.test(e.cls) ? "bad" : "n");
      s += `<g class="${cls}" data-edge="${e.id}"><path d="${e.d}" marker-end="url(#${id}-${m})" data-mk="${m}"/>`;
      if (e.label) s += `<text x="${e.lx}" y="${e.ly}" text-anchor="${e.anchor || "middle"}">${esc(e.label)}</text>`;
      s += `</g>`;
    });
    spec.nodes.forEach((n) => {
      const w = n.w || 120, h = n.h || 40;
      s += `<g class="node ${n.cls || ""}" data-node="${n.id}"><rect x="${n.x - w / 2}" y="${n.y - h / 2}" width="${w}" height="${h}" rx="9"/>`;
      s += `<text x="${n.x}" y="${n.y + (n.sub ? -2 : 4)}" text-anchor="middle">${esc(n.text)}</text>`;
      if (n.sub) s += `<text class="sub" x="${n.x}" y="${n.y + 12}" text-anchor="middle">${esc(n.sub)}</text>`;
      if (n.flag) s += `<circle cx="${n.x + w / 2 - 2}" cy="${n.y - h / 2 + 2}" r="8" style="fill:var(--bad)"/><text x="${n.x + w / 2 - 2}" y="${n.y - h / 2 + 6}" text-anchor="middle" style="fill:var(--bg);font-size:11px;font-weight:700">!</text>`;
      s += `</g>`;
    });
    (spec.extra || []).forEach((x) => { s += x; });
    s += `</svg>`;
    return { svg: s, id };
  }
  function highlight(root, nodeId, edgeIds) {
    root.querySelectorAll(".node").forEach((n) => n.classList.toggle("on", n.dataset.node === nodeId));
    root.querySelectorAll(".edge").forEach((e) => {
      const on = (edgeIds || []).includes(e.dataset.edge);
      e.classList.toggle("on", on);
      const p = e.querySelector("path");
      const mid = p.getAttribute("marker-end").replace(/-(n|on|bad)\)$/, on ? "-on)" : `-${p.dataset.mk})`);
      p.setAttribute("marker-end", mid);
    });
  }

  /* ================================================================
     PART 0 — WHY VERIFY
     ================================================================ */
  function renderWhy() {
    const rows = D.why.rows;
    const correct = rows.map((r) => [r.update, r.correct[r.choice]]);
    const swapped = rows.map((r) => [r.update, r.swapped[r.swapped_choice]]);
    const flips = rows.filter((r) => r.choice !== r.swapped_choice);
    const lo = Math.min(D.ground_energy, ...swapped.map((p) => p[1]), ...correct.map((p) => p[1]));
    const hi = Math.max(...swapped.map((p) => p[1]), ...correct.map((p) => p[1]));
    const NAMES = ["current", "−1", "+1"];
    $("whyChart").innerHTML = chart({
      label: "Reported energy per iteration with declared and swapped coefficients",
      x: [0.5, rows.length + 0.5], y: [Math.floor(lo * 10) / 10 - 0.05, Math.ceil(hi * 10) / 10],
      xticks: [1, 5, 10, 15, 20, 25], yticks: [-0.8, -0.6, -0.4, -0.2, 0, 0.2, 0.4].filter((t) => t >= lo - 0.1 && t <= hi + 0.05),
      yfmt: (t) => f(t, 1), xlabel: "iteration", ylabel: "reported energy of the chosen candidate",
      hlines: [{ y: D.ground_energy, label: "reference minimum " + f(D.ground_energy, 4), color: "var(--muted)", left: true }],
      under: [(X, Y) => flips.map((r) => `<line x1="${X(r.update)}" x2="${X(r.update)}" y1="${Y(Math.floor(lo * 10) / 10 - 0.05)}" y2="${Y(Math.floor(lo * 10) / 10 - 0.05) - 8}" style="stroke:var(--bad);stroke-width:3"/>`).join("")],
      series: [
        { pts: correct, color: "var(--series-a)", dots: true },
        { pts: swapped, color: "var(--series-b)", dots: true, dash: "5 3" },
      ],
      hover: rows.map((r) => ({ x: r.update, text: `Iteration ${r.update}\nDeclared: ${f(r.correct[r.choice], 4)} → picks ${NAMES[r.choice]}\nSwapped: ${f(r.swapped[r.swapped_choice], 4)} → picks ${NAMES[r.swapped_choice]}` })),
    });
    $("whyCaption").innerHTML =
      `<span class="legend" style="margin:0"><span><i style="background:var(--series-a)"></i>declared coefficients</span>` +
      `<span><i style="background:var(--series-b)"></i>YZ ↔ XX swapped</span><span><i style="background:var(--bad);height:8px;width:3px"></i>a different candidate would be chosen</span></span>` +
      `Run <span class="mono">${esc(D.run.run_id)}</span>. Hover an iteration to see both choices.`;
    $("whyFlips").textContent = `would choose a different candidate in ${flips.length}`;
    $("whyTotal").textContent = rows.length;
    const fault = D.faults.find((x) => x.fault === "coefficient_swap");
    $("whyFault").innerHTML = `The numeric check N2, which rebuilds each energy from the declared coefficients, reports ${vbadge(fault.vector.N2)} in
      ${fault.detected}/${fault.runs} runs. The temporal replay (DejaVu) accepts ${fault.dejavu_passed}/${fault.runs}, because every step still happens in the right order.
      Catching it takes a check of the arithmetic, not of the order.`;
  }

  /* ================================================================
     PART 1 — MECHANICS
     ================================================================ */
  const S = { iter: 1, cand: null, playTimer: null, play: null };

  function renderOperator() {
    const t = cfg.hamiltonian.terms;
    const parts = TERMS.map((k, i) => {
      const v = t[k] / SCALE;
      return (i === 0 ? (v < 0 ? "−" : "") : (v < 0 ? " − " : " + ")) + Math.abs(v) + "·" + k;
    });
    $("hamiltonian").textContent = "H = " + parts.join("");
    $("eref").textContent = "E_ref = " + f(D.ground_energy, 4);
    $("gap").textContent = String(cfg.success_gap);
    $("shotsPerGroup").textContent = fi(SHOTS);
  }

  function renderCircuit() {
    const y1 = 30, y0 = 84;
    let s = `<svg class="dg" viewBox="0 0 560 120" role="img" aria-label="Four-parameter efficient SU2 circuit">`;
    s += `<text x="8" y="${y1 + 4}">q₁</text><text x="8" y="${y0 + 4}">q₀</text>`;
    s += `<line x1="30" x2="470" y1="${y1}" y2="${y1}" style="stroke:var(--faint)"/><line x1="30" x2="470" y1="${y0}" y2="${y0}" style="stroke:var(--faint)"/>`;
    const gate = (x, y, w, label, sub) =>
      `<g class="node"><rect x="${x - w / 2}" y="${y - 14}" width="${w}" height="28" rx="5"/><text x="${x}" y="${y + 4}" text-anchor="middle" style="font-size:11.5px">${label}${sub ? `<tspan style="font-size:9px" dy="3">${sub}</tspan>` : ""}</text></g>`;
    const pair = (x, w, a, b) => gate(x, y1, w, a[0], a[1]) + gate(x, y0, w, b[0], b[1]);
    s += pair(62, 28, ["H"], ["H"]);
    s += pair(118, 58, ["RZ(θ", "1"], ["RZ(θ", "0"]).replace(/<\/tspan>/g, "</tspan>)");
    s += pair(176, 28, ["Y"], ["Y"]);
    // CX(0 -> 1): control on q0, target on q1
    s += `<line x1="222" x2="222" y1="${y1 - 11}" y2="${y0}" style="stroke:currentColor;stroke-width:1.5"/>`;
    s += `<circle cx="222" cy="${y0}" r="4.5" style="fill:currentColor"/><circle cx="222" cy="${y1}" r="11" style="fill:var(--panel);stroke:currentColor;stroke-width:1.5"/>`;
    s += `<line x1="211" x2="233" y1="${y1}" y2="${y1}" style="stroke:currentColor;stroke-width:1.5"/>`;
    s += pair(268, 28, ["H"], ["H"]);
    s += pair(324, 58, ["RZ(θ", "3"], ["RZ(θ", "2"]).replace(/<\/tspan>/g, "</tspan>)");
    s += pair(382, 28, ["Y"], ["Y"]);
    s += `<rect x="410" y="${y1 - 18}" width="44" height="${y0 - y1 + 36}" rx="6" style="fill:none;stroke:var(--accent);stroke-dasharray:4 3"/>`;
    s += `<text x="432" y="${y0 + 32}" text-anchor="middle" class="lbl">basis</text>`;
    s += `<text x="432" y="${(y1 + y0) / 2 + 4}" text-anchor="middle" style="font-size:10px;fill:var(--accent)">group</text>`;
    const meter = (y) => `<g class="node"><rect x="478" y="${y - 14}" width="34" height="28" rx="5"/><path d="M484,${y + 6} A11,11 0 0 1 506,${y + 6}" style="fill:none;stroke:currentColor"/><line x1="495" y1="${y + 6}" x2="503" y2="${y - 7}" style="stroke:currentColor"/></g>`;
    s += meter(y1) + meter(y0);
    s += `<text x="530" y="${y1 + 4}" class="lbl">b₁</text><text x="530" y="${y0 + 4}" class="lbl">b₀</text>`;
    s += `<text x="${(62 + 176) / 2}" y="114" text-anchor="middle" class="lbl">first rotation layer</text>`;
    s += `<text x="${(268 + 382) / 2}" y="114" text-anchor="middle" class="lbl">second rotation layer</text>`;
    s += `</svg>`;
    $("circuit").innerHTML = s;
  }

  // Shared-execution-model diagram (the paper's eight modes)
  let modeDg;
  function renderModes() {
    const N = (id, x, y, text, sub) => ({ id, x, y, text, sub });
    const spec = {
      viewBox: "0 -34 760 300", label: "Eight modes of the shared execution model",
      nodes: [
        N("init", 70, 50, "Initialize"), N("stop", 220, 50, "Stop check"), N("prep", 370, 50, "Prepare", "bind θ"),
        N("meas", 520, 50, "Measure", "one group"), N("agg", 680, 50, "Aggregate", "energy"),
        N("val", 680, 200, "Validate", "numeric checks"), N("commit", 370, 200, "Commit", "optimizer step"),
        N("term", 220, 200, "Terminal", "DONE / ABORT"),
      ],
      edges: [
        { id: "init-stop", d: "M130,50 L158,50" },
        { id: "stop-prep", d: "M280,50 L308,50", label: "continue", lx: 294, ly: 40 },
        { id: "prep-meas", d: "M430,50 L458,50" },
        { id: "meas-meas", d: "M495,30 C485,-12 555,-12 545,30", label: "next group (×3)", lx: 520, ly: -18 },
        { id: "meas-agg", d: "M580,50 L618,50", label: "3 groups", lx: 599, ly: 40 },
        { id: "agg-val", d: "M680,70 L680,178" },
        { id: "val-prep", d: "M622,186 C560,150 470,120 410,72", label: "next candidate", lx: 548, ly: 128 },
        { id: "val-commit", d: "M620,200 L432,200", label: "3 candidates validated", lx: 526, ly: 216 },
        { id: "commit-stop", d: "M330,180 L252,72", label: "next iteration", lx: 300, ly: 140, anchor: "start" },
        { id: "stop-term", d: "M220,70 L220,178", label: "success / budget", lx: 212, ly: 128, anchor: "end" },
      ],
      extra: [`<text x="220" y="250" text-anchor="middle" class="lbl">any error → ABORT</text>`],
    };
    const d = diagram(spec);
    $("modes").innerHTML = d.svg;
    modeDg = $("modes");
  }

  const OUTCOME_COLORS = ["var(--series-a)", "color-mix(in srgb, var(--series-a) 45%, var(--panel))",
    "var(--series-b)", "color-mix(in srgb, var(--series-b) 45%, var(--panel))"];
  const CAND_NAMES = ["current", "−1", "+1"];

  function idxHtml(index, coord) {
    return "(" + index.map((z, i) => (i === coord ? `<b>${z}</b>` : z)).join(", ") + ")";
  }

  function renderIteration() {
    const u = updates[S.iter - 1];
    $("iterSlider").value = S.iter;
    $("iterMeta").textContent = `iteration ${S.iter} of ${N_UPD} · coordinate ${u.coordinate} · ${fi(u.shots)} shots so far`;
    $("candidates").innerHTML = u.candidates.map((c, ci) => {
      const bars = GROUPS.map((g, gi) => {
        const counts = c.groups[gi];
        const spans = counts.map((n, k) => `<span style="width:${(100 * n) / SHOTS}%;background:${OUTCOME_COLORS[k]}" title="${["00", "01", "10", "11"][k]}: ${n}"></span>`).join("");
        return `<span class="g">${g.join(",")}</span><div class="bar4" id="g-${ci}-${gi}">${spans}</div>`;
      }).join("");
      const rows = TERMS.map((t) => `<tr><td class="mono">${t}</td><td class="num">${f(c.expectations[t], 4)}</td><td class="num">${f(c.contributions[t], 4)}</td></tr>`).join("");
      return `<div class="cand ${ci === u.choice ? "chosen" : ""}" id="cand-${ci}">
        <div style="display:flex;justify-content:space-between;align-items:center"><b>${CAND_NAMES[ci]}</b>${ci === u.choice ? badge("selected", "accent") : ""}</div>
        <div class="idx small">z = ${idxHtml(c.index, u.coordinate)}</div>
        <div class="bars">${bars}</div>
        <table><thead><tr><th>term</th><th class="num">⟨P⟩</th><th class="num">contrib.</th></tr></thead><tbody>${rows}</tbody></table>
        <div style="margin-top:6px">energy <b class="mono">${f(c.energy, 5)}</b> <span class="small muted">· score ${fi(c.score)}</span></div>
      </div>`;
    }).join("");
    $("countLegend").innerHTML = ["00", "01", "10", "11"].map((o, k) => `<span><span class="sw" style="background:${OUTCOME_COLORS[k]}"></span>outcome b₁b₀ = ${o}</span>`).join("") +
      `<span>Each bar is ${fi(SHOTS)} shots of one measurement group.</span>`;
    // trajectory
    const pts = [[0, D.run.ideal_start]].concat(updates.map((x) => [x.update, x.ideal_after]));
    const target = D.ground_energy + cfg.success_gap;
    $("trajChart").innerHTML = chart({
      w: 480, h: 220, label: "Ideal energy of the selected point per iteration",
      x: [0, N_UPD], y: [-0.8, 0.4], xticks: [0, 5, 10, 15, 20, 25], yticks: [-0.8, -0.4, 0, 0.4], yfmt: (t) => f(t, 1),
      xlabel: "iteration", hlines: [{ y: D.ground_energy, label: "E_ref", color: "var(--muted)" },
        { y: target, label: "success threshold (E_ref + " + cfg.success_gap + ")", color: "var(--good)", dash: "2 3", left: true }],
      series: [{ pts, color: "var(--series-a)", dots: true }],
      over: [(X, Y) => `<circle cx="${X(S.iter)}" cy="${Y(u.ideal_after)}" r="6" style="fill:none;stroke:var(--accent);stroke-width:2"/>`],
      hover: pts.map(([x, y]) => ({ x, text: `after iteration ${x}: ideal energy ${f(y, 4)}` })),
    });
    const tr = D.run.terminal;
    $("shotMath").innerHTML = `3 candidates × ${GROUPS.length} groups × ${fi(SHOTS)} shots = <b>${fi(SHOTS_PER_ITER)}</b> physical shots per iteration.
      This run stopped with reason <b>${esc(tr.reason)}</b> after ${tr.updates} iterations and ${fi(tr.physical_shots)} shots,
      at z = (${tr.index.join(", ")}).`;
    renderNumeric();
    highlight(modeDg, null, []);
  }

  function iterationSteps() {
    const steps = [{ m: "stop", e: "stop-prep" }];
    for (let c = 0; c < 3; c++) {
      steps.push({ m: "prep", e: c ? "val-prep" : "stop-prep", c });
      for (let g = 0; g < 3; g++) steps.push({ m: "meas", e: g ? "meas-meas" : "prep-meas", c, g });
      steps.push({ m: "agg", e: "meas-agg", c });
      steps.push({ m: "val", e: "agg-val", c });
    }
    steps.push({ m: "commit", e: "val-commit" });
    steps.push({ m: "stop", e: "commit-stop" });
    return steps;
  }
  function clearPlayMarks() {
    document.querySelectorAll(".bar4.hl, .cand.hl").forEach((x) => x.classList.remove("hl"));
  }
  function stopPlay() {
    clearInterval(S.playTimer); S.playTimer = null;
    $("playModes").textContent = "▶ Play this iteration";
  }
  function playIteration() {
    if (S.playTimer) { stopPlay(); return; }
    const steps = iterationSteps();
    let i = 0;
    $("playModes").textContent = "■ Stop";
    const tick = () => {
      clearPlayMarks();
      if (i >= steps.length) { stopPlay(); return; }
      const st = steps[i++];
      highlight(modeDg, st.m, [st.e]);
      if (st.c !== undefined) $("cand-" + st.c).classList.add("hl");
      if (st.g !== undefined) $(`g-${st.c}-${st.g}`).classList.add("hl");
    };
    tick();
    S.playTimer = setInterval(tick, 520);
  }

  /* ================================================================
     PART 2 — LENSES
     ================================================================ */
  const CLASSES = ["Readiness", "Freshness", "Termination", "Failure handling"];
  const KIND_TEXT = {
    INVARSPEC: "Invariant: must hold in every reachable state.",
    LTLSPEC: "LTL: must hold along every infinite path.",
    CTLSPEC: "CTL: a branching-time property over the computation tree.",
  };

  function propGrid(container, failing, selected, onClick) {
    container.innerHTML = CLASSES.map((cl) => {
      const ps = D.properties.filter((p) => p.cls === cl);
      return `<div class="prop-col"><h4>${cl}</h4>` + ps.map((p) => {
        const fail = failing.includes(p.name);
        return `<button type="button" class="prop ${fail ? "fail" : ""} ${selected === p.name ? "sel" : ""}" data-p="${p.name}" title="${esc(p.comment)}">
          <span class="dot"></span><span class="pn">${esc(p.name.split("_")[0])}</span><span>${esc(p.name.split("_").slice(1).join(" "))}</span></button>`;
      }).join("") + `</div>`;
    }).join("");
    container.querySelectorAll(".prop").forEach((b) => b.addEventListener("click", () => onClick(b.dataset.p)));
  }

  function renderLogicalLens(sel) {
    sel = sel || D.properties[0].name;
    $("propCount").textContent = D.properties.length;
    propGrid($("lensProps"), [], sel, renderLogicalLens);
    const p = D.properties.find((x) => x.name === sel);
    $("lensPropDetail").innerHTML = `<h3 class="mono" style="font-size:1rem">${esc(p.name)}</h3>
      <p class="small">${esc(p.comment)}</p>
      <p><code>${esc(p.formula)}</code></p>
      <p class="small muted">${KIND_TEXT[p.kind] || p.kind} Contract ${esc(p.contract)}.</p>
      <p class="small">Result: ${badge("holds", "good")}<br>Non-vacuity: witness ${p.witnesses.map((w) => `<code>${esc(w)}</code>`).join(", ")} is reachable;
      probe <code>${esc(p.probe)}</code> is reachable.</p>`;
    const nv = D.nonvacuity;
    $("nvSummary").textContent = `${nv.as_expected}/${nv.queries} such queries came out as expected.`;
    const killed = D.mutants.filter((m) => m.killed).length;
    $("mutSummary").textContent = `${killed}/${D.mutants.length} were detected by at least one property.`;
  }

  function renderNumeric() {
    const u = updates[S.iter - 1];
    if (S.cand === null || S.cand > 2) S.cand = u.choice;
    $("numIter").textContent = `${S.iter} of run ${D.run.run_id}`;
    $("numCandPick").innerHTML = u.candidates.map((c, i) =>
      `<button type="button" data-c="${i}" ${i === S.cand ? 'class="primary"' : ""}>${CAND_NAMES[i]}${i === u.choice ? " (selected)" : ""}</button>`).join("");
    $("numCandPick").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { S.cand = +b.dataset.c; renderNumeric(); }));
    const c = u.candidates[S.cand];
    const ok = (good) => (good ? `<span style="color:var(--good)">✓</span>` : `<span style="color:var(--bad)">✗</span>`);
    let n1 = TERMS.map((t) => {
      const fr = expectationFraction(c, t);
      const signs = fr.counts.map((n, k) => (sign(t, k) > 0 ? "+" : "−") + n).join(" ").replace(/^\+/, "");
      return `<tr><td class="mono">${t}</td><td class="mono small">(${signs}) / ${fr.den}</td><td class="num">${fr.num}/${fr.den}</td><td class="num">${f(c.expectations[t], 6)}</td><td>${ok(fr.num / fr.den === c.expectations[t])}</td></tr>`;
    }).join("");
    const coefs = cfg.hamiltonian.terms;
    const sumNum = TERMS.reduce((a, t) => a + coefs[t] * expectationFraction(c, t).num, 0);
    const exactE = sumNum / (SCALE * SHOTS);
    const contribOk = TERMS.every((t) => Math.abs(coefs[t] * c.expectations[t] / SCALE - c.contributions[t]) < 1e-12);
    const cands = [u.index.slice(), u.index.slice(), u.index.slice()];
    cands[1][u.coordinate] = (u.index[u.coordinate] - 1 + cfg.grid_size) % cfg.grid_size;
    cands[2][u.coordinate] = (u.index[u.coordinate] + 1) % cfg.grid_size;
    const genOk = cands.every((z, i) => z.join() === u.candidates[i].index.join());
    let best = 0;
    u.candidates.forEach((x, i) => { if (x.score < u.candidates[best].score) best = i; });
    $("numWork").innerHTML = `
      <h4 style="margin-top:12px">N1 · counts → expectations</h4>
      <div class="scroll-x"><table><thead><tr><th>term</th><th>signed counts</th><th class="num">exact</th><th class="num">recorded</th><th></th></tr></thead><tbody>${n1}</tbody></table></div>
      <p class="small muted">ZI reads only q₁; ZZ, YZ and XX read the parity of both bits after the basis change.</p>
      <h4>N2 · expectations → energy</h4>
      <p class="small">Σ c<sub>P</sub>·⟨P⟩ with the declared integer coefficients (${TERMS.map((t) => t + " " + coefs[t]).join(", ")}, scaled by 10⁴):
        exact ${sumNum}/${fi(SCALE * SHOTS)} = <b class="mono">${f(exactE, 10)}</b>; recorded <b class="mono">${f(c.energy, 10)}</b> ${ok(Math.abs(exactE - c.energy) < 1e-12)}.
        Contributions match ${ok(contribOk)}. Integer selection score ${fi(c.score)} = energy × 10⁴ × ${fi(SHOTS)} ${ok(Math.round(exactE * SCALE * SHOTS) === c.score)}.</p>
      <h4>N3 · shot accounting</h4>
      <p class="small">${GROUPS.length} groups × ${fi(SHOTS)} = ${fi(GROUPS.length * SHOTS)} shots for this candidate; ${fi(SHOTS_PER_ITER)} for the iteration;
        cumulative after iteration ${S.iter}: ${fi(S.iter * SHOTS_PER_ITER)} vs recorded ${fi(u.shots)} ${ok(S.iter * SHOTS_PER_ITER === u.shots)}.</p>
      <h4>N4 · candidates and selection</h4>
      <p class="small">From z = (${u.index.join(", ")}), coordinate ${u.coordinate} gives ${cands.map((z, i) => CAND_NAMES[i] + " " + idxHtml(z, u.coordinate)).join(", ")} ${ok(genOk)}.
        Smallest score, ties to current then −1 then +1: <b>${CAND_NAMES[best]}</b>; optimizer chose <b>${CAND_NAMES[u.choice]}</b> ${ok(best === u.choice)}.</p>`;
    const rows = ["N1", "N2", "N3", "N4"].map((k) => {
      const c2 = D.contracts[k], a = D.agreement.find((x) => x.contract === k);
      return `<div style="border-top:1px solid var(--line);padding:10px 0">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><b>${k}</b> ${vbadge(c2.verdict)} ${badge("runtime " + a.runtime_counts.AGREEMENT + "/" + D.totals.runs, "good")}</div>
        <div class="small">${esc(c2.description)}</div>
        <div class="small muted"><b>Before:</b> ${esc(c2.stage1)}</div>
        <div class="small muted"><b>During:</b> ${esc(c2.stage2)}</div></div>`;
    }).join("");
    $("numContracts").innerHTML = `<h3>Numeric contracts</h3>${rows}
      <p class="small muted">Largest energy reconstruction error over all baseline runs: ${D.totals.max_energy_error.toExponential(2)}. Dafny's proofs assume mathematical arithmetic and the stated preconditions; bit order and parity mapping are part of the trusted base.</p>`;
  }

  function renderProbabilistic() {
    const P = D.probabilistic;
    const model = P.model_cdf.map((v, k) => [k, v]);
    const emp = P.empirical_cdf.map((v, k) => [k, v]);
    $("cdfRuns").textContent = D.totals.runs;
    $("cdfChart").innerHTML = chart({
      label: "Probability of first success within k iterations: model vs empirical",
      x: [0, cfg.maximum_updates], y: [0, 1], xticks: [0, 10, 20, 30, 40, 50], yticks: [0, 0.25, 0.5, 0.75, 1],
      yfmt: (t) => Math.round(t * 100) + "%", xlabel: "iteration bound k", ylabel: "P(success by k)",
      series: [{ pts: model, color: "var(--series-a)", step: true, width: 2.4 }, { pts: emp, color: "var(--series-b)", step: true, dash: "5 3" }],
      over: [(X, Y) => P.checkpoints.map((c) => {
        const x = X(c.update_bound);
        return `<line x1="${x}" x2="${x}" y1="${Y(c.wilson_95[0])}" y2="${Y(c.wilson_95[1])}" style="stroke:var(--series-b);stroke-width:2"/>` +
          `<line x1="${x - 4}" x2="${x + 4}" y1="${Y(c.wilson_95[0])}" y2="${Y(c.wilson_95[0])}" style="stroke:var(--series-b)"/>` +
          `<line x1="${x - 4}" x2="${x + 4}" y1="${Y(c.wilson_95[1])}" y2="${Y(c.wilson_95[1])}" style="stroke:var(--series-b)"/>` +
          `<circle cx="${x}" cy="${Y(c.model_probability)}" r="3.5" style="fill:var(--series-a)"/>`;
      }).join("")],
      hover: model.map(([k, v]) => ({ x: k, text: `k = ${k}\nmodel ${pct(v)}\nempirical ${pct(P.empirical_cdf[k])}` })),
    });
    $("dtmcNote").innerHTML = `Storm checks bounded reachability on a Gaussian DTMC with ${fi(P.dtmc_states)} states and ${fi(P.transitions)} transitions.
      Each transition is one optimizer iteration; the Gaussian approximation of the finite-shot energy estimate is motivated by the central limit theorem and has no certified finite-shot error bound.`;
    $("cpTable").innerHTML = `<thead><tr><th>k</th><th class="num">model</th><th class="num">observed</th><th class="num">Wilson 95%</th><th></th></tr></thead><tbody>` +
      P.checkpoints.map((c) => `<tr><td>${c.update_bound}${c.primary ? " <span class='small muted'>(primary)</span>" : ""}</td><td class="num">${pct(c.model_probability)}</td>
        <td class="num" title="${c.runtime_successes}/${c.runtime_runs} runs">${pct(c.runtime_probability)}</td><td class="num">${pct(c.wilson_95[0])}–${pct(c.wilson_95[1])}</td><td>${vbadge(c.verdict_agreement)}</td></tr>`).join("") +
      `</tbody>`;
    const [p2, p3] = P.conditional_means;
    $("condCard").innerHTML = `<h3>Conditional resources (P2, P3)</h3>
      <p class="small">Among the ${p2.successful_runs} successful runs:</p>
      <table><thead><tr><th></th><th class="num">model</th><th class="num">observed</th><th class="num">bootstrap 95%</th></tr></thead><tbody>
      <tr><td>P2 iterations</td><td class="num">${p2.model_mean.toFixed(2)}</td><td class="num">${p2.runtime_mean.toFixed(2)}</td><td class="num">${p2.bootstrap_95[0].toFixed(2)}–${p2.bootstrap_95[1].toFixed(2)}</td></tr>
      <tr><td>P3 shots</td><td class="num">${fi(Math.round(p3.model_mean))}</td><td class="num">${fi(Math.round(p3.runtime_mean))}</td><td class="num">${fi(Math.round(p3.bootstrap_95[0]))}–${fi(Math.round(p3.bootstrap_95[1]))}</td></tr>
      </tbody></table>
      <p class="small" style="margin-top:10px">${badge("statistically compatible", "good")} The bootstrap interval for P2 does not contain the model mean (raw p = 0.024).
        Tested jointly with the informative P1 checkpoints under Holm adjustment at α = 0.05, the adjusted p-value is 0.094, so every informative comparison is compatible at the family level.
        P3 is P2 times the fixed ${fi(SHOTS_PER_ITER)} shots per iteration.</p>
      <details><summary>Original automated labels</summary>
        <p class="small">The automated report applied a marginal interval-containment rule and labelled P2 ${vbadge(p2.verdict_agreement)} and P3 ${vbadge(p3.verdict_agreement)}.
        The paper keeps these labels for provenance; the family-level reading is a post-audit reporting correction. Compatibility holds at this sample size and is not a claim of distributional equivalence; no equivalence margin was preregistered.</p>
      </details>`;
  }

  // Runtime lens
  const EVENT_CHECKS = {
    run_start: [],
    update_start: [],
    measurement: [["N3", "allocation_checked"], ["L3", "evaluation_identity_current"]],
    evaluation: [["L1", "groups_before_energy"], ["N1", "expectation_reconstructed", 4], ["N2", "energy_reconstructed"], ["L3", "evaluation_identity_current"]],
    numeric_valid: [["L2", "validation_certified"], ["L3", "evaluation_identity_current"]],
    optimizer_commit: [["L2", "validations_before_commit"], ["L3", "commit_identity_current"], ["N3", "cumulative_total_checked"], ["N4", "candidates_generated"], ["N4", "selection_checked"]],
    terminal: [["L4", "terminal_reason"], ["N3", "cumulative_total_checked"]],
  };
  const RT = { pos: 0, timer: null, counts: {} };
  function rtDescribe(e) {
    const [kind, u, c, g] = e;
    if (kind === "run_start") return `run ${D.run.run_id} starts at z = (${D.run.start_index.join(", ")})`;
    if (kind === "update_start") return `iteration ${u} begins`;
    if (kind === "measurement") return `iter ${u} · ${CAND_NAMES[c]} · group {${GROUPS[g].join(",")}} → ${fi(SHOTS)} counts`;
    if (kind === "evaluation") return `iter ${u} · ${CAND_NAMES[c]} · energy ${f(updates[u - 1].candidates[c].energy, 4)}`;
    if (kind === "numeric_valid") return `iter ${u} · ${CAND_NAMES[c]} · validated`;
    if (kind === "optimizer_commit") return `iter ${u} · commit ${CAND_NAMES[updates[u - 1].choice]}`;
    if (kind === "terminal") return `stop: ${D.run.terminal.reason} after ${D.run.terminal.updates} iterations`;
    return "";
  }
  function rtRenderCounters() {
    const keys = [];
    Object.values(EVENT_CHECKS).forEach((list) => list.forEach(([k, n]) => { if (!keys.some((x) => x[1] === n)) keys.push([k, n]); }));
    keys.sort((a, b) => (a[0] + a[1]).localeCompare(b[0] + b[1]));
    $("rtCounters").innerHTML = `<table><tbody>` + keys.map(([k, n]) =>
      `<tr><td><b>${k}</b></td><td class="mono small">${n}</td><td class="num">${fi(RT.counts[n] || 0)}</td><td>${(RT.counts[n] || 0) ? '<span style="color:var(--good)">✓ all pass</span>' : ""}</td></tr>`).join("") + `</tbody></table>`;
  }
  function rtAdvance(n) {
    const sk = D.run.skeleton;
    const stream = $("rtStream");
    let html = "";
    for (let i = 0; i < n && RT.pos < sk.length; i++) {
      const e = sk[RT.pos];
      const checks = EVENT_CHECKS[e[0]] || [];
      checks.forEach(([, name, times]) => { RT.counts[name] = (RT.counts[name] || 0) + (times || 1); });
      html += `<div class="ev" data-i="${RT.pos}"><span class="muted">${RT.pos + 1}</span><span>${e[0]}</span><span>${esc(rtDescribe(e))}${checks.length ? ` <span class="chk">✓ ${[...new Set(checks.map((x) => x[0]))].join(" ")}</span>` : ""}</span></div>`;
      RT.pos++;
    }
    if (html) {
      stream.querySelectorAll(".ev.cur").forEach((x) => x.classList.remove("cur"));
      stream.insertAdjacentHTML("beforeend", html);
      const last = stream.lastElementChild;
      last.classList.add("cur");
      stream.scrollTop = stream.scrollHeight;
    }
    rtRenderCounters();
    if (RT.pos >= sk.length) rtStop();
  }
  function rtStop() { clearInterval(RT.timer); RT.timer = null; $("rtPlay").textContent = "▶ Play"; }
  function rtReset() { rtStop(); RT.pos = 0; RT.counts = {}; $("rtStream").innerHTML = ""; rtAdvance(1); }
  function renderRuntime() {
    $("rtRun").textContent = D.run.run_id;
    $("rtCount").textContent = fi(D.run.skeleton.length);
    $("rtRuns").textContent = D.totals.runs;
    $("rtStep").onclick = () => rtAdvance(1);
    $("rtJump").onclick = () => { rtStop(); rtAdvance(1e6); };
    $("rtReset").onclick = rtReset;
    $("rtPlay").onclick = () => {
      if (RT.timer) { rtStop(); return; }
      if (RT.pos >= D.run.skeleton.length) rtReset();
      $("rtPlay").textContent = "■ Pause";
      RT.timer = setInterval(() => rtAdvance(1), 140);
    };
    rtReset();
    $("rtTotals").innerHTML = `<table><thead><tr><th>contract</th><th class="num">checks</th><th>runs</th></tr></thead><tbody>` +
      D.agreement.map((a) => `<tr><td><b>${a.contract}</b> <span class="small muted">${esc(a.description)}</span></td><td class="num">${fi(a.runtime_checks)}</td><td>${badge((a.runtime_counts.AGREEMENT || 0) + "/" + D.totals.runs, "good")}</td></tr>`).join("") +
      `</tbody></table><p class="small muted" style="margin-top:8px">DejaVu temporal replay accepted ${D.totals.dejavu_passed}/${D.totals.runs} runs; online and offline Python verdicts agree for every run: ${D.totals.online_replay_agreement ? "yes" : "no"}.
      Runtime checking covers the observed traces only.</p>`;
  }

  function setupLensTabs() {
    const tabs = [...document.querySelectorAll("#lensTabs button")];
    tabs.forEach((b) => b.addEventListener("click", () => {
      tabs.forEach((x) => x.setAttribute("aria-selected", x === b ? "true" : "false"));
      document.querySelectorAll(".lens").forEach((l) => { l.hidden = l.id !== "lens-" + b.dataset.lens; });
    }));
  }

  /* ================================================================
     PART 3 — TOGETHER
     ================================================================ */
  const FAULT_TEXT = {
    coefficient_swap: "Swap the YZ and XX coefficients",
    corrupt_energy: "Corrupt a reported energy",
    missing_evidence: "Delete counts from a saved trace",
    premature_update: "Commit before all validations",
    shot_mismatch: "Change the shot allocation",
  };
  const SYM = { AGREEMENT: ["✓", "good"], DISAGREEMENT: ["✗", "bad"], ASSUMPTION_MISMATCH: ["≠", "warn"], INCONCLUSIVE: ["?", "grey"] };

  function renderPipeline() {
    const t = D.totals;
    const box = (x, y, w, h, title, lines, cls) =>
      `<g class="node ${cls || ""}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="9"/>` +
      `<text x="${x + 12}" y="${y + 20}" style="font-size:12.5px">${esc(title)}</text>` +
      lines.map((l, i) => `<text class="sub" x="${x + 12}" y="${y + 38 + i * 14}" style="font-size:10.5px">${esc(l)}</text>`).join("") + `</g>`;
    const arrow = (d, label, lx, ly) => `<g class="edge"><path d="${d}" marker-end="url(#pl-a)"/>${label ? `<text x="${lx}" y="${ly}" text-anchor="middle">${esc(label)}</text>` : ""}</g>`;
    let s = `<svg class="dg" viewBox="0 0 960 250" role="img" aria-label="Two-stage verification pipeline"><defs><marker id="pl-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" style="fill:var(--faint)"/></marker></defs>`;
    s += `<text x="10" y="16" class="lbl" style="font-weight:600;letter-spacing:.08em">STAGE 1 · BEFORE EXECUTION</text>`;
    s += box(10, 26, 220, 58, "nuXmv · L1–L4", [`${D.properties.length} properties hold`, `${D.nonvacuity.queries} non-vacuity queries, ${D.mutants.length} mutants`]);
    s += box(10, 94, 220, 58, "Dafny · N1–N4", ["arithmetic kernels proved", "normalize, aggregate, wrap, argmin"]);
    s += box(10, 162, 220, 58, "Storm · P1–P3", [`Gaussian DTMC, ${fi(D.probabilistic.dtmc_states)} states`, "bounded reachability at 5 checkpoints"]);
    s += arrow("M232,55 L276,110", "", 0, 0) + arrow("M232,123 L276,123", "", 0, 0) + arrow("M232,191 L276,136", "", 0, 0);
    s += box(280, 82, 170, 82, "Freeze + hash", ["Stage 1 results and config", "sha256 " + t.stage1_digest.slice(0, 12) + "…", "gate: all established"]);
    s += arrow("M452,123 L496,123", "run", 474, 115);
    s += `<text x="500" y="16" class="lbl" style="font-weight:600;letter-spacing:.08em">STAGE 2 · DURING AND AFTER EXECUTION</text>`;
    s += box(500, 60, 200, 126, `${t.runs} baseline runs`, [`${fi(t.shots)} physical shots`, "online Python monitor per event", "DejaVu replay of each trace", `${t.successes} successes, ${t.runs - t.successes} at budget`, "+ 50 fault-injection runs"]);
    s += arrow("M702,123 L746,123", "compare", 724, 115);
    s += box(750, 60, 200, 126, "Cross-stage verdict", ["per contract:", "AGREEMENT", "DISAGREEMENT", "ASSUMPTION_MISMATCH", "INCONCLUSIVE"]);
    s += `</svg>`;
    $("pipeline").innerHTML = s;
  }

  function renderTogether() {
    const t = D.totals;
    const evals = D.agreement.find((a) => a.contract === "L2").runtime_triggers.validation_certified;
    const meas = D.agreement.find((a) => a.contract === "N3").runtime_triggers.allocation_checked;
    const iters = D.agreement.find((a) => a.contract === "N4").runtime_triggers.selection_checked;
    const stat = (v, l) => `<div class="card stat"><span class="v">${v}</span><span class="l">${l}</span></div>`;
    $("totals").innerHTML = stat(t.runs, "baseline runs, one seeded stream each") + stat(`${t.successes}`, `succeeded within ${cfg.maximum_updates} iterations (${pct(t.successes / t.runs)})`) +
      stat(fi(t.shots), "physical shots in total") + stat(fi(evals), `candidate evaluations, ${fi(meas)} group executions, ${fi(iters)} iterations`);

    const rows = D.agreement.map((a) => `<tr><td><b>${a.contract}</b></td><td>${esc(a.description)}</td><td>${vbadge(a.stage1)}</td>
      <td class="small">${fi(a.runtime_checks)} checks · ${a.runtime_counts.AGREEMENT || 0}/${t.runs} runs pass</td><td>${vbadge(a.verdict_agreement)}</td></tr>`);
    const P = D.probabilistic, prim = P.checkpoints.find((c) => c.primary), [p2, p3] = P.conditional_means;
    rows.push(`<tr><td><b>P1</b></td><td>${esc(D.contracts.P1.description)}</td><td>${vbadge(D.contracts.P1.verdict)}</td>
      <td class="small">k = ${prim.update_bound}: ${prim.runtime_successes}/${prim.runtime_runs} = ${pct(prim.runtime_probability)} (Wilson ${pct(prim.wilson_95[0])}–${pct(prim.wilson_95[1])}) vs model ${pct(prim.model_probability)}</td>
      <td>${vbadge(prim.verdict_agreement)} <div class="small muted">statistically compatible</div></td></tr>`);
    rows.push(`<tr><td><b>P2</b></td><td>${esc(D.contracts.P2.description)}</td><td>${vbadge(D.contracts.P2.verdict)}</td>
      <td class="small">${p2.runtime_mean.toFixed(2)} vs model ${p2.model_mean.toFixed(2)} iterations; Holm-adjusted p = 0.094</td>
      <td>${vbadge("AGREEMENT")} <div class="small muted">statistically compatible · <a href="#lenses" data-goto="probabilistic">raw label</a></div></td></tr>`);
    rows.push(`<tr><td><b>P3</b></td><td>${esc(D.contracts.P3.description)}</td><td>${vbadge(D.contracts.P3.verdict)}</td>
      <td class="small">${fi(Math.round(p3.runtime_mean))} vs model ${fi(Math.round(p3.model_mean))} shots; derived from P2</td>
      <td>${vbadge("AGREEMENT")} <div class="small muted">follows P2</div></td></tr>`);
    $("verdictTable").innerHTML = `<thead><tr><th>ID</th><th>requirement</th><th>Stage 1</th><th>Stage 2 evidence</th><th>verdict</th></tr></thead><tbody>${rows.join("")}</tbody>`;
    $("verdictTable").querySelectorAll("[data-goto]").forEach((a) => a.addEventListener("click", () => {
      document.querySelector(`#lensTabs [data-lens="${a.dataset.goto}"]`).click();
    }));

    const F = (k) => D.faults.find((x) => x.fault === k);
    const l1 = D.agreement.find((a) => a.contract === "L1");
    const card = (v, title, body) => `<div class="card"><div style="margin-bottom:6px">${vbadge(v)}</div><h3>${title}</h3><div class="small">${body}</div></div>`;
    $("verdictWords").innerHTML =
      card("AGREEMENT", "The requirement held where it was checked",
        `<p>L1 in the baseline: nuXmv proved that aggregation needs all groups, and in all ${t.runs} runs each of the ${fi(l1.runtime_triggers.groups_before_energy)}
        aggregations was preceded by its three group records.</p><p class="muted">Agreement is scoped: it holds for the mapped requirement, on observed traces.</p>`) +
      card("DISAGREEMENT", "An observed run violated a proved requirement",
        `<p><b>Coefficient swap</b>: N2 disagrees in ${F("coefficient_swap").detected}/${F("coefficient_swap").runs} runs, while DejaVu accepts ${F("coefficient_swap").dejavu_passed}/${F("coefficient_swap").runs}: the order is fine, the arithmetic is not.</p>
        <p><b>Premature commit</b>: L2 disagrees and DejaVu rejects ${F("premature_update").runs - F("premature_update").dejavu_passed}/${F("premature_update").runs}: an ordering fault that temporal checking catches.</p>`) +
      card("ASSUMPTION_MISMATCH", "The run left the conditions a result assumes",
        `<p><b>Changed shot allocation</b>: N3 reports a mismatch in ${F("shot_mismatch").detected}/${F("shot_mismatch").runs} runs. The Gaussian model's variance and the numeric allocation premise no longer apply, so the probabilistic comparison is inapplicable until the assumption is restored or the model revised.</p>
        <p class="muted">Caveat: the injector configures this applicability label; it records which stochastic assumptions the fault changes.</p>`) +
      card("INCONCLUSIVE", "The records are not enough to decide",
        `<p><b>Deleted counts</b>: N1 cannot reconstruct expectations, so it is inconclusive in ${F("missing_evidence").detected}/${F("missing_evidence").runs} runs, as are N2–N4.</p>
        <p class="muted">Caveat: the checker also reports L1 ${vbadge("DISAGREEMENT")}, because its completeness check treats an unavailable record as a missing measurement. A deleted record alone does not show that the run aggregated too early. The paper reports this as a classification limitation.</p>`);

    const cols = ["L1", "L2", "L3", "L4", "N1", "N2", "N3", "N4"];
    $("faultMatrix").innerHTML = `<thead><tr><th>fault</th>${cols.map((c) => `<th>${c}</th>`).join("")}<th>expected</th><th>detected</th><th>DejaVu accepts</th></tr></thead><tbody>` +
      D.faults.map((x) => `<tr><td>${esc(FAULT_TEXT[x.fault] || x.fault)}<div class="small muted mono">${x.fault}</div></td>` +
        cols.map((c) => {
          const [sym, kind] = SYM[x.vector[c]];
          const target = c === x.expected_contract;
          return `<td title="${c}: ${x.vector[c]}"><span class="badge b-${kind} sym" style="${target ? "box-shadow:0 0 0 2px currentColor" : ""}">${sym}</span></td>`;
        }).join("") +
        `<td class="small">${x.expected_contract} ${vbadge(x.expected_verdict)}</td><td class="num">${x.detected}/${x.runs}</td><td class="num">${x.dejavu_passed}/${x.runs}</td></tr>`).join("") + `</tbody>`;
    $("faultLegend").innerHTML = Object.entries(SYM).map(([v, [s, k]]) => `<span><span class="badge b-${k}">${s}</span> ${v.replace(/_/g, " ")}</span>`).join("") +
      `<span>Ringed cell: the expected target. All faults are injected at the first iteration/candidate boundary.</span>`;

    $("caveats").innerHTML = [
      "Each tool is exhaustive only for what it encodes: nuXmv for the abstract controller, Dafny for the kernels under mathematical semantics and preconditions, Storm for the constructed Gaussian DTMC. Runtime checks cover the observed traces. A formal refinement from every model to the Python program is future work.",
      "The Gaussian approximation is motivated by the central limit theorem; no certified finite-shot approximation-error bound is supplied.",
      "Probabilistic agreement means statistical compatibility at this sample size, not equivalence: no equivalence margin was preregistered, checkpoint intervals are pointwise and correlated, and the primary comparison can detect deviations of about 3.6 percentage points at 80% power.",
      "The P2/P3 reading (Holm-adjusted, family level) is a post-audit reporting correction. The original marginal labels remain in the record.",
      "The benchmark is small: two qubits, a fixed 16-point grid, ideal finite-shot statistics and an exact-energy stopping oracle that exists only in simulation.",
      "Development executions used the same seeds, so this is an engineering evaluation, not a blinded confirmatory study.",
      "Circuit and basis generation, bit order and parity interpretation, event instrumentation and the tools themselves are trusted. Hashes tie files to the experiment; they do not authenticate the physical origin of counts.",
      "The fault suite covers five classes at one injection boundary. Terminal-boundary faults, stale inputs and other sites need further tests.",
    ].map((x) => `<li>${esc(x)}</li>`).join("");
  }

  /* ================================================================
     LOGICAL EXPLORER
     ================================================================ */
  const MUT_INFO = {
    M1_early_aggregation: { kind: "guard", title: "Aggregate after one group", desc: "The measure loop exits after the first group instead of all three." },
    M2_skipped_candidate: { kind: "guard", title: "Commit after one candidate", desc: "The optimizer steps after validating one candidate instead of three." },
    M11_success_as_abort: { kind: "guard", title: "Accept success only at the budget", desc: "Convergence leads to DONE only at the last iteration; earlier success falls through to ABORT." },
    M9_measurement_error_ignored: { kind: "guard", title: "Ignore measurement failures", desc: "measure_fails is removed from the error signal, so a failed measurement does not abort." },
    M5_skipped_rebind: { kind: "rewire", title: "Measure without rebinding", desc: "After one candidate, go straight to measurement without binding the next candidate's parameters." },
    M10_budget_as_abort: { kind: "rewire", title: "Budget exhaustion aborts", desc: "When the budget is spent, go to ABORT instead of DONE." },
    M12_budget_overrun: { kind: "rewire", title: "Keep going past the budget", desc: "When the budget is spent, start another iteration instead of stopping." },
    M3_no_candidate_reset: { kind: "reset", title: "Never reset the candidate counter", desc: "cands_done keeps its value when a new iteration starts.", node: "CHECK_STOP" },
    M4_stale_energy_ready: { kind: "reset", title: "Keep the old ‘energy ready’ flag", desc: "energy_ready is not cleared when a new iteration starts.", node: "CHECK_STOP" },
    M6_stale_binding: { kind: "reset", title: "Stamp the binding only in iteration 0", desc: "bound_version is updated only when iter = 0, so later bindings carry a stale iteration.", node: "BIND" },
    M7_wrong_candidate: { kind: "reset", title: "Bind every evaluation as candidate 0", desc: "bound_cand is always set to 0, whichever candidate is prepared.", node: "BIND" },
    M8_stale_energy_epoch: { kind: "reset", title: "Stamp the energy only in iteration 0", desc: "energy_version is updated only when iter = 0, so later energies carry a stale iteration.", node: "COMPUTE_ENERGY" },
  };
  const MUT_GROUPS = [
    ["rewire", "Rewire an arrow", ["M5_skipped_rebind", "M10_budget_as_abort", "M12_budget_overrun"]],
    ["guard", "Change or remove a guard", ["M1_early_aggregation", "M2_skipped_candidate", "M11_success_as_abort", "M9_measurement_error_ignored"]],
    ["reset", "Drop a reset or version stamp", ["M3_no_candidate_reset", "M4_stale_energy_ready", "M6_stale_binding", "M7_wrong_candidate", "M8_stale_energy_epoch"]],
  ];

  // Base controller geometry (nuXmv states)
  const CTRL_NODES = [
    { id: "S_INIT", x: 80, y: 50 }, { id: "CHECK_STOP", x: 250, y: 50 }, { id: "BIND", x: 440, y: 50 },
    { id: "EXECUTE_MEASURE", x: 640, y: 50, w: 160 }, { id: "COMPUTE_ENERGY", x: 640, y: 210, w: 160 },
    { id: "OPTIMIZER_STEP", x: 440, y: 210, w: 140 }, { id: "DONE", x: 250, y: 210 }, { id: "ABORT", x: 80, y: 210 },
  ];
  const CTRL_EDGES = [
    { id: "e0", from: "S_INIT", to: "CHECK_STOP", d: "M140,50 L188,50" },
    { id: "e1", from: "CHECK_STOP", to: "DONE", d: "M235,70 L235,188", label: "converged", lx: 228, ly: 115, anchor: "end" },
    { id: "e2", from: "CHECK_STOP", to: "DONE", d: "M265,70 L265,188", label: "budget spent", lx: 272, ly: 172, anchor: "start" },
    { id: "e3", from: "CHECK_STOP", to: "BIND", d: "M310,50 L378,50", label: "continue", lx: 344, ly: 42 },
    { id: "e4", from: "BIND", to: "EXECUTE_MEASURE", d: "M500,50 L558,50" },
    { id: "e5", from: "EXECUTE_MEASURE", to: "EXECUTE_MEASURE", d: "M612,30 C600,-14 680,-14 668,30", label: "next group", lx: 640, ly: -18 },
    { id: "e6", from: "EXECUTE_MEASURE", to: "COMPUTE_ENERGY", d: "M625,70 L625,188", label: "all groups", lx: 618, ly: 125, anchor: "end" },
    { id: "e7", from: "COMPUTE_ENERGY", to: "BIND", d: "M572,190 C530,150 480,110 452,72", label: "next candidate", lx: 488, ly: 148, anchor: "end" },
    { id: "e8", from: "COMPUTE_ENERGY", to: "OPTIMIZER_STEP", d: "M560,210 L512,210", label: "all candidates", lx: 536, ly: 248 },
    { id: "e9", from: "OPTIMIZER_STEP", to: "CHECK_STOP", d: "M392,190 L300,72" },
    { id: "eD", from: "DONE", to: "DONE", d: "M238,230 C226,270 274,270 262,230" },
    { id: "eA", from: "ABORT", to: "ABORT", d: "M68,230 C56,270 104,270 92,230" },
    { id: "eErr", from: "*", to: "ABORT", d: "M150,284 L100,232", label: "error (any state)", lx: 156, ly: 290, anchor: "start" },
  ];
  const MUT_EDGES = {
    M1_early_aggregation: { cut: ["e5"], changed: { e6: "after 1 group" } },
    M2_skipped_candidate: { cut: ["e7"], changed: { e8: "after 1 candidate" } },
    M5_skipped_rebind: { cut: ["e7"], add: [{ id: "n1", from: "COMPUTE_ENERGY", to: "EXECUTE_MEASURE", d: "M675,188 L675,72", label: "next candidate", lx: 682, ly: 125, anchor: "start" }] },
    M10_budget_as_abort: { cut: ["e2"], add: [{ id: "n1", from: "CHECK_STOP", to: "ABORT", d: "M200,70 L122,188", label: "budget spent", lx: 150, ly: 112, anchor: "end" }] },
    M11_success_as_abort: { changed: { e1: "converged & iter = MAX" }, add: [{ id: "n1", from: "CHECK_STOP", to: "ABORT", d: "M200,70 L122,188", label: "converged early", lx: 150, ly: 112, anchor: "end" }] },
    M12_budget_overrun: { cut: ["e2"], add: [{ id: "n1", from: "CHECK_STOP", to: "BIND", d: "M300,32 C320,0 370,0 392,32", label: "budget spent", lx: 346, ly: 2 }] },
    M9_measurement_error_ignored: { changed: { eErr: "error, but not measure_fails" } },
  };

  const EX = { mut: null, prop: null, step: 0, timer: null };

  function ctrlSpec(mutName) {
    const me = MUT_EDGES[mutName] || {};
    const info = MUT_INFO[mutName] || {};
    const edges = CTRL_EDGES.map((e) => {
      const x = Object.assign({}, e);
      if ((me.cut || []).includes(e.id)) x.cls = "cut";
      if (me.changed && me.changed[e.id]) { x.cls = "changed"; x.label = me.changed[e.id]; }
      return x;
    }).concat((me.add || []).map((e) => Object.assign({ cls: "new" }, e)));
    const nodes = CTRL_NODES.map((n) => Object.assign({}, n, { text: n.id, w: n.w || 120, flag: info.node === n.id }));
    return { viewBox: "0 -30 800 330", label: "nuXmv controller state machine", nodes, edges };
  }

  function renderMutPicker() {
    let s = `<h3>Choose a change</h3>
      <button type="button" class="mut" data-m="" aria-pressed="${EX.mut === null}"><div class="mt">Original controller</div><div class="md">No change. All 24 properties hold.</div></button>`;
    MUT_GROUPS.forEach(([, title, list]) => {
      s += `<div class="mut-group"><h4>${title}</h4>` + list.map((name) => {
        const i = MUT_INFO[name], m = D.mutants.find((x) => x.name === name);
        return `<button type="button" class="mut" data-m="${name}" aria-pressed="${EX.mut === name}"><div class="mt">${esc(i.title)}</div>
          <div class="md">${esc(i.desc)}</div><div class="md mono">${name.split("_")[0]} · targets ${m.target} · breaks ${m.failing.length}</div></button>`;
      }).join("") + `</div>`;
    });
    $("mutPicker").innerHTML = s;
    $("mutPicker").querySelectorAll(".mut").forEach((b) => b.addEventListener("click", () => selectMutant(b.dataset.m || null)));
  }

  function selectMutant(name) {
    exStop();
    EX.mut = name;
    const m = name && D.mutants.find((x) => x.name === name);
    EX.prop = m ? m.failing[0] : null;
    EX.step = 0;
    renderMutPicker();
    renderExplorer();
  }

  function renderExplorer() {
    const m = EX.mut && D.mutants.find((x) => x.name === EX.mut);
    const d = diagram(ctrlSpec(EX.mut));
    $("ctrlDiagram").innerHTML = d.svg;
    if (m) {
      $("mutEdit").innerHTML = `<h4 style="margin-top:8px">The edit to the nuXmv model</h4>` + m.edits.map(([a, b]) =>
        `<div class="mono small" style="white-space:pre-wrap;margin-bottom:6px"><div style="color:var(--good)">− ${esc(a)}</div><div style="color:var(--bad)">+ ${esc(b)}</div></div>`).join("") +
        `<p class="small muted">Red marks the change on the diagram. Struck-out dashed arrows can no longer fire.</p>`;
    } else {
      $("mutEdit").innerHTML = `<p class="small muted" style="margin-top:8px">Guards are evaluated top to bottom; the first match wins, so an error always takes priority and goes to ABORT. DONE and ABORT are absorbing.
        <span class="mono">NTERMS = NCANDS = 3</span>, <span class="mono">MAX_ITERS = ${cfg.maximum_updates}</span>.</p>`;
    }
    const failing = m ? m.failing : [];
    propGrid($("exProps"), failing, EX.prop, (p) => { exStop(); EX.prop = p; EX.step = 0; renderExplorer(); });
    $("mutTally").innerHTML = m
      ? `${badge(failing.length + " fail", "bad")} ${badge(D.properties.length - failing.length + " still hold", "good")} · detected by contract${m.detected_by.length > 1 ? "s" : ""} ${m.detected_by.join(", ")}`
      : badge(`${D.properties.length} hold`, "good");
    renderCx();
  }

  function cxData() {
    const m = EX.mut && D.mutants.find((x) => x.name === EX.mut);
    if (!m || !EX.prop || !m.counterexamples[EX.prop]) return null;
    return { m, cx: m.counterexamples[EX.prop], p: D.properties.find((x) => x.name === EX.prop) };
  }

  function renderCx() {
    const box = $("cxCard");
    const x = cxData();
    if (!x) {
      const p = EX.prop && D.properties.find((q) => q.name === EX.prop);
      box.innerHTML = EX.mut
        ? `<h3>${esc(EX.prop || "")}</h3><p class="small">${p ? esc(p.comment) : ""}</p><p><code>${p ? esc(p.formula) : ""}</code></p><p>${badge("still holds under this change", "good")}</p>`
        : `<h3>Counterexample replay</h3><p class="muted">Pick a change on the left. nuXmv's counterexample for each failing property will be replayed here and on the diagram.</p>`;
      return;
    }
    const { cx, p } = x;
    const steps = cx.steps;
    const loopIdx = cx.loop_at === null ? null : cx.loop_at - (cx.length - steps.length);
    const skipAt = steps.findIndex((q) => q.skip);
    // Columns: state, iter, and any tracked variable that changes within this trace.
    const keys = Object.keys(steps.find((s) => !s.skip)).filter((k) => k !== "state");
    const varying = keys.filter((k) => k === "iter" || new Set(steps.filter((s) => !s.skip).map((s) => s[k])).size > 1);
    const cols = ["state"].concat(varying);
    let prev = null;
    const body = steps.map((s, i) => {
      if (s.skip) { prev = null; return `<tr class="skip" data-i="${i}"><td colspan="${cols.length + 1}">… ${fi(s.steps)} steps omitted: iterations ${s.from_iter} → ${s.to_iter} repeat the same cycle …</td></tr>`; }
      const tds = cols.map((k) => `<td class="${prev && prev[k] !== s[k] ? "changed" : ""}">${esc(s[k])}</td>`).join("");
      prev = s;
      const mark = loopIdx === i ? "↻ " : "";
      const original = skipAt >= 0 && i > skipAt ? i + cx.length - steps.length : i;
      return `<tr data-i="${i}"><td class="muted">${mark}${original + 1}</td>${tds}</tr>`;
    }).join("");
    let how;
    if (p.kind === "INVARSPEC") how = "An invariant fails at a single reachable state: the last state shown violates it.";
    else if (loopIdx !== null) how = `An infinite path (a lasso): from step marked ↻ the trace ${loopIdx === steps.length - 1 ? "stays in its last state forever" : "repeats forever"}, and along it the property never becomes true.`;
    else how = "A path on which the property fails.";
    box.innerHTML = `<div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:baseline">
        <h3 style="margin:0">Counterexample: <span class="mono">${esc(p.name)}</span> under ${esc(x.m.name.split("_")[0])}</h3>
        <span class="small muted">${fi(cx.length)} states from nuXmv${cx.length !== steps.length ? ", middle condensed" : ""}</span></div>
      <p class="small" style="margin:6px 0">${esc(p.comment)} <code>${esc(p.formula)}</code></p>
      <p class="small muted">${esc(KIND_TEXT[p.kind] || "")} ${esc(how)}</p>
      <div class="controls">
        <button type="button" id="cxPrev" aria-label="Previous state">◀</button>
        <input type="range" id="cxSlider" min="0" max="${steps.length - 1}" value="${EX.step}" aria-label="Counterexample step">
        <button type="button" id="cxNext" aria-label="Next state">▶</button>
        <button type="button" class="primary" id="cxPlay">${EX.timer ? "■ Stop" : "▶ Replay on diagram"}</button>
        <span class="small mono" id="cxPos"></span>
      </div>
      <div class="scroll-x" style="max-height:340px;overflow-y:auto;border:1px solid var(--line);border-radius:8px">
        <table class="cx-table"><thead><tr><th>#</th>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>
      <p class="small muted" style="margin-top:8px">Highlighted cells changed from the previous state. Only variables that change in this trace are shown.</p>`;
    $("cxPrev").onclick = () => { exStop(); exGo(EX.step - 1); };
    $("cxNext").onclick = () => { exStop(); exGo(EX.step + 1); };
    $("cxSlider").oninput = (e) => { exStop(); exGo(+e.target.value); };
    $("cxPlay").onclick = () => {
      if (EX.timer) { exStop(); return; }
      if (EX.step >= steps.length - 1) EX.step = 0;
      $("cxPlay").textContent = "■ Stop";
      exGo(EX.step);
      EX.timer = setInterval(() => { if (EX.step >= steps.length - 1) exStop(); else exGo(EX.step + 1); }, 650);
    };
    box.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => { exStop(); exGo(+tr.dataset.i); }));
    exGo(EX.step);
  }

  function exStop() { clearInterval(EX.timer); EX.timer = null; const b = $("cxPlay"); if (b) b.textContent = "▶ Replay on diagram"; }

  function exGo(i) {
    const x = cxData();
    if (!x) return;
    const steps = x.cx.steps;
    i = Math.max(0, Math.min(steps.length - 1, i));
    EX.step = i;
    const s = steps[i];
    $("cxSlider").value = i;
    const root = $("ctrlDiagram");
    const rows = $("cxCard").querySelectorAll("tbody tr");
    rows.forEach((r) => r.classList.toggle("cur", +r.dataset.i === i));
    const cur = rows[i];
    if (cur) {
      const sc = cur.closest(".scroll-x");
      const top = cur.offsetTop - sc.clientHeight / 2;
      sc.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    }
    if (s.skip) {
      highlight(root, null, []);
      $("cxPos").textContent = `${fi(s.steps)} steps condensed`;
      return;
    }
    const prev = i > 0 && !steps[i - 1].skip ? steps[i - 1] : null;
    const spec = ctrlSpec(EX.mut);
    let edges = [];
    if (prev) {
      edges = spec.edges.filter((e) => e.from === prev.state && e.to === s.state && e.cls !== "cut");
      if (prev.state === "CHECK_STOP" && s.state === "DONE" && edges.length > 1) {
        edges = edges.filter((e) => (s.converged === "TRUE" || prev.converged === "TRUE" ? e.id === "e1" : e.id === "e2"));
      }
      if (!edges.length && s.state === "ABORT") edges = spec.edges.filter((e) => e.id === "eErr");
    }
    highlight(root, s.state, edges.map((e) => e.id));
    $("cxPos").textContent = `state ${s.state} · iter ${s.iter}`;
  }

  function renderNonvacuity() {
    const nv = D.nonvacuity;
    const branchesExpected = D.branches.filter(([g]) => g !== "TRUE").length;
    $("nvPanel").innerHTML = `<div class="grid3 stats3">
        <div class="stat"><span class="v">${nv.kinds.W_}</span><span class="l">premise witnesses reachable</span></div>
        <div class="stat"><span class="v">${nv.kinds.C_}</span><span class="l">conclusion probes reachable</span></div>
        <div class="stat"><span class="v">${nv.kinds.B_}</span><span class="l">branch queries (${branchesExpected} reachable, 1 must not be)</span></div></div>
      <p class="small" style="margin-top:12px">${badge(`${nv.as_expected}/${nv.queries} as expected`, "good")} for the delivered controller.</p>
      <h4 style="margin-top:12px">The controller's guards, in priority order</h4>
      <div class="scroll-x"><table><tbody>${D.branches.map(([g, t], i) => `<tr><td class="muted">B${i}</td><td class="mono small">${esc(g)}</td><td class="mono small">→ ${esc(t)}</td><td>${g === "TRUE" ? badge("unreachable", "grey") : badge("fires", "good")}</td></tr>`).join("")}</tbody></table></div>
      <p class="small muted">B0 keeps a terminal state where it is; B12 is the defensive fallback. Mutation complements this: non-vacuity shows a property is exercised, mutation shows it can fail.</p>`;
  }

  /* ---------- boot ---------- */
  function boot() {
    $("srcName").textContent = D.source.split("/").pop();
    $("footSrc").textContent = D.source;
    $("footHash").textContent = D.totals.stage1_digest;
    $("runId").textContent = D.run.run_id;
    renderWhy();
    renderOperator();
    renderCircuit();
    renderModes();
    $("iterSlider").max = N_UPD;
    const go = (i) => { stopPlay(); clearPlayMarks(); S.iter = Math.max(1, Math.min(N_UPD, i)); S.cand = null; renderIteration(); };
    $("iterSlider").addEventListener("input", (e) => go(+e.target.value));
    $("iterPrev").addEventListener("click", () => go(S.iter - 1));
    $("iterNext").addEventListener("click", () => go(S.iter + 1));
    $("playModes").addEventListener("click", playIteration);
    renderIteration();
    setupLensTabs();
    renderLogicalLens();
    renderProbabilistic();
    renderRuntime();
    renderPipeline();
    renderTogether();
    renderMutPicker();
    renderExplorer();
    renderNonvacuity();
  }
  boot();
})();
