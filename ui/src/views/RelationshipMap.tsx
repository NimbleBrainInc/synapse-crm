import { useEffect, useRef, useState, useCallback } from "react";
import type { Contact } from "../hooks/useContacts";
import type { Deal } from "../hooks/useDeals";
import { STAGE_COLORS, STAGE_LABELS } from "../hooks/useDeals";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GraphNode {
  id: string;
  label: string;
  sublabel?: string;
  type: "contact" | "deal";
  stage?: string;
  color: string;
  radius: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface GraphEdge {
  source: string;
  target: string;
  label: string;
}

// ---------------------------------------------------------------------------
// Layout types & algorithms
// ---------------------------------------------------------------------------

type LayoutType = "force" | "circular" | "pipeline" | "cluster";

const LAYOUT_LABELS: Record<LayoutType, string> = {
  force: "Force",
  circular: "Circular",
  pipeline: "Pipeline",
  cluster: "Cluster",
};

const WORLD_SIZE = 2000;

function layoutForce(nodes: GraphNode[], edges: GraphEdge[]) {
  const cx = WORLD_SIZE / 2;
  const cy = WORLD_SIZE / 2;
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    const r = Math.min(nodes.length * 20, WORLD_SIZE * 0.35);
    n.x = cx + r * Math.cos(angle);
    n.y = cy + r * Math.sin(angle);
    n.vx = 0;
    n.vy = 0;
  });

  for (let iter = 0; iter < 150; iter++) {
    const alpha = 1 - iter / 150;
    const strength = alpha * 0.3;

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const minDist = (a.radius + b.radius) * 4;
        const force = ((minDist * minDist) / (dist * dist)) * strength * 2;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx -= fx; a.vy -= fy;
        b.vx += fx; b.vy += fy;
      }
    }

    for (const edge of edges) {
      const a = nodeMap.get(edge.source);
      const b = nodeMap.get(edge.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = ((dist - 160) / dist) * strength * 0.5;
      a.vx += dx * force; a.vy += dy * force;
      b.vx -= dx * force; b.vy -= dy * force;
    }

    for (const n of nodes) {
      n.vx += (cx - n.x) * strength * 0.04;
      n.vy += (cy - n.y) * strength * 0.04;
      n.vx *= 0.6; n.vy *= 0.6;
      n.x += n.vx; n.y += n.vy;
      const pad = n.radius + 20;
      n.x = Math.max(pad, Math.min(WORLD_SIZE - pad, n.x));
      n.y = Math.max(pad, Math.min(WORLD_SIZE - pad, n.y));
    }
  }
}

function layoutCircular(nodes: GraphNode[], edges: GraphEdge[]) {
  const cx = WORLD_SIZE / 2;
  const cy = WORLD_SIZE / 2;
  const contactNodes = nodes.filter((n) => n.type === "contact");
  const dealNodes = nodes.filter((n) => n.type === "deal");
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // Contacts in an outer ring
  const outerR = Math.min(contactNodes.length * 25, WORLD_SIZE * 0.38);
  contactNodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / contactNodes.length - Math.PI / 2;
    n.x = cx + outerR * Math.cos(angle);
    n.y = cy + outerR * Math.sin(angle);
  });

  // Deals positioned near their linked contact, slightly inward
  const innerR = outerR * 0.55;
  const dealsByContact = new Map<string, GraphNode[]>();
  for (const edge of edges) {
    if (edge.label === "belongs_to") {
      if (!dealsByContact.has(edge.target)) dealsByContact.set(edge.target, []);
      const dealNode = nodeMap.get(edge.source);
      if (dealNode) dealsByContact.get(edge.target)!.push(dealNode);
    }
  }

  // Place linked deals near their contact
  const placed = new Set<string>();
  for (const contact of contactNodes) {
    const linkedDeals = dealsByContact.get(contact.id) || [];
    const contactAngle = Math.atan2(contact.y - cy, contact.x - cx);
    linkedDeals.forEach((deal, i) => {
      const spread = 0.15 * (i - (linkedDeals.length - 1) / 2);
      const angle = contactAngle + spread;
      deal.x = cx + innerR * Math.cos(angle);
      deal.y = cy + innerR * Math.sin(angle);
      placed.add(deal.id);
    });
  }

  // Unlinked deals in center
  let unlinkedIdx = 0;
  for (const deal of dealNodes) {
    if (placed.has(deal.id)) continue;
    const angle = (2 * Math.PI * unlinkedIdx) / Math.max(1, dealNodes.length - placed.size);
    deal.x = cx + 80 * Math.cos(angle);
    deal.y = cy + 80 * Math.sin(angle);
    unlinkedIdx++;
  }
}

