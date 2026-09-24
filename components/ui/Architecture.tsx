"use client";

import { useRef, useState } from "react";
import { ArchitectureGraph } from "./ArchitectureGraph";
import { InnerLoop, type Inner } from "./InnerLoop";

type Tool = {
  id: string;
  agent: boolean;
  label: string;
  blurb: string;
  inner: Inner;
};

// Ordered to match the graph's columns: grading sits on the right, where its
// edge can return to the coach without crossing anything.
const TOOLS: Tool[] = [
  {
    id: "generate_question",
    agent: true,
    label: "Question specialist agent",
    blurb: "writes the next question",
    inner: {
      kind: "agent",
      task: "topic · difficulty · focus",
      schema: "Question",
      note: "text, rubric, hint",
    },
  },
  {
    id: "give_hint",
    agent: false,
    label: "Prepared hint",
    blurb: "no model call",
    inner: { kind: "plain", task: "the current question", note: "plain Python" },
  },
  {
    id: "grade_answer",
    agent: true,
    label: "Grading specialist agent",
    blurb: "reads your answer",
    inner: {
      kind: "agent",
      task: "question · rubric · answer",
      schema: "Grade",
      note: "score, feedback, gaps",
    },
  },
];

export function Architecture() {
  const [selected, setSelected] = useState(0);
  const tabs = useRef<(SVGGElement | null)[]>([]);
  const tool = TOOLS[selected];

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const index = tabs.current.findIndex((node) => node === event.currentTarget);
      if (index >= 0) setSelected(index);
      return;
    }
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (selected + step + TOOLS.length) % TOOLS.length;
    setSelected(next);
    tabs.current[next]?.focus();
  }

  return (
    <section className="architecture" id="how-it-works" aria-labelledby="how-it-works-title">
      <header className="arch-head">
        <h2 id="how-it-works-title">Multi-Agent Orchestration</h2>
      </header>

      <div className="graph-scroll">
        <ArchitectureGraph
          nodes={TOOLS.map(({ id, agent, label, blurb }) => ({ id, agent, label, blurb }))}
          selected={selected}
          onSelect={setSelected}
          onKeyDown={onKeyDown}
          tabs={tabs}
        />
      </div>

      <p className="legend">
        <span className="legend-orb" aria-hidden /> agent
        <span className="legend-gap" />
        <span className="legend-glyph" aria-hidden /> plain Python
        <span className="legend-gap" />
        <strong>Pick a tool.</strong>
      </p>

      <div
        className="inner-panel"
        id="tool-detail"
        role="tabpanel"
        aria-labelledby={`tab-${tool.id}`}
        tabIndex={0}
      >
        <p className="inner-caption">
          inside <code>{tool.id}</code>
        </p>
        <div className="graph-scroll">
          <InnerLoop inner={tool.inner} />
        </div>
      </div>
    </section>
  );
}
