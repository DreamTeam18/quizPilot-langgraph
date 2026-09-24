"use client";

export type Inner =
  | { kind: "agent"; task: string; schema: string; note: string }
  | { kind: "plain"; task: string; note: string };

/**
 * What happens inside one tool call.
 *
 * The agent variant is a genuine cycle: the specialist can call read_notes and
 * come back, and if it answers with prose instead of a real tool call it gets
 * one corrective turn before the call fails. The plain variant has no cycle at
 * all, which is the whole point of showing it next to the other two.
 */
export function InnerLoop({ inner }: { inner: Inner }) {
  return (
    <svg
      className="graph inner"
      viewBox="0 0 800 270"
      role="img"
      aria-label={
        inner.kind === "agent"
          ? `Inside the call: the task goes to the specialist, which may call read_notes and return, retries once if it answers with prose, and finishes by emitting a validated ${inner.schema}.`
          : "Inside the call: the stored question is read by plain Python and returned. No model runs and there is no loop."
      }
    >
      <defs>
        <radialGradient id="innerOrb" cx="34%" cy="28%" r="78%">
          <stop offset="0%" stopColor="#bae6fd" />
          <stop offset="42%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#3b82f6" />
        </radialGradient>
        <marker
          id="innerArrow"
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

      {/* ---- the injected task, identical in both variants ---- */}
      <g className="node chip-node">
        <rect x="6" y="103" width="180" height="58" rx="10" />
        <text className="node-kicker" x="96" y="125">
          injected
        </text>
        <text className="node-fields" x="96" y="145">
          {inner.task}
        </text>
      </g>

      {inner.kind === "agent" ? (
        <>
          <g className="edges">
            <path d="M186,133 H226" markerEnd="url(#innerArrow)" />
            <path d="M302,99 V72" markerEnd="url(#innerArrow)" />
            <path d="M350,66 V93" markerEnd="url(#innerArrow)" />
            <path d="M416,133 H476" markerEnd="url(#innerArrow)" />
            <path d="M682,133 H772" markerEnd="url(#innerArrow)" />
            {/* the corrective turn, looping back into the specialist */}
            <path
              d="M326,167 V202 Q326,214 314,214 H208 Q196,214 196,202 V145 Q196,133 208,133 H232"
              className="retry"
              markerEnd="url(#innerArrow)"
            />
          </g>

          <g className="edge-labels">
            <text className="to-left" x="288" y="86">
              calls
            </text>
            <text className="to-right" x="364" y="86">
              returns
            </text>
            <text x="446" y="123">emits</text>
            <text x="727" y="123">to the graph</text>
            <text x="326" y="236">no tool call · one retry</text>
          </g>

          <g className="node">
            <rect x="246" y="12" width="160" height="54" rx="12" />
            <text className="node-mono" x="326" y="34" textAnchor="middle">
              read_notes
            </text>
            <text className="node-sub" x="326" y="52" textAnchor="middle">
              lesson notes
            </text>
          </g>

          <g className="node">
            <rect x="236" y="99" width="180" height="68" rx="14" />
            <Orb cx={266} cy={133} r={12} />
            <text className="node-title" x="288" y="128">
              specialist
            </text>
            <text className="node-sub" x="288" y="148">
              fresh conversation
            </text>
          </g>

          <g className="node">
            <rect x="486" y="99" width="196" height="68" rx="14" />
            <text className="node-mono" x="584" y="127" textAnchor="middle">
              {inner.schema}
            </text>
            <text className="node-sub" x="584" y="148" textAnchor="middle">
              {inner.note}
            </text>
          </g>
        </>
      ) : (
        <>
          <g className="edges">
            <path d="M186,133 H276" markerEnd="url(#innerArrow)" />
            <path d="M506,133 H772" markerEnd="url(#innerArrow)" />
          </g>

          <g className="edge-labels">
            <text x="639" y="123">to the graph</text>
            <text x="396" y="206">no model, no loop</text>
          </g>

          <g className="node">
            <rect x="286" y="99" width="220" height="68" rx="14" />
            <g className="glyph">
              <rect x="306" y="122" width="22" height="22" rx="6" />
              <text x="317" y="137">{"{}"}</text>
            </g>
            <text className="node-mono" x="340" y="128">
              question.hint
            </text>
            <text className="node-sub" x="340" y="148">
              {inner.note}
            </text>
          </g>
        </>
      )}
    </svg>
  );
}

function Orb({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g className="orb">
      <circle cx={cx} cy={cy} r={r + 3} className="orb-glow" />
      <circle cx={cx} cy={cy} r={r} fill="url(#innerOrb)" />
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
