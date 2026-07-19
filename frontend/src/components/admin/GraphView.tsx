/**
 * Admin · People graph. d3-force layout over silver.persons +
 * person_connections, enriched with live venture nodes and membership edges.
 * The simulation seeds from deterministic index angles, cools with
 * alphaDecay 0.05 and STOPS at alphaMin 0.02 (drag reheats briefly, then
 * stops again) — no perpetual CPU. Click a node for the provenance panel.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
} from "d3-force";
import { getDB, useLiveVersion } from "./data";
import {
  GRAPH_H,
  GRAPH_W,
  buildGraphModel,
  nodeHitRadius,
  type GraphEdge,
  type GraphNode,
} from "./graph";
import { DetailPanel, type GraphSelection } from "./DetailPanel";

interface DragState {
  id: string;
  pointerId: number;
  startX: number;
  startY: number;
  dragging: boolean;
}

export function GraphView() {
  const version = useLiveVersion();
  const db = getDB();

  // Rebuild (and re-layout) only when the venture/team topology changes,
  // not on every store mutation (outreach status etc.).
  const topology = useMemo(
    () =>
      db.ventures
        .map(
          (v) =>
            `${v.venture_id}:${(db.team[v.venture_id] ?? []).map((m) => m.person_id).join(",")}`,
        )
        .join("|"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [version],
  );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const model = useMemo(() => buildGraphModel(getDB()), [topology]);
  const nodeById = useMemo(() => new Map(model.nodes.map((n) => [n.id, n])), [model]);

  const svgRef = useRef<SVGSVGElement | null>(null);
  const simRef = useRef<Simulation<GraphNode, GraphEdge> | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const [, setFrame] = useState(0);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [selection, setSelection] = useState<GraphSelection>(null);

  useEffect(() => {
    const sim = forceSimulation<GraphNode>(model.nodes)
      .force(
        "link",
        forceLink<GraphNode, GraphEdge>(model.edges)
          .id((d) => d.id)
          .distance((e) => (e.kind === "membership" ? 95 : 135))
          .strength(0.5),
      )
      .force("charge", forceManyBody<GraphNode>().strength(-340))
      .force("center", forceCenter<GraphNode>(GRAPH_W / 2, GRAPH_H / 2))
      .force("collide", forceCollide<GraphNode>().radius((d) => nodeHitRadius(d) + 24))
      .alphaDecay(0.05)
      .alphaMin(0.02) // d3 halts its timer below this — the sim settles and stops
      .on("tick", () => setFrame((f) => f + 1));
    simRef.current = sim;
    return () => {
      sim.stop();
      simRef.current = null;
    };
  }, [model]);

  function toSvgPoint(clientX: number, clientY: number): { x: number; y: number } {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return { x: 0, y: 0 };
    const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }

  function select(node: GraphNode) {
    setSelection({ kind: node.kind, id: node.id });
  }

  function handlePointerDown(e: React.PointerEvent<SVGGElement>, node: GraphNode) {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = {
      id: node.id,
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      dragging: false,
    };
  }

  function handlePointerMove(e: React.PointerEvent<SVGGElement>, node: GraphNode) {
    const drag = dragRef.current;
    if (!drag || drag.id !== node.id || e.pointerId !== drag.pointerId) return;
    if (!drag.dragging) {
      if (Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 3) return;
      drag.dragging = true;
      simRef.current?.alphaTarget(0.15).restart(); // brief reheat while dragging
    }
    const p = toSvgPoint(e.clientX, e.clientY);
    node.fx = p.x;
    node.fy = p.y;
    setFrame((f) => f + 1);
  }

  function handlePointerUp(e: React.PointerEvent<SVGGElement>, node: GraphNode) {
    const drag = dragRef.current;
    if (!drag || drag.id !== node.id || e.pointerId !== drag.pointerId) return;
    dragRef.current = null;
    if (drag.dragging) {
      node.fx = null;
      node.fy = null;
      simRef.current?.alphaTarget(0); // alpha decays below alphaMin → auto-stop
    } else {
      select(node);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<SVGGElement>, node: GraphNode) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      select(node);
    }
  }

  const hoverNeighbors = hoveredId ? (model.neighbors.get(hoveredId) ?? new Set<string>()) : null;

  return (
    <div className="mt-8 flex h-[640px] animate-fade-up overflow-hidden rounded-none border border-line bg-paper">
      <div data-demo-id="admin-graph" className="relative min-w-0 flex-1">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${GRAPH_W} ${GRAPH_H}`}
          className="block h-full w-full select-none"
          style={{ touchAction: "none" }}
          role="group"
          aria-label="People and venture graph"
        >
          {/* edges */}
          <g>
            {model.edges.map((edge) => {
              const s = nodeById.get(edge.sourceId);
              const t = nodeById.get(edge.targetId);
              if (!s || !t) return null;
              const active =
                hoveredId != null && (edge.sourceId === hoveredId || edge.targetId === hoveredId);
              const isMembership = edge.kind === "membership";
              return (
                <line
                  key={edge.id}
                  x1={s.x ?? 0}
                  y1={s.y ?? 0}
                  x2={t.x ?? 0}
                  y2={t.y ?? 0}
                  stroke={
                    isMembership
                      ? active
                        ? "var(--line-strong)"
                        : "var(--line)"
                      : active
                        ? "var(--ink)"
                        : "var(--line-strong)"
                  }
                  strokeWidth={isMembership ? 1 : Math.min(4, 1 + edge.weight)}
                  strokeDasharray={isMembership ? "3 5" : undefined}
                >
                  <title>{edge.label}</title>
                </line>
              );
            })}
          </g>

          {/* nodes */}
          <g>
            {model.nodes.map((node) => {
              const x = node.x ?? 0;
              const y = node.y ?? 0;
              const isSelected = selection?.id === node.id;
              const isHovered = hoveredId === node.id;
              const isNeighbor = hoverNeighbors?.has(node.id) ?? false;
              const isFocused = focusedId === node.id;
              const emphasized = isHovered || isSelected || isNeighbor;
              return (
                <g
                  key={node.id}
                  data-demo-id={`admin-node-${node.id}`}
                  transform={`translate(${x},${y})`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${node.kind === "person" ? "Person" : "Venture"}: ${node.name}`}
                  aria-pressed={isSelected}
                  className="cursor-pointer"
                  style={{ outline: "none" }}
                  onPointerDown={(e) => handlePointerDown(e, node)}
                  onPointerMove={(e) => handlePointerMove(e, node)}
                  onPointerUp={(e) => handlePointerUp(e, node)}
                  onPointerEnter={() => setHoveredId(node.id)}
                  onPointerLeave={() => setHoveredId(null)}
                  onFocus={() => setFocusedId(node.id)}
                  onBlur={() => setFocusedId(null)}
                  onKeyDown={(e) => handleKeyDown(e, node)}
                >
                  {node.kind === "person" ? (
                    <>
                      {isSelected && (
                        <circle
                          r={node.r + 4}
                          fill="none"
                          stroke="var(--electric)"
                          strokeWidth={1.5}
                        />
                      )}
                      {isFocused && !isSelected && (
                        <circle
                          r={node.r + 6}
                          fill="none"
                          stroke="var(--line-strong)"
                          strokeWidth={1}
                          strokeDasharray="2 3"
                        />
                      )}
                      <circle r={node.r} fill="var(--ink)" fillOpacity={emphasized ? 1 : 0.85} />
                      <text
                        textAnchor="middle"
                        dy="0.35em"
                        className="pointer-events-none font-mono"
                        fill="var(--paper)"
                        fontSize={node.r * 0.72}
                      >
                        {node.initials}
                      </text>
                      <text
                        textAnchor="middle"
                        y={node.r + 14}
                        className="pointer-events-none font-mono"
                        fill={emphasized ? "var(--ink)" : "var(--quiet)"}
                        stroke="var(--paper)"
                        strokeWidth={3}
                        paintOrder="stroke"
                        fontSize={10}
                      >
                        {node.name}
                      </text>
                    </>
                  ) : (
                    <>
                      {isSelected && (
                        <rect
                          x={-node.half - 4}
                          y={-node.half - 4}
                          width={node.half * 2 + 8}
                          height={node.half * 2 + 8}
                          fill="none"
                          stroke="var(--electric)"
                          strokeWidth={1.5}
                        />
                      )}
                      {isFocused && !isSelected && (
                        <rect
                          x={-node.half - 6}
                          y={-node.half - 6}
                          width={node.half * 2 + 12}
                          height={node.half * 2 + 12}
                          fill="none"
                          stroke="var(--line-strong)"
                          strokeWidth={1}
                          strokeDasharray="2 3"
                        />
                      )}
                      <rect
                        x={-node.half}
                        y={-node.half}
                        width={node.half * 2}
                        height={node.half * 2}
                        fill="var(--paper)"
                        stroke={emphasized ? "var(--ink)" : "var(--line-strong)"}
                        strokeWidth={1}
                      />
                      <text
                        textAnchor="middle"
                        dy="0.35em"
                        className="pointer-events-none font-mono"
                        fill="var(--ink)"
                        fontSize={11}
                      >
                        {node.name.slice(0, 1).toUpperCase()}
                      </text>
                      <text
                        textAnchor="middle"
                        y={node.half + 15}
                        className="pointer-events-none font-mono uppercase"
                        fill={emphasized ? "var(--ink)" : "var(--quiet)"}
                        stroke="var(--paper)"
                        strokeWidth={3}
                        paintOrder="stroke"
                        fontSize={10}
                        letterSpacing="0.06em"
                      >
                        {node.name}
                      </text>
                    </>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        <p className="pointer-events-none absolute bottom-3 left-4 font-mono text-[11px] text-quiet">
          ● person · ■ venture · — connection · ┄ membership · drag to reposition, click for
          provenance
        </p>
      </div>
      <DetailPanel
        selection={selection}
        version={version}
        onSelectPerson={(id) => setSelection({ kind: "person", id })}
      />
    </div>
  );
}