const PIPELINE_STAGES = ["lead", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"];

function layoutPipeline(nodes: GraphNode[], edges: GraphEdge[]) {
  const contactNodes = nodes.filter((n) => n.type === "contact");
  const dealNodes = nodes.filter((n) => n.type === "deal");
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // Build contact -> deals mapping
  const contactDeals = new Map<string, Set<string>>();
  for (const edge of edges) {
    if (edge.label === "belongs_to") {
      if (!contactDeals.has(edge.target)) contactDeals.set(edge.target, new Set());
      contactDeals.get(edge.target)!.add(edge.source);
    }
  }

  // Group deals by stage
  const dealsByStage = new Map<string, GraphNode[]>();
  for (const stage of PIPELINE_STAGES) dealsByStage.set(stage, []);
  for (const deal of dealNodes) {
    const stage = deal.stage || "lead";
    if (dealsByStage.has(stage)) dealsByStage.get(stage)!.push(deal);
    else dealsByStage.get("lead")!.push(deal);
  }

  // Place deals in columns by stage
  const colWidth = WORLD_SIZE / (PIPELINE_STAGES.length + 1);
  const topMargin = 200;
  for (let col = 0; col < PIPELINE_STAGES.length; col++) {
    const stage = PIPELINE_STAGES[col];
    const stageDeals = dealsByStage.get(stage) || [];
    const x = colWidth * (col + 0.8);
    stageDeals.forEach((deal, row) => {
      deal.x = x;
      deal.y = topMargin + row * 90;
    });
  }

  // Place contacts below their deals (average x of their deals)
  const maxDealY = Math.max(...dealNodes.map((d) => d.y), topMargin);
  const contactY = maxDealY + 180;
  let contactIdx = 0;
  for (const contact of contactNodes) {
    const dealIds = contactDeals.get(contact.id);
    if (dealIds && dealIds.size > 0) {
      const linkedDeals = [...dealIds].map((id) => nodeMap.get(id)).filter(Boolean) as GraphNode[];
      const avgX = linkedDeals.reduce((s, d) => s + d.x, 0) / linkedDeals.length;
      contact.x = avgX;
      contact.y = contactY + (contactIdx % 2) * 70;
    } else {
      contact.x = 100 + contactIdx * 80;
      contact.y = contactY + 140;
    }
    contactIdx++;
  }

  // Resolve contact overlaps with simple spreading
  contactNodes.sort((a, b) => a.x - b.x);
  for (let i = 1; i < contactNodes.length; i++) {
    const prev = contactNodes[i - 1];
    const curr = contactNodes[i];
    const minGap = (prev.radius + curr.radius) * 2.2;
    if (curr.x - prev.x < minGap) {
      curr.x = prev.x + minGap;
    }
  }
}

function layoutCluster(nodes: GraphNode[], edges: GraphEdge[]) {
  const contactNodes = nodes.filter((n) => n.type === "contact");
  const dealNodes = nodes.filter((n) => n.type === "deal");
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const cx = WORLD_SIZE / 2;
  const cy = WORLD_SIZE / 2;

  // Build contact -> deals
  const contactDeals = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.label === "belongs_to") {
      if (!contactDeals.has(edge.target)) contactDeals.set(edge.target, []);
      contactDeals.get(edge.target)!.push(edge.source);
    }
  }

  // Each contact is a cluster center; place contacts in a large ring
  const clusterR = Math.min(contactNodes.length * 30, WORLD_SIZE * 0.38);
  contactNodes.forEach((contact, i) => {
    const angle = (2 * Math.PI * i) / contactNodes.length - Math.PI / 2;
    contact.x = cx + clusterR * Math.cos(angle);
    contact.y = cy + clusterR * Math.sin(angle);

    // Place deals around their contact
    const dealIds = contactDeals.get(contact.id) || [];
    dealIds.forEach((dealId, j) => {
      const deal = nodeMap.get(dealId);
      if (!deal) return;
      const subAngle = angle + 0.3 * (j - (dealIds.length - 1) / 2);
      const subR = 70 + j * 15;
      deal.x = contact.x + subR * Math.cos(subAngle);
      deal.y = contact.y + subR * Math.sin(subAngle);
    });
  });

  // Place unlinked deals in center
  const placed = new Set(
    [...contactDeals.values()].flat()
  );
  let idx = 0;
  for (const deal of dealNodes) {
    if (placed.has(deal.id)) continue;
    const angle = (2 * Math.PI * idx) / Math.max(1, dealNodes.length - placed.size);
    deal.x = cx + 60 * Math.cos(angle);
    deal.y = cy + 60 * Math.sin(angle);
    idx++;
  }
}

