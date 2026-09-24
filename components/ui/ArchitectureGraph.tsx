"use client";

import type { KeyboardEvent, RefObject } from "react";

export type GraphNode = {
  id: string;
  /** An agent node draws an orb; a plain node draws a code glyph instead. */
  agent: boolean;
  /** Role, not function name — the tool's identifier belongs to the detail graph. */
  label: string;
  blurb: string;
};

type Props = {
  nodes: GraphNode[];
  selected: number;
  onSelect: (index: number) => void;
  onKeyDown: (event: KeyboardEvent) => void;
  tabs: RefObject<(SVGGElement | null)[]>;
};

// Laid out on one grid: the tool columns are 216 wide starting at these x's,
// which puts their centres at 170 / 404 / 638. The coach and the learner share
// the middle centre, and the two return lanes sit outside the dashed group at
// x=22 and x=778 so they never cross it.
const COLUMN = [62, 296, 530];
const NODE_W = 216;
const NODE_TOP = 152;
const NODE_H = 86;
const CENTRE = [170, 404, 638];

export function ArchitectureGraph({ nodes, selected, onSelect, onKeyDown, tabs }: Props) {
  return (
    <svg
      className="graph"
      viewBox="0 0 800 390"
      role="group"
      aria-label="Coach, tools and learner, and the edges between them"
    >
      <defs>
        <radialGradient id="orbFill" cx="34%" cy="28%" r="78%">
          <stop offset="0%" stopColor="#bae6fd" />
          <stop offset="42%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#3b82f6" />
        </radialGradient>
        <marker
          id="arrowhead"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="9"
          markerHeight="9"
          markerUnits="userSpaceOnUse"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" className="edge-head" />
        </marker>
      </defs>

      <g className="edges">
        {/* the coach fans out to whichever tool is valid this turn */}
        <path d="M404,82 V94 Q404,106 392,106 H182 Q170,106 170,118 V146" markerEnd="url(#arrowhead)" />
        <path d="M404,82 V146" markerEnd="url(#arrowhead)" />
        <path d="M404,82 V94 Q404,106 416,106 H626 Q638,106 638,118 V146" markerEnd="url(#arrowhead)" />

        {/* a question and a hint both land in front of the learner */}
        <path d="M170,238 V278 Q170,290 182,290 H404" />
        <path d="M404,238 V312" markerEnd="url(#arrowhead)" />

        {/* grading hands control straight back to the coach, down the right lane */}
        <path
          d="M638,238 V250 Q638,262 650,262 H766 Q778,262 778,250 V63 Q778,51 766,51 H502"
          markerEnd="url(#arrowhead)"
        />

        {/* the learner's reply resumes the paused graph, up the left lane */}
        <path d="M314,346 H34 Q22,346 22,334 V63 Q22,51 34,51 H306" markerEnd="url(#arrowhead)" />
      </g>

      {/* the dashed container, with its label breaking the top border */}
      <rect className="group-box" x="52" y="126" width="696" height="124" rx="16" />
      <g className="edge-labels">
        <rect x="216" y="119" width="142" height="15" rx="7" />
        <text x="287" y="131">tools for this phase</text>
        <text x="521" y="99">calls exactly one tool</text>
        <text x="788" y="156" transform="rotate(-90 788 156)">
          returns a grade
        </text>
        <text x="10" y="200" transform="rotate(-90 10 200)">
          interrupt · resume
        </text>
      </g>

      {/* ---- coach ---- */}
      <g className="node">
        <rect x="314" y="20" width="180" height="62" rx="14" />
        <Orb cx={344} cy={51} r={12} />
        <text className="node-title" x="366" y="46">
          Agentic coach
        </text>
        <text className="node-sub" x="366" y="65">
          orchestrator
        </text>
      </g>

      {/* ---- tools ---- */}
      <g role="tablist" aria-label="Tools the coach can call">
        {nodes.map((node, index) => {
          const x = COLUMN[index];
          const isOn = index === selected;
          return (
            <g
              key={node.id}
              ref={(element) => {
                tabs.current[index] = element;
              }}
              className={`node tool${isOn ? " is-selected" : ""}`}
              role="tab"
              id={`tab-${node.id}`}
              aria-selected={isOn}
              aria-controls="tool-detail"
              tabIndex={isOn ? 0 : -1}
              onClick={() => onSelect(index)}
              onKeyDown={onKeyDown}
            >
              <title>{`${node.label} — ${node.blurb}`}</title>
              <rect x={x} y={NODE_TOP} width={NODE_W} height={NODE_H} rx="14" />
              {node.agent ? (
                <Orb cx={x + 27} cy={NODE_TOP + 43} r={11} />
              ) : (
                <g className="glyph">
                  <rect x={x + 16} y={NODE_TOP + 33} width="22" height="22" rx="6" />
                  <text x={x + 27} y={NODE_TOP + 48}>
                    {"{}"}
                  </text>
                </g>
              )}
              <text className="node-title" x={x + 46} y={NODE_TOP + 39}>
                {node.label}
              </text>
              <text className="node-sub" x={x + 46} y={NODE_TOP + 59}>
                {node.blurb}
              </text>
            </g>
          );
        })}
      </g>

      {/* ---- learner ---- */}
      <g className="node">
        <rect x="314" y="318" width="180" height="56" rx="14" />
        <text className="node-title" x={CENTRE[1]} y="343" textAnchor="middle">
          You
        </text>
        <text className="node-sub" x={CENTRE[1]} y="361" textAnchor="middle">
          the graph pauses and saves
        </text>
      </g>
    </svg>
  );
}

/** A small glossy sphere: the same read as the hero orb, at glyph size. */
function Orb({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g className="orb">
      <circle cx={cx} cy={cy} r={r + 3} className="orb-glow" />
      <circle cx={cx} cy={cy} r={r} fill="url(#orbFill)" />
      {/* Offset highlight: what makes a flat circle read as a lit sphere. */}
      <ellipse
        cx={cx - r * 0.3}
        cy={cy - r * 0.4}
        rx={r * 0.34}
        ry={r * 0.24}
        className="orb-spec"
      />
    </g>
  );
}
