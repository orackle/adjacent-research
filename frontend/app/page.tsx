"use client";

import React, { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";
import "./globals.css";

// ── Types ─────────────────────────────────────────────────────────────────────

interface MapResult {
  field: string;
  why: string;
  blocker: string;
  leap: "near" | "mid" | "far";
  adoption_urgency: number;
  feasibility_now: number;
  confidence: number;
  _score?: number;
}

interface MapResponse {
  technology: string;
  results: MapResult[];
}

interface ChainPaper {
  corpus_id: string;
  title: string;
  abstract: string;
  year: number | null;
  citation_count: number;
  cd_index: number | null;
  novelty_score: number | null;
  breakthrough_score: number | null;
  arxiv_id: string | null;
  doi: string | null;
}

interface EdgeLink {
  source: string;
  target: string;
}

interface FrontierItem {
  field: string;
  prediction: string;
  horizon: string;
}

interface TraceResponse {
  query: string;
  chain: ChainPaper[];
  narrative: string;
  transitions: { from_id: string; to_id: string; leap: string }[];
  pivotal_paper_id: string | null;
  frontier: FrontierItem[];
  edges: EdgeLink[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const EXAMPLES_MAP = [
  "diffusion models",
  "CRISPR gene editing",
  "solid-state batteries",
  "transformer architecture",
  "quantum error correction",
];

const EXAMPLES_TRACE = [
  "attention mechanism deep learning",
  "protein structure prediction",
  "reinforcement learning from human feedback",
  "graph neural networks",
];

const LEAP_LABELS: Record<string, string> = {
  near: "Adjacent Possible",
  mid: "Stretch Leap",
  far: "Frontier Leap",
};

const MAP_STEPS = [
  "Querying semantic index...",
  "Generating candidate fields...",
  "Scoring adoption barriers...",
  "Synthesizing ranked vectors...",
];

const TRACE_STEPS = [
  "Locating citation source nodes...",
  "Tracing BFS graph pathways...",
  "Evaluating bridge coefficient...",
  "Synthesizing causal lineage...",
];

const STEP_DURATIONS = [3000, 6000, 8000, 1500];

// ── Dynamic imports (shader gradient) ─────────────────────────────────────────

const ShaderGradientCanvas = dynamic(
  () => import("@shadergradient/react").then((mod) => mod.ShaderGradientCanvas),
  { ssr: false }
);

const ShaderGradient = dynamic(
  () => import("@shadergradient/react").then((mod) => mod.ShaderGradient),
  { ssr: false }
);

const ShaderGradientAny: any = ShaderGradient;

function ShaderGradientBackground({ dimmed }: { dimmed?: boolean }) {
  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100vw",
        height: "100vh",
        zIndex: -1,
        pointerEvents: "none",
        /* Overlay a white wash to tone down the saturation */
        background: dimmed
          ? "rgba(240,244,248,0.72)"
          : "rgba(240,244,248,0.45)",
      }}
    >
      <ShaderGradientCanvas
        lazyLoad={false}
        pointerEvents="none"
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      >
        <ShaderGradientAny
          animate="on"
          brightness={0.72}          /* Reduced from 1.2 */
          cAzimuthAngle={180}
          cDistance={2.8}
          cPolarAngle={95}
          cameraZoom={1}
          color1="#c2e4f5"           /* Softer colours */
          color2="#9dd5e8"
          color3="#dceefb"
          destination="onCanvas"
          embedMode="off"
          envPreset="city"
          fov={45}
          frameRate={10}
          gizmoHelper="hide"
          grain="off"
          lightType="3d"
          pixelDensity={1}
          positionX={0}
          positionY={-2.1}
          positionZ={0}
          range="disabled"
          rangeEnd={40}
          rangeStart={0}
          reflection={0.05}
          rotationX={0}
          rotationY={0}
          rotationZ={225}
          shader="defaults"
          type="waterPlane"
          uAmplitude={0}
          uDensity={1.6}
          uFrequency={4.5}
          uSpeed={0.12}             /* Slower movement */
          uStrength={2.2}
          uTime={0.2}
          wireframe={false}
        />
      </ShaderGradientCanvas>
    </div>
  );
}

// ── Shared UI components ───────────────────────────────────────────────────────

function LeapBadge({ leap }: { leap: string }) {
  return <span className={`leap-badge leap-${leap}`}>{LEAP_LABELS[leap] ?? leap}</span>;
}

function Spinner({ size = 16, color = "var(--accent)" }: { size?: number; color?: string }) {
  return (
    <div
      className="spin"
      style={{
        width: size,
        height: size,
        border: `2px solid ${color}`,
        borderTopColor: "transparent",
        borderRadius: "50%",
        flexShrink: 0,
      }}
    />
  );
}