function applyLayout(layout: LayoutType, nodes: GraphNode[], edges: GraphEdge[]) {
  switch (layout) {
    case "force": layoutForce(nodes, edges); break;
    case "circular": layoutCircular(nodes, edges); break;
    case "pipeline": layoutPipeline(nodes, edges); break;
    case "cluster": layoutCluster(nodes, edges); break;
  }
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

// ---------------------------------------------------------------------------
// Arrow geometry helper
// ---------------------------------------------------------------------------

function arrowEdge(
  sx: number, sy: number, sr: number,
  tx: number, ty: number, tr: number,
  isRect: boolean,
): { x1: number; y1: number; x2: number; y2: number } {
  const dx = tx - sx;
  const dy = ty - sy;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  const ux = dx / dist;
  const uy = dy / dist;

  // Source offset (always circle for deal source)
  const sourceR = sr + 4;
  const x1 = sx + ux * sourceR;
  const y1 = sy + uy * sourceR;

  // Target offset — contact is circle, deal is rect
  let targetR: number;
  if (!isRect) {
    targetR = tr + 8;
  } else {
    // Approximate distance to edge of rounded rect
    const hw = tr * 1.4;
    const hh = tr;
    const ax = Math.abs(ux);
    const ay = Math.abs(uy);
    targetR = ax > 0.001 ? Math.min(hw / ax, hh / ay) : hh / ay;
    targetR = Math.min(targetR, Math.max(hw, hh)) + 8;
  }
  const x2 = tx - ux * targetR;
  const y2 = ty - uy * targetR;

  return { x1, y1, x2, y2 };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RelationshipMap({
  contacts,
  deals,
  isDark,
  onContactClick,
  onDealClick,
}: {
  contacts: Contact[];
  deals: Deal[];
  isDark: boolean;
  onContactClick: (contact: Contact) => void;
  onDealClick: (deal: Deal) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [viewSize, setViewSize] = useState({ width: 800, height: 600 });
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [layout, setLayout] = useState<LayoutType>("force");

  // Pan/zoom state
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  // Drag node state
  const [dragNode, setDragNode] = useState<string | null>(null);
  const dragMoved = useRef(false);

  // Measure container
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) setViewSize({ width, height });
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Build graph
  useEffect(() => {
    const activeContacts = contacts.filter((c) => c.status === "active");
    const activeDeals = deals.filter((d) => d.status === "active");
    const contactColor = isDark ? "#60a5fa" : "#2563eb";

    const graphNodes: GraphNode[] = [
      ...activeContacts.map((c) => ({
        id: c.id,
        label: c.name,
        sublabel: c.company || c.role || "",
        type: "contact" as const,
        color: contactColor,
        radius: 30,
        x: 0, y: 0, vx: 0, vy: 0,
      })),
      ...activeDeals.map((d) => ({
        id: d.id,
        label: d.title.length > 28 ? d.title.slice(0, 25) + "..." : d.title,
        sublabel: d.value ? formatCurrency(d.value) : (STAGE_LABELS[d.stage] || d.stage),
        type: "deal" as const,
        stage: d.stage,
        color: STAGE_COLORS[d.stage] || "#6B7280",
        radius: 24,
        x: 0, y: 0, vx: 0, vy: 0,
      })),
    ];

    const graphEdges: GraphEdge[] = [];
    const nodeIds = new Set(graphNodes.map((n) => n.id));

    // Deal -> Contact (belongs_to)
    for (const deal of activeDeals) {
      for (const rel of deal.relationships || []) {
        if (rel.rel === "belongs_to" && nodeIds.has(rel.target)) {
          graphEdges.push({ source: deal.id, target: rel.target, label: rel.rel });
        }
      }
    }

    // Contact -> Contact (referred, knows, former_colleague, etc.)
    for (const contact of activeContacts) {
      for (const rel of contact.relationships || []) {
        if (nodeIds.has(rel.target)) {
          graphEdges.push({ source: contact.id, target: rel.target, label: rel.rel });
        }
      }
    }

    if (graphNodes.length > 0) {
      applyLayout(layout, graphNodes, graphEdges);
      // Center the view on the graph
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const n of graphNodes) {
        minX = Math.min(minX, n.x - n.radius);
        minY = Math.min(minY, n.y - n.radius);
        maxX = Math.max(maxX, n.x + n.radius);
        maxY = Math.max(maxY, n.y + n.radius);
      }
      const gw = maxX - minX + 100;
      const gh = maxY - minY + 100;
      const fitZoom = Math.min(viewSize.width / gw, viewSize.height / gh, 1.5);
      const gcx = (minX + maxX) / 2;
      const gcy = (minY + maxY) / 2;
      setZoom(fitZoom);
      setPan({
        x: viewSize.width / 2 - gcx * fitZoom,
        y: viewSize.height / 2 - gcy * fitZoom,
      });
    }

    setNodes(graphNodes);
    setEdges(graphEdges);
  }, [contacts, deals, viewSize, isDark, layout]);

  // Wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const svg = containerRef.current?.querySelector("svg");
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const newZoom = Math.max(0.15, Math.min(5, zoom * factor));
    // Zoom toward mouse position
    setPan((p) => ({
      x: mx - ((mx - p.x) / zoom) * newZoom,
      y: my - ((my - p.y) / zoom) * newZoom,
    }));
    setZoom(newZoom);
  }, [zoom]);

  // Pan handlers (on background)
  const handleBgPointerDown = useCallback((e: React.PointerEvent) => {
    // Only pan on direct background click (not on nodes)
    if ((e.target as Element).closest("[data-node]")) return;
    setIsPanning(true);
    panStart.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
    (e.target as Element).setPointerCapture(e.pointerId);
  }, [pan]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (dragNode) {
      // Dragging a node — convert screen to world coords
      const svg = containerRef.current?.querySelector("svg");
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const worldX = (e.clientX - rect.left - pan.x) / zoom;
      const worldY = (e.clientY - rect.top - pan.y) / zoom;
      dragMoved.current = true;
      setNodes((prev) =>
        prev.map((n) => (n.id === dragNode ? { ...n, x: worldX, y: worldY } : n))
      );
      return;
    }
    if (!isPanning) return;
    const dx = e.clientX - panStart.current.x;
    const dy = e.clientY - panStart.current.y;
    setPan({ x: panStart.current.panX + dx, y: panStart.current.panY + dy });
  }, [isPanning, dragNode, pan, zoom]);

  const handlePointerUp = useCallback(() => {
    setIsPanning(false);
    setDragNode(null);
  }, []);

  // Node drag start
  const handleNodePointerDown = useCallback((nodeId: string, e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setDragNode(nodeId);
    dragMoved.current = false;
    (e.target as Element).setPointerCapture(e.pointerId);
  }, []);

  const handleNodeClick = useCallback(
    (nodeId: string) => {
      if (dragMoved.current) return;
      const contact = contacts.find((c) => c.id === nodeId);
      if (contact) { onContactClick(contact); return; }
      const deal = deals.find((d) => d.id === nodeId);
      if (deal) { onDealClick(deal); return; }
    },
    [contacts, deals, onContactClick, onDealClick],
  );

  // Zoom controls
  const zoomIn = () => {
    const nz = Math.min(5, zoom * 1.3);
    setPan((p) => ({
      x: viewSize.width / 2 - ((viewSize.width / 2 - p.x) / zoom) * nz,
      y: viewSize.height / 2 - ((viewSize.height / 2 - p.y) / zoom) * nz,
    }));
    setZoom(nz);
  };
  const zoomOut = () => {
    const nz = Math.max(0.15, zoom / 1.3);
    setPan((p) => ({
      x: viewSize.width / 2 - ((viewSize.width / 2 - p.x) / zoom) * nz,
      y: viewSize.height / 2 - ((viewSize.height / 2 - p.y) / zoom) * nz,
    }));
    setZoom(nz);
  };
  const resetView = () => {
    setZoom(1);
    setPan({ x: viewSize.width / 2 - WORLD_SIZE / 2, y: viewSize.height / 2 - WORLD_SIZE / 2 });
  };

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const bg = isDark ? "#1a1a2e" : "#f8f9fa";
  const edgeColor = isDark ? "#3d3d5c" : "#d1d5db";
  const highlightEdge = isDark ? "#8b8baf" : "#6b7280";
  const textColor = isDark ? "#e0e0e0" : "#1a1a2e";
  const mutedText = isDark ? "#888" : "#666";
  const arrowColor = isDark ? "#5a5a7a" : "#9ca3af";
  const arrowHighlight = isDark ? "#a0a0cc" : "#6b7280";
  const controlBg = isDark ? "#16162a" : "#ffffff";
  const controlBorder = isDark ? "#3d3d5c" : "#d1d5db";

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "calc(100vh - 140px)",
        background: bg,
        overflow: "hidden",
        position: "relative",
      }}
    >
      {nodes.length === 0 ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
            color: mutedText,
            fontSize: "0.9rem",
          }}
        >
          No contacts or deals to map. Add some data first.
        </div>
      ) : (
        <svg
          width={viewSize.width}
          height={viewSize.height}
          onWheel={handleWheel}
          onPointerDown={handleBgPointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          style={{
            cursor: isPanning ? "grabbing" : dragNode ? "grabbing" : "grab",
            touchAction: "none",
          }}
        >
          {/* Arrow marker defs */}
          <defs>
            <marker id="arrow" viewBox="0 0 10 6" refX="10" refY="3"
              markerWidth="10" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 3 L 0 6 Z" fill={arrowColor} />
            </marker>
            <marker id="arrow-highlight" viewBox="0 0 10 6" refX="10" refY="3"
              markerWidth="10" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 3 L 0 6 Z" fill={arrowHighlight} />
            </marker>
            <marker id="arrow-social" viewBox="0 0 10 6" refX="10" refY="3"
              markerWidth="10" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 3 L 0 6 Z" fill={isDark ? "#4ade80" : "#16a34a"} />
            </marker>
            <marker id="arrow-social-hl" viewBox="0 0 10 6" refX="10" refY="3"
              markerWidth="10" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 3 L 0 6 Z" fill={isDark ? "#86efac" : "#22c55e"} />
            </marker>
          </defs>

          {/* Transform group for pan/zoom */}
          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {/* Edges with arrows */}
            {edges.map((edge, i) => {
              const s = nodeMap.get(edge.source);
              const t = nodeMap.get(edge.target);
              if (!s || !t) return null;
              const isHighlighted =
                hoveredNode === edge.source || hoveredNode === edge.target;
              const isSocial = edge.label !== "belongs_to";
              const targetIsRect = t.type === "deal";
              const { x1, y1, x2, y2 } = arrowEdge(
                s.x, s.y, s.type === "deal" ? s.radius * 1.4 : s.radius,
                t.x, t.y, t.radius,
                targetIsRect,
              );
              const socialColor = isDark ? "#4ade80" : "#16a34a";
              const socialHl = isDark ? "#86efac" : "#22c55e";
              return (
                <line
                  key={i}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={
                    isSocial
                      ? (isHighlighted ? socialHl : socialColor)
                      : (isHighlighted ? highlightEdge : edgeColor)
                  }
                  strokeWidth={isHighlighted ? 2.5 : isSocial ? 1 : 1.2}
                  strokeDasharray={isSocial ? "6 3" : undefined}
                  strokeOpacity={isSocial && !isHighlighted ? 0.5 : 1}
                  markerEnd={
                    isSocial
                      ? (isHighlighted ? "url(#arrow-social-hl)" : "url(#arrow-social)")
                      : (isHighlighted ? "url(#arrow-highlight)" : "url(#arrow)")
                  }
                />
              );
            })}

            {/* Edge labels */}
            {edges.map((edge, i) => {
              const s = nodeMap.get(edge.source);
              const t = nodeMap.get(edge.target);
              if (!s || !t) return null;
              const isHighlighted =
                hoveredNode === edge.source || hoveredNode === edge.target;
              if (!isHighlighted) return null;
              const mx = (s.x + t.x) / 2;
              const my = (s.y + t.y) / 2;
              return (
                <text
                  key={`label-${i}`}
                  x={mx}
                  y={my - 6}
                  textAnchor="middle"
                  fill={mutedText}
                  fontSize="8"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {edge.label}
                </text>
              );
            })}

            {/* Nodes */}
            {nodes.map((node) => {
              const isHovered = hoveredNode === node.id;
              const isContact = node.type === "contact";
              const scale = isHovered ? 1.08 : 1;
              return (
                <g
                  key={node.id}
                  data-node="true"
                  transform={`translate(${node.x}, ${node.y}) scale(${scale})`}
                  onPointerDown={(e) => handleNodePointerDown(node.id, e)}
                  onClick={() => handleNodeClick(node.id)}
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  style={{ cursor: "pointer" }}
                >
                  {isContact ? (
                    <circle
                      r={node.radius}
                      fill={isDark ? `${node.color}25` : `${node.color}15`}
                      stroke={node.color}
                      strokeWidth={isHovered ? 2.5 : 1.5}
                    />
                  ) : (
                    <rect
                      x={-node.radius * 1.4}
                      y={-node.radius}
                      width={node.radius * 2.8}
                      height={node.radius * 2}
                      rx={8}
                      fill={isDark ? `${node.color}25` : `${node.color}12`}
                      stroke={node.color}
                      strokeWidth={isHovered ? 2.5 : 1.5}
                    />
                  )}

                  <text
                    textAnchor="middle"
                    dy={node.sublabel ? "-0.2em" : "0.35em"}
                    fill={textColor}
                    fontSize={isContact ? "11" : "10"}
                    fontWeight={isContact ? 700 : 600}
                    style={{ pointerEvents: "none", userSelect: "none" }}
                  >
                    {node.label}
                  </text>

                  {node.sublabel && (
                    <text
                      textAnchor="middle"
                      dy="1.1em"
                      fill={mutedText}
                      fontSize="9"
                      style={{ pointerEvents: "none", userSelect: "none" }}
                    >
                      {node.sublabel}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      )}

      {/* Layout selector */}
      {nodes.length > 0 && (
        <div
          style={{
            position: "absolute",
            top: "0.75rem",
            right: "0.75rem",
            display: "flex",
            gap: "2px",
            background: controlBg,
            border: `1px solid ${controlBorder}`,
            borderRadius: "8px",
            overflow: "hidden",
            boxShadow: isDark ? "0 2px 8px rgba(0,0,0,0.4)" : "0 2px 8px rgba(0,0,0,0.1)",
          }}
        >
          {(["force", "circular", "pipeline", "cluster"] as LayoutType[]).map((l) => (
            <button
              key={l}
              onClick={() => setLayout(l)}
              style={{
                padding: "0.35rem 0.65rem",
                border: "none",
                background: layout === l ? (isDark ? "#2d2d44" : "#e8e8f0") : "transparent",
                color: layout === l ? textColor : mutedText,
                fontSize: "0.7rem",
                fontWeight: layout === l ? 700 : 500,
                cursor: "pointer",
              }}
            >
              {LAYOUT_LABELS[l]}
            </button>
          ))}
        </div>
      )}

      {/* Zoom controls */}
      {nodes.length > 0 && (
        <div
          style={{
            position: "absolute",
            bottom: "1rem",
            right: "1rem",
            display: "flex",
            flexDirection: "column",
            gap: "2px",
            background: controlBg,
            border: `1px solid ${controlBorder}`,
            borderRadius: "8px",
            overflow: "hidden",
            boxShadow: isDark ? "0 2px 8px rgba(0,0,0,0.4)" : "0 2px 8px rgba(0,0,0,0.1)",
          }}
        >
          {[
            { label: "+", action: zoomIn },
            { label: "-", action: zoomOut },
            { label: "Fit", action: resetView },
          ].map((btn) => (
            <button
              key={btn.label}
              onClick={btn.action}
              style={{
                width: "36px",
                height: "32px",
                border: "none",
                background: "transparent",
                color: textColor,
                fontSize: btn.label === "Fit" ? "0.6rem" : "1.1rem",
                fontWeight: 600,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = isDark ? "#2d2d44" : "#f0f0f0";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "transparent";
              }}
            >
              {btn.label}
            </button>
          ))}
        </div>
      )}

      {/* Legend */}
      {nodes.length > 0 && (
        <div
          style={{
            position: "absolute",
            bottom: "1rem",
            left: "1rem",
            display: "flex",
            gap: "1rem",
            fontSize: "0.7rem",
            color: mutedText,
            background: controlBg,
            border: `1px solid ${controlBorder}`,
            borderRadius: "6px",
            padding: "0.4rem 0.75rem",
            boxShadow: isDark ? "0 2px 8px rgba(0,0,0,0.4)" : "0 2px 8px rgba(0,0,0,0.1)",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
            <svg width="12" height="12">
              <circle cx="6" cy="6" r="5" fill="none" stroke={isDark ? "#60a5fa" : "#2563eb"} strokeWidth="1.5" />
            </svg>
            Contact
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
            <svg width="14" height="12">
              <rect x="1" y="1" width="12" height="10" rx="3" fill="none" stroke="#6B7280" strokeWidth="1.5" />
            </svg>
            Deal
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
            <svg width="16" height="12">
              <line x1="1" y1="6" x2="11" y2="6" stroke={arrowColor} strokeWidth="1.2" />
              <polygon points="11,3 16,6 11,9" fill={arrowColor} />
            </svg>
            Deal
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
            <svg width="16" height="12">
              <line x1="1" y1="6" x2="11" y2="6" stroke={isDark ? "#4ade80" : "#16a34a"} strokeWidth="1" strokeDasharray="4 2" />
              <polygon points="11,3 16,6 11,9" fill={isDark ? "#4ade80" : "#16a34a"} />
            </svg>
            Referral
          </span>
          <span style={{ color: isDark ? "#555" : "#aaa" }}>
            {Math.round(zoom * 100)}%
          </span>
        </div>
      )}
    </div>
  );
}