function LoadingIndicator({ steps, currentStep }: { steps: string[]; currentStep: number }) {
  const progressPercent = Math.min(100, Math.round((currentStep / steps.length) * 100));
  return (
    <div className="fade-up" style={{ padding: "24px", background: "var(--s0)", border: "1px solid var(--b1)", borderRadius: "8px", maxWidth: "380px", margin: "40px auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <Spinner />
          <span style={{ fontWeight: 600, fontSize: "0.83rem", color: "var(--t1)" }}>Running pipeline...</span>
        </div>
        <span className="font-mono" style={{ fontSize: "0.73rem", color: "var(--t3)", fontWeight: 500 }}>{progressPercent}%</span>
      </div>
      <div className="progress-rail" style={{ marginBottom: "14px" }}>
        <div className="progress-rail-fill" style={{ width: `${progressPercent}%` }} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
        {steps.map((step, i) => {
          const done = i < currentStep;
          const active = i === currentStep;
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span className="font-mono" style={{ width: "14px", fontSize: "0.73rem", color: done ? "var(--near)" : active ? "var(--accent)" : "var(--t4)", fontWeight: active ? 700 : 400 }}>
                {done ? "✓" : active ? "→" : "·"}
              </span>
              <span style={{ fontSize: "0.76rem", color: done ? "var(--t2)" : active ? "var(--t1)" : "var(--t4)", fontWeight: active ? 600 : 400 }}>
                {step}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Color Utilities ────────────────────────────────────────────────────────────

function getUrgencyColor(val: number) {
  if (val >= 67) return "var(--near)";
  if (val >= 34) return "var(--mid)";
  return "var(--t3)";
}

function getFeasibilityColor(val: number) {
  if (val >= 67) return "var(--feas-hi)";
  if (val >= 34) return "var(--accent)";
  return "var(--feas-lo)";
}

// ── Paper Link Component ───────────────────────────────────────────────────────

function PaperLinks({ paper }: { paper: ChainPaper }) {
  const openAlexUrl = paper.corpus_id.startsWith("W")
    ? `https://openalex.org/${paper.corpus_id}`
    : null;

  return (
    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "8px" }}>
      {paper.doi && (
        <a
          className="paper-link"
          href={`https://doi.org/${paper.doi}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          DOI ↗
        </a>
      )}
      {paper.arxiv_id && (
        <a
          className="paper-link"
          href={`https://arxiv.org/abs/${paper.arxiv_id}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          arXiv ↗
        </a>
      )}
      {openAlexUrl && (
        <a
          className="paper-link"
          href={openAlexUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          OpenAlex ↗
        </a>
      )}
    </div>
  );
}

// ── Scatter Plot ───────────────────────────────────────────────────────────────

function ScatterPlot({ results, selectedIndex, onSelectIndex }: {
  results: MapResult[];
  selectedIndex: number | null;
  onSelectIndex: (i: number) => void;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const W = 380, H = 260;
  const PAD = { top: 16, right: 16, bottom: 36, left: 40 };
  const toX = (v: number) => PAD.left + ((v / 100) * (W - PAD.left - PAD.right));
  const toY = (v: number) => H - PAD.bottom - ((v / 100) * (H - PAD.top - PAD.bottom));
  const leapColors: Record<string, string> = { near: "var(--near)", mid: "var(--mid)", far: "var(--far)" };
  const gridLines = [0, 25, 50, 75, 100];

  return (
    <div style={{ width: "100%", overflowX: "hidden" }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block", margin: "0 auto" }}>
        {gridLines.map((v) => (
          <g key={v}>
            <line x1={toX(v)} y1={PAD.top} x2={toX(v)} y2={H - PAD.bottom} stroke="var(--b1)" strokeWidth={1} />
            <line x1={PAD.left} y1={toY(v)} x2={W - PAD.right} y2={toY(v)} stroke="var(--b1)" strokeWidth={1} />
            <text className="font-mono" x={toX(v)} y={H - PAD.bottom + 12} textAnchor="middle" fill="var(--t4)" fontSize={8}>{v}</text>
            <text className="font-mono" x={PAD.left - 5} y={toY(v) + 3} textAnchor="end" fill="var(--t4)" fontSize={8}>{v}</text>
          </g>
        ))}
        <text className="font-ui" x={W / 2} y={H - 2} textAnchor="middle" fill="var(--t3)" fontSize={8} fontWeight={700} letterSpacing="0.06em">FEASIBILITY NOW</text>
        <text className="font-ui" x={9} y={H / 2} textAnchor="middle" fill="var(--t3)" fontSize={8} fontWeight={700} letterSpacing="0.06em" transform={`rotate(-90, 9, ${H / 2})`}>ADOPTION URGENCY</text>

        {results.map((r, i) => {
          const cx = toX(r.feasibility_now ?? 0);
          const cy = toY(r.adoption_urgency ?? 0);
          const color = leapColors[r.leap] ?? "var(--accent)";
          const isSelected = selectedIndex === i;
          const isHovered = hovered === i;
          return (
            <g key={i} onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)} onClick={() => onSelectIndex(i)} style={{ cursor: "pointer" }}>
              {(isHovered || isSelected) && <circle cx={cx} cy={cy} r={isSelected ? 13 : 9} fill={color} opacity={0.14} />}
              <circle cx={cx} cy={cy} r={isSelected ? 6 : 5} fill={color} stroke="#fff" strokeWidth={1.5} />
            </g>
          );
        })}

        {hovered !== null && (() => {
          const r = results[hovered];
          const cx = toX(r.feasibility_now ?? 0);
          const cy = toY(r.adoption_urgency ?? 0);
          const tipW = 150, tipH = 42;
          const tx = Math.min(cx + 8, W - PAD.right - tipW);
          const ty = Math.max(cy - tipH - 6, PAD.top);
          return (
            <g style={{ pointerEvents: "none" }}>
              <rect x={tx} y={ty} width={tipW} height={tipH} rx={4} fill="rgba(10,15,30,0.82)" />
              <foreignObject x={tx + 6} y={ty + 5} width={tipW - 12} height={tipH - 10}>
                <div style={{ fontSize: "8px", color: "#e2e8f0", lineHeight: 1.35 }}>
                  <div style={{ fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.field}</div>
                  <div style={{ color: "#94a3b8", marginTop: "2px" }}>Urgency: {r.adoption_urgency} · Feas: {r.feasibility_now}</div>
                </div>
              </foreignObject>
            </g>
          );
        })()}
      </svg>
    </div>
  );
}

// ── Timeline components ────────────────────────────────────────────────────────

function TimelinePaperNode({ paper, index, isPivotal, isActive, onClick, transition }: {
  paper: ChainPaper;
  index: number;
  isPivotal: boolean;
  isActive: boolean;
  onClick: () => void;
  transition?: string;
}) {
  return (
    <div style={{ position: "relative", width: "100%", paddingLeft: "76px", paddingBottom: "28px" }}>
      <div className={`timeline-node-dot ${isPivotal ? "pivotal" : ""}`} />

      <span className="font-mono" style={{
        position: "absolute", left: "0", width: "36px", textAlign: "right",
        fontSize: "0.75rem", fontWeight: 700,
        color: isPivotal ? "var(--far)" : "var(--t3)", top: "-1px",
      }}>
        {paper.year ?? "—"}
      </span>

      {transition && (
        <div style={{
          background: "var(--s0)", border: "1px solid var(--b1)", borderRadius: "4px",
          padding: "3px 9px", fontSize: "0.7rem", color: "var(--t2)",
          display: "inline-block", marginBottom: "10px", maxWidth: "400px",
        }}>
          <span style={{ color: "var(--accent)", fontWeight: 700 }}>Leap: </span>{transition}
        </div>
      )}

      <div
        onClick={onClick}
        className="card"
        style={{
          padding: "14px 18px",
          cursor: "pointer",
          background: isActive ? "rgba(79,70,229,0.07)" : "rgba(255,255,255,0.85)",
          borderColor: isActive ? "rgba(79,70,229,0.28)" : isPivotal ? "var(--far-border)" : "var(--b1)",
          borderRadius: "8px",
          boxShadow: isPivotal ? "0 2px 12px var(--far-bg)" : "0 1px 4px rgba(15,23,42,0.03)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "10px" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h4 className="font-ui" style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--t1)", lineHeight: 1.3, marginBottom: "4px" }}>
              {paper.title}
            </h4>
            <div className="font-mono" style={{ display: "flex", gap: "10px", fontSize: "0.71rem", color: "var(--t3)", flexWrap: "wrap" }}>
              <span>{paper.citation_count.toLocaleString()} citations</span>
              {paper.breakthrough_score != null && (
                <span style={{ color: "var(--near)", fontWeight: 500 }}>
                  breakthrough:{paper.breakthrough_score.toFixed(1)}
                </span>
              )}
            </div>
          </div>
          <div className="font-mono" style={{ fontSize: "0.73rem", fontWeight: 500, color: "var(--t4)", border: "1px solid var(--b1)", padding: "2px 6px", borderRadius: "3px", background: "rgba(255,255,255,0.70)", flexShrink: 0 }}>
            #{index + 1}
          </div>
        </div>

        {isActive && (
          <div className="slide-in" style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid var(--b1)" }}>
            {paper.abstract && (
              <p className="font-ui" style={{ fontSize: "0.78rem", color: "var(--t2)", lineHeight: 1.6, marginBottom: "10px" }}>
                {paper.abstract}
              </p>
            )}
            <PaperLinks paper={paper} />
          </div>
        )}
      </div>
    </div>
  );
}

function CitationMiniGraph({ chain, edges, pivotalId }: { chain: ChainPaper[]; edges: EdgeLink[]; pivotalId: string | null }) {
  if (chain.length < 2) return null;
  const W = 380, H = 140, nodeR = 12, padding = 28;
  const positions: Record<string, { x: number; y: number }> = {};
  chain.forEach((p, i) => {
    const x = padding + (i / Math.max(chain.length - 1, 1)) * (W - 2 * padding);
    const y = H / 2 + (i % 2 === 0 ? -22 : 22);
    positions[p.corpus_id] = { x, y };
  });
  return (
    <div style={{ width: "100%", overflowX: "hidden" }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block", margin: "0 auto" }}>
        {edges.map((e, i) => {
          const s = positions[e.source], t = positions[e.target];
          if (!s || !t) return null;
          return <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke="var(--accent)" strokeWidth={1} strokeDasharray="3 3" opacity={0.25} />;
        })}
        {chain.map((p, i) => {
          if (i === 0) return null;
          const s = positions[chain[i - 1].corpus_id], t = positions[p.corpus_id];
          return <line key={`seq-${i}`} x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke="var(--accent)" strokeWidth={1.5} opacity={0.5} />;
        })}
        {chain.map((p) => {
          const pos = positions[p.corpus_id];
          const isPivotal = p.corpus_id === pivotalId;
          const color = isPivotal ? "var(--far)" : "var(--accent)";
          return (
            <g key={p.corpus_id}>
              {isPivotal && <circle cx={pos.x} cy={pos.y} r={nodeR + 4} fill="var(--far-bg)" opacity={0.4} />}
              <circle cx={pos.x} cy={pos.y} r={nodeR} fill="rgba(255,255,255,0.90)" stroke={color} strokeWidth={isPivotal ? 2 : 1.2} />
              <text className="font-mono" x={pos.x} y={pos.y + 1} textAnchor="middle" dominantBaseline="middle" fontSize={7} fontWeight={700} fill={color}>
                {p.year ? String(p.year).slice(-2) : "?"}
              </text>
              <title>{p.title}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function NarrativeBlock({ narrative }: { narrative: string }) {
  return (
    <div className="narrative-block">
      <div style={{ fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--accent)", marginBottom: "8px" }}>
        Intellectual Lineage Narrative
      </div>
      <p>{narrative}</p>
    </div>
  );
}

// ── Landing Page ───────────────────────────────────────────────────────────────

function LandingPage({ onStart }: { onStart: (mode: "map" | "trace", query: string) => void }) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"map" | "trace">("map");

  const submit = () => {
    if (query.trim()) onStart(mode, query.trim());
  };

  return (
    <motion.div
      className="landing-screen"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.35 }}
    >
      {/* Logo */}
      <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05, duration: 0.4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "12px", justifyContent: "center" }}>
          <span style={{ fontSize: "2rem" }}>◈</span>
          <h1 className="font-display" style={{ fontSize: "2rem", fontWeight: 800, color: "var(--t1)", letterSpacing: "-0.03em" }}>
            Interlace
          </h1>
        </div>
        <p style={{ fontSize: "0.9rem", color: "var(--t3)", textAlign: "center", marginBottom: "40px" }}>
          Research Adjacency Engine
        </p>
      </motion.div>

      {/* Tagline */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12, duration: 0.4 }} style={{ marginBottom: "36px", textAlign: "center" }}>
        <h2 className="font-display" style={{ fontSize: "2.8rem", fontWeight: 800, color: "var(--t1)", letterSpacing: "-0.03em", lineHeight: 1.12, marginBottom: "14px", maxWidth: "580px" }}>
          Discover What's<br />Adjacent to Any Idea
        </h2>
        <p style={{ fontSize: "1rem", color: "var(--t2)", lineHeight: 1.65, maxWidth: "460px", margin: "0 auto" }}>
          Map the frontier of any research domain — ranked adjacency pathways, feasibility scores, and causal citation chains.
        </p>
      </motion.div>

      {/* Mode toggle + search */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, duration: 0.4 }} style={{ width: "100%", maxWidth: "520px" }}>
        {/* Mode switch */}
        <div style={{ display: "flex", gap: "8px", marginBottom: "12px", background: "rgba(255,255,255,0.70)", borderRadius: "10px", padding: "4px", border: "1px solid var(--b1)" }}>
          {(["map", "trace"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                flex: 1, padding: "8px", border: "none", borderRadius: "7px", cursor: "pointer",
                fontFamily: "inherit", fontSize: "0.8rem", fontWeight: 600,
                transition: "all 0.15s ease",
                background: mode === m ? "white" : "transparent",
                color: mode === m ? "var(--t1)" : "var(--t3)",
                boxShadow: mode === m ? "0 1px 6px rgba(15,23,42,0.10)" : "none",
              }}
            >
              {m === "map" ? "◈ Adjacent Mapper" : "⚡ Lineage Tracer"}
            </button>
          ))}
        </div>

        {/* Search box */}
        <div style={{ position: "relative", marginBottom: "14px" }}>
          <svg style={{ position: "absolute", left: "16px", top: "50%", transform: "translateY(-50%)", color: "var(--t4)", pointerEvents: "none" }}
            width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}>
            <circle cx={11} cy={11} r={8} /><path d="m21 21-4.35-4.35" />
          </svg>
          <input
            className="search-input-hero"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder={mode === "map" ? "e.g. diffusion models, CRISPR..." : "e.g. transformer architecture..."}
            autoFocus
          />
        </div>

        <button className="btn-primary-hero" style={{ width: "100%", marginBottom: "20px" }} onClick={submit} disabled={!query.trim()}>
          {mode === "map" ? "Map Adjacencies →" : "Trace Lineage →"}
        </button>

        {/* Example chips */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", justifyContent: "center" }}>
          {(mode === "map" ? EXAMPLES_MAP : EXAMPLES_TRACE).slice(0, 4).map((ex) => (
            <button key={ex} className="chip" onClick={() => { setQuery(ex); onStart(mode, ex); }}>
              {ex}
            </button>
          ))}
        </div>
      </motion.div>

      {/* Feature cards */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35, duration: 0.5 }}
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", maxWidth: "520px", width: "100%", marginTop: "44px" }}>
        <div className="hero-feature-card">
          <div style={{ fontSize: "1.1rem", marginBottom: "8px" }}>◈</div>
          <div style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--t1)", marginBottom: "5px" }}>Adjacent Mapper</div>
          <p style={{ fontSize: "0.75rem", color: "var(--t3)", lineHeight: 1.5 }}>
            Ranked adjacent fields scored by urgency and feasibility.
          </p>
        </div>
        <div className="hero-feature-card">
          <div style={{ fontSize: "1.1rem", marginBottom: "8px" }}>⚡</div>
          <div style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--t1)", marginBottom: "5px" }}>Lineage Tracer</div>
          <p style={{ fontSize: "0.75rem", color: "var(--t3)", lineHeight: 1.5 }}>
            Causal citation chains from founding paper to frontier.
          </p>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Sidebar ────────────────────────────────────────────────────────────────────

function Sidebar({ activeTab, setActiveTab, mapQuery, setMapQuery, traceQuery, setTraceQuery, mapLoading, traceLoading, onMap, onTrace }: {
  activeTab: "map" | "trace";
  setActiveTab: (t: "map" | "trace") => void;
  mapQuery: string;
  setMapQuery: (v: string) => void;
  traceQuery: string;
  setTraceQuery: (v: string) => void;
  mapLoading: boolean;
  traceLoading: boolean;
  onMap: (q?: string) => void;
  onTrace: (q?: string) => void;
}) {
  return (
    <motion.aside
      className="sidebar"
      initial={{ x: -280, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 280, damping: 28 }}
    >
      {/* Logo header */}
      <div style={{ padding: "24px 20px 16px", borderBottom: "1px solid var(--b1)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "2px" }}>
          <span style={{ fontSize: "1.1rem" }}>◈</span>
          <h1 className="font-display" style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--t1)", letterSpacing: "-0.02em" }}>
            Interlace
          </h1>
        </div>
        <p style={{ fontSize: "0.68rem", color: "var(--t4)", lineHeight: 1.3, paddingLeft: "2px" }}>
          Research Adjacency Engine
        </p>
      </div>

      {/* Scrollable inner */}
      <div className="sidebar-scroll-inner" style={{ paddingTop: "16px" }}>
        {/* Mode tabs */}
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginBottom: "16px" }}>
          {(["map", "trace"] as const).map((tab) => (
            <button
              key={tab}
              className={`mode-tab ${activeTab === tab ? "active" : ""}`}
              onClick={() => setActiveTab(tab)}
            >
              <span className="mode-tab-icon">{tab === "map" ? "◈" : "⚡"}</span>
              <div>
                <div className="mode-tab-label">{tab === "map" ? "Adjacent Mapper" : "Lineage Tracer"}</div>
                <div className="mode-tab-desc">{tab === "map" ? "Discovery horizon vectors" : "Causal citation chains"}</div>
              </div>
            </button>
          ))}
        </div>

        <div className="divider" />

        {/* Query panel */}
        <AnimatePresence mode="wait">
          {activeTab === "map" ? (
            <motion.div key="map-panel" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.15 }}>
              <span className="section-label" style={{ display: "block", marginBottom: "8px" }}>Technology Query</span>
              <div style={{ position: "relative", marginBottom: "10px" }}>
                <svg style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--t4)" }} width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                  <circle cx={11} cy={11} r={8} /><path d="m21 21-4.35-4.35" />
                </svg>
                <input className="search-input" type="text" value={mapQuery} onChange={(e) => setMapQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onMap()} placeholder="Technology area..." disabled={mapLoading} autoComplete="off" />
              </div>
              <button className="btn-primary" style={{ width: "100%", marginBottom: "20px" }} onClick={() => onMap()} disabled={mapLoading || !mapQuery.trim()}>
                {mapLoading ? "Mapping..." : "Map Adjacencies"}
              </button>
              <span className="section-label" style={{ display: "block", marginBottom: "7px" }}>Try Examples</span>
              <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                {EXAMPLES_MAP.map((ex) => (
                  <button key={ex} className="chip" style={{ textAlign: "left", display: "block" }} onClick={() => { setMapQuery(ex); onMap(ex); }} disabled={mapLoading}>
                    {ex}
                  </button>
                ))}
              </div>
            </motion.div>
          ) : (
            <motion.div key="trace-panel" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.15 }}>
              <span className="section-label" style={{ display: "block", marginBottom: "8px" }}>Research Topic</span>
              <div style={{ position: "relative", marginBottom: "10px" }}>
                <svg style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--t4)" }} width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                  <circle cx={11} cy={11} r={8} /><path d="m21 21-4.35-4.35" />
                </svg>
                <input className="search-input" type="text" value={traceQuery} onChange={(e) => setTraceQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onTrace()} placeholder="Topic or mechanism..." disabled={traceLoading} autoComplete="off" />
              </div>
              <button className="btn-primary" style={{ width: "100%", marginBottom: "20px" }} onClick={() => onTrace()} disabled={traceLoading || !traceQuery.trim()}>
                {traceLoading ? "Tracing..." : "Trace Lineage"}
              </button>
              <span className="section-label" style={{ display: "block", marginBottom: "7px" }}>Try Examples</span>
              <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                {EXAMPLES_TRACE.map((ex) => (
                  <button key={ex} className="chip" style={{ textAlign: "left", display: "block" }} onClick={() => { setTraceQuery(ex); onTrace(ex); }} disabled={traceLoading}>
                    {ex}
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Footer */}
      <div style={{ padding: "12px 20px", borderTop: "1px solid var(--b1)", flexShrink: 0 }}>
        <div style={{ fontSize: "0.65rem", color: "var(--t4)", textAlign: "center" }}>Interlace v1.2 · MIT License</div>
      </div>
    </motion.aside>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

type AppTab = "map" | "trace";

export default function Home() {
  // Landing vs app view
  const [hasStarted, setHasStarted] = useState(false);
  const [activeTab, setActiveTab] = useState<AppTab>("map");

  // Map state
  const [mapQuery, setMapQuery] = useState("");
  const [mapLoading, setMapLoading] = useState(false);
  const [mapStep, setMapStep] = useState(0);
  const [mapResponse, setMapResponse] = useState<MapResponse | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapEmpty, setMapEmpty] = useState<string | null>(null);
  const [selectedMapIndex, setSelectedMapIndex] = useState<number | null>(null);

  // Trace state
  const [traceQuery, setTraceQuery] = useState("");
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceStep, setTraceStep] = useState(0);
  const [traceResponse, setTraceResponse] = useState<TraceResponse | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [activeTracePaperId, setActiveTracePaperId] = useState<string | null>(null);

  const stepTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const startFakeProgress = useCallback((setStep: (n: number) => void) => {
    setStep(0);
    let elapsed = 0;
    STEP_DURATIONS.forEach((dur, i) => {
      elapsed += dur;
      const t = setTimeout(() => setStep(i + 1), elapsed);
      stepTimers.current.push(t);
    });
  }, []);

  const clearFakeProgress = useCallback(() => {
    stepTimers.current.forEach(clearTimeout);
    stepTimers.current = [];
  }, []);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const handleMap = async (tech?: string) => {
    const q = (tech ?? mapQuery).trim();
    if (!q) return;
    setHasStarted(true);
    setActiveTab("map");
    setMapLoading(true);
    setMapError(null);
    setMapEmpty(null);
    setMapResponse(null);
    setSelectedMapIndex(null);
    startFakeProgress(setMapStep);
    try {
      const res = await fetch(`${apiUrl}/map`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ technology: q, top_k: 12 }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `Server error ${res.status}`);
      }
      const data: MapResponse = await res.json();
      clearFakeProgress();
      setMapStep(MAP_STEPS.length);
      if (!data.results?.length) {
        setMapEmpty(`No adjacencies found for "${q}". Try rephrasing.`);
      } else {
        setMapResponse(data);
      }
    } catch (e: unknown) {
      clearFakeProgress();
      setMapError((e as Error).message ?? "Unexpected error. Is the backend running?");
    } finally {
      setMapLoading(false);
    }
  };

  const handleTrace = async (q?: string) => {
    const query = (q ?? traceQuery).trim();
    if (!query) return;
    setHasStarted(true);
    setActiveTab("trace");
    setTraceLoading(true);
    setTraceError(null);
    setTraceResponse(null);
    setActiveTracePaperId(null);
    startFakeProgress(setTraceStep);
    try {
      const res = await fetch(`${apiUrl}/trace`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, max_chain: 8 }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `Server error ${res.status}`);
      }
      const data: TraceResponse = await res.json();
      clearFakeProgress();
      setTraceStep(TRACE_STEPS.length);
      setTraceResponse(data);
    } catch (e: unknown) {
      clearFakeProgress();
      setTraceError((e as Error).message ?? "Unexpected error. Is the backend running?");
    } finally {
      setTraceLoading(false);
    }
  };

  const handleLandingStart = (mode: "map" | "trace", query: string) => {
    if (mode === "map") {
      setMapQuery(query);
      handleMap(query);
    } else {
      setTraceQuery(query);
      handleTrace(query);
    }
  };

  return (
    <>
      <ShaderGradientBackground dimmed={hasStarted} />

      <AnimatePresence mode="wait">
        {!hasStarted ? (
          <LandingPage key="landing" onStart={handleLandingStart} />
        ) : (
          <motion.div
            key="app"
            className="app-shell"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
          >
            {/* Sidebar */}
            <Sidebar
              activeTab={activeTab}
              setActiveTab={setActiveTab}
              mapQuery={mapQuery}
              setMapQuery={setMapQuery}
              traceQuery={traceQuery}
              setTraceQuery={setTraceQuery}
              mapLoading={mapLoading}
              traceLoading={traceLoading}
              onMap={handleMap}
              onTrace={handleTrace}
            />

            {/* Main content */}
            <main className="content-area" style={{ position: "relative", zIndex: 1 }}>
              <AnimatePresence mode="wait">
                {activeTab === "map" ? (
                  <motion.div key="map-tab" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.18 }}>
                    {mapLoading && <div className="content-inner"><LoadingIndicator steps={MAP_STEPS} currentStep={mapStep} /></div>}

                    {mapError && (
                      <div className="content-inner">
                        <div className="state-box" style={{ borderColor: "#fecaca", background: "#fef2f2", color: "#b91c1c" }}>
                          ⚠️ {mapError}
                        </div>
                      </div>
                    )}

                    {mapEmpty && !mapLoading && (
                      <div className="content-inner">
                        <div className="state-box">{mapEmpty}</div>
                      </div>
                    )}

                    {mapResponse && !mapLoading && (
                      <div className="result-split">
                        {/* Left: scatter + legend */}
                        <div className="result-left">
                          <div style={{ marginBottom: "20px" }}>
                            <span className="section-label">Spatial Opportunity Map</span>
                            <h3 className="font-display" style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--t1)", marginTop: "3px" }}>
                              The Adjacency Compass
                            </h3>
                            <p style={{ fontSize: "0.73rem", color: "var(--t3)", lineHeight: 1.4, marginTop: "2px" }}>
                              Click points to highlight the matching field.
                            </p>
                          </div>

                          <div className="card" style={{ padding: "16px", marginBottom: "20px" }}>
                            <ScatterPlot
                              results={mapResponse.results}
                              selectedIndex={selectedMapIndex}
                              onSelectIndex={(idx) => {
                                setSelectedMapIndex(idx);
                                document.getElementById(`map-row-${idx}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                              }}
                            />
                          </div>

                          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            {[
                              { key: "near", label: "Adjacent Possible", sub: "Ready to apply now" },
                              { key: "mid",  label: "Stretch Leap",      sub: "Requires adaptation" },
                              { key: "far",  label: "Frontier Leap",     sub: "Highly speculative" },
                            ].map(({ key, label, sub }) => (
                              <div key={key} style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.72rem", color: "var(--t2)" }}>
                                <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: `var(--${key})`, flexShrink: 0 }} />
                                <strong>{label}</strong>
                                <span style={{ color: "var(--t4)" }}>— {sub}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Right: ranked list */}
                        <div className="result-right">
                          <div style={{ marginBottom: "20px" }}>
                            <span className="section-label">Vector Synthesis</span>
                            <h2 className="font-display" style={{ fontSize: "1.55rem", fontWeight: 800, color: "var(--t1)" }}>
                              Ranked Adjacency Pathways
                            </h2>
                            <p style={{ fontSize: "0.78rem", color: "var(--t3)" }}>
                              Query: <strong style={{ color: "var(--t1)" }}>{mapResponse.technology}</strong>
                            </p>
                          </div>

                          <div>
                            {mapResponse.results.map((r, i) => {
                              const isActive = selectedMapIndex === i;
                              return (
                                <div
                                  key={r.field}
                                  id={`map-row-${i}`}
                                  className={`result-row ${isActive ? "active" : ""}`}
                                  onClick={() => setSelectedMapIndex(isActive ? null : i)}
                                >
                                  <span className="rank-num" style={{ marginTop: "4px" }}>{String(i + 1).padStart(2, "0")}</span>

                                  <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "10px", marginBottom: "4px" }}>
                                      <h3 className="font-ui" style={{ fontSize: "0.93rem", fontWeight: 700, color: "var(--t1)", lineHeight: 1.3 }}>
                                        {r.field}
                                      </h3>
                                      <LeapBadge leap={r.leap} />
                                    </div>

                                    <p style={{ fontSize: "0.79rem", color: "var(--t2)", lineHeight: 1.5, marginBottom: "6px" }}>
                                      {r.why}
                                    </p>

                                    <AnimatePresence>
                                      {isActive && (
                                        <motion.div
                                          initial={{ height: 0, opacity: 0 }}
                                          animate={{ height: "auto", opacity: 1 }}
                                          exit={{ height: 0, opacity: 0 }}
                                          transition={{ duration: 0.18, ease: "easeOut" }}
                                          style={{ overflow: "hidden" }}
                                        >
                                          <div style={{ background: "rgba(255,255,255,0.85)", border: "1px solid var(--b1)", borderRadius: "6px", padding: "10px 14px", marginTop: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
                                            <div style={{ fontSize: "0.77rem", color: "var(--t2)" }}>
                                              <strong style={{ color: "var(--t4)", textTransform: "uppercase", fontSize: "0.66rem" }}>Blocker: </strong>{r.blocker}
                                            </div>
                                            <div style={{ fontSize: "0.72rem", color: "var(--t3)" }}>
                                              Confidence: <strong style={{ color: "var(--t1)" }}>{r.confidence}%</strong>
                                            </div>
                                          </div>
                                        </motion.div>
                                      )}
                                    </AnimatePresence>
                                  </div>

                                  <div style={{ display: "flex", gap: "10px", flexShrink: 0, paddingLeft: "10px" }}>
                                    <div style={{ textAlign: "right" }}>
                                      <div className="font-mono score-display sm" style={{ color: getUrgencyColor(r.adoption_urgency) }}>{r.adoption_urgency}</div>
                                      <span style={{ fontSize: "0.63rem", color: "var(--t4)" }}>urgency</span>
                                    </div>
                                    <div style={{ textAlign: "right" }}>
                                      <div className="font-mono score-display sm" style={{ color: getFeasibilityColor(r.feasibility_now) }}>{r.feasibility_now}</div>
                                      <span style={{ fontSize: "0.63rem", color: "var(--t4)" }}>feasibility</span>
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    )}

                    {!mapLoading && !mapResponse && !mapError && !mapEmpty && (
                      <div className="content-inner" style={{ textAlign: "center", paddingTop: "80px" }}>
                        <div className="font-display" style={{ fontSize: "2rem", color: "var(--t4)", fontStyle: "italic", marginBottom: "14px" }}>◈</div>
                        <h3 className="font-display" style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--t1)", marginBottom: "8px" }}>Adjacency Discovery</h3>
                        <p style={{ color: "var(--t3)", fontSize: "0.83rem", maxWidth: "320px", margin: "0 auto", lineHeight: 1.5 }}>
                          Use the sidebar to run a query.
                        </p>
                      </div>
                    )}
                  </motion.div>
                ) : (
                  <motion.div key="trace-tab" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.18 }}>
                    <div className="content-inner">
                      {traceLoading && <LoadingIndicator steps={TRACE_STEPS} currentStep={traceStep} />}

                      {traceError && (
                        <div className="state-box" style={{ borderColor: "#fecaca", background: "#fef2f2", color: "#b91c1c" }}>
                          ⚠️ Pipeline tracing failed: {traceError}
                        </div>
                      )}

                      {traceResponse && !traceLoading && (
                        <div>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "28px", borderBottom: "1px solid var(--b1)", paddingBottom: "14px" }}>
                            <div>
                              <span className="section-label">Intellectual Trace</span>
                              <h2 className="font-display" style={{ fontSize: "1.7rem", fontWeight: 800, color: "var(--t1)", marginTop: "3px" }}>
                                Lineage Chain
                              </h2>
                              <p style={{ fontSize: "0.78rem", color: "var(--t3)" }}>
                                Tracing: <strong style={{ color: "var(--t1)" }}>{traceResponse.query}</strong>
                              </p>
                            </div>
                            <span className="font-mono" style={{ fontSize: "0.78rem", color: "var(--t2)", fontWeight: 500 }}>
                              {traceResponse.chain.length} papers · {traceResponse.edges?.length ?? 0} edges
                            </span>
                          </div>

                          <div className="card" style={{ padding: "18px", marginBottom: "28px" }}>
                            <span className="section-label" style={{ display: "block", marginBottom: "10px" }}>Citation Graph (BFS 3 hops)</span>
                            <CitationMiniGraph chain={traceResponse.chain} edges={traceResponse.edges ?? []} pivotalId={traceResponse.pivotal_paper_id} />
                          </div>

                          <NarrativeBlock narrative={traceResponse.narrative} />

                          {/* Timeline */}
                          <div style={{ position: "relative", width: "100%", margin: "36px 0" }}>
                            <div className="timeline-rail" />
                            <div style={{ display: "flex", flexDirection: "column" }}>
                              {traceResponse.chain.map((paper, i) => {
                                const isPivotal = paper.corpus_id === traceResponse.pivotal_paper_id;
                                const isActive = activeTracePaperId === paper.corpus_id;
                                const transitions = traceResponse.transitions ?? [];
                                const transition = transitions.find((t) => t.to_id === paper.corpus_id)?.leap;
                                return (
                                  <TimelinePaperNode
                                    key={paper.corpus_id}
                                    paper={paper}
                                    index={i}
                                    isPivotal={isPivotal}
                                    isActive={isActive}
                                    onClick={() => setActiveTracePaperId(isActive ? null : paper.corpus_id)}
                                    transition={transition}
                                  />
                                );
                              })}
                            </div>
                          </div>

                          {/* Horizon Roadmap */}
                          {traceResponse.frontier?.length > 0 && (
                            <div style={{ marginTop: "44px" }}>
                              <div style={{ marginBottom: "14px" }}>
                                <span className="section-label">Horizon Roadmap</span>
                                <h3 className="font-display" style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--t1)", marginTop: "3px" }}>
                                  Predicted Discoveries
                                </h3>
                              </div>
                              <div className="horizon-bar">
                                {[
                                  { label: "1–2 Years", color: "var(--near)", filter: (f: FrontierItem) => f.horizon.includes("1-2") || f.horizon.toLowerCase().includes("near") },
                                  { label: "3–5 Years", color: "var(--mid)",  filter: (f: FrontierItem) => f.horizon.includes("3-5") || f.horizon.toLowerCase().includes("mid") },
                                  { label: "5–10 Years", color: "var(--far)", filter: (f: FrontierItem) => f.horizon.includes("5-10") || f.horizon.toLowerCase().includes("far") || f.horizon.includes("10") },
                                ].map(({ label, color, filter }) => (
                                  <div key={label} className="horizon-zone">
                                    <div className="horizon-zone-label" style={{ color }}>{label}</div>
                                    {traceResponse.frontier.filter(filter).map((f, i) => (
                                      <div key={i} style={{ marginBottom: "10px" }}>
                                        <h5 className="font-ui" style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--t1)", marginBottom: "2px" }}>{f.field}</h5>
                                        <p style={{ fontSize: "0.72rem", color: "var(--t3)", lineHeight: 1.4 }}>{f.prediction}</p>
                                      </div>
                                    ))}
                                    {traceResponse.frontier.filter(filter).length === 0 && (
                                      <span style={{ fontSize: "0.71rem", color: "var(--t4)" }}>No predictions.</span>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {!traceLoading && !traceResponse && !traceError && (
                        <div style={{ textAlign: "center", paddingTop: "80px" }}>
                          <div className="font-display" style={{ fontSize: "2rem", color: "var(--t4)", fontStyle: "italic", marginBottom: "14px" }}>⚡</div>
                          <h3 className="font-display" style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--t1)", marginBottom: "8px" }}>Citation Trace</h3>
                          <p style={{ color: "var(--t3)", fontSize: "0.83rem", maxWidth: "320px", margin: "0 auto", lineHeight: 1.5 }}>
                            Use the sidebar to trace a research lineage.
                          </p>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </main>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
