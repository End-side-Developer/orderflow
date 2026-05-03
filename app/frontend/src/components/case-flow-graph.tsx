"use client";

import "@xyflow/react/dist/style.css";

import { useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { getDocumentCaseFlow, type CaseFlowData, type CaseFlowNode } from "@/lib/api/client";
import { cn } from "@/lib/utils";

interface CaseFlowGraphProps {
  documentId: string;
  currentPage?: number;
  onNodePageJump?: (page: number) => void;
  compact?: boolean;
}

type CaseNodeData = {
  label: string;
  detail: string | null;
  nodeType: CaseFlowNode["node_type"];
  pageRef: number | null;
  active: boolean;
};

const NODE_COLUMNS: Record<CaseFlowNode["node_type"], number> = {
  party: 0,
  event: 1,
  order: 2,
  obligation: 3,
};

const NODE_STYLE: Record<CaseFlowNode["node_type"], string> = {
  party: "border-blue-400/40 bg-blue-500/10",
  event: "border-slate-400/40 bg-slate-500/10",
  order: "border-amber-400/40 bg-amber-500/10",
  obligation: "border-red-400/40 bg-red-500/10",
};

function CaseNodeCard({ data }: NodeProps<Node<CaseNodeData>>) {
  return (
    <div
      className={cn(
        "min-w-[180px] max-w-[220px] rounded-md border px-3 py-2 shadow-sm transition-colors",
        NODE_STYLE[data.nodeType],
        data.active ? "ring-2 ring-primary" : "hover:bg-muted/20",
      )}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !bg-slate-500" />
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-semibold text-foreground">{data.label}</span>
        {data.pageRef != null ? (
          <Badge variant="outline" className="text-[10px]">
            p.{data.pageRef}
          </Badge>
        ) : null}
      </div>
      {data.detail ? (
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground line-clamp-3">
          {data.detail}
        </p>
      ) : null}
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !bg-slate-500" />
    </div>
  );
}

const nodeTypes: NodeTypes = {
  caseNode: CaseNodeCard,
};

function toFlowGraph(
  data: CaseFlowData,
  currentPage?: number,
  compact?: boolean,
): { nodes: Node<CaseNodeData>[]; edges: Edge[] } {
  const laneCounts: Record<CaseFlowNode["node_type"], number> = {
    party: 0,
    event: 0,
    order: 0,
    obligation: 0,
  };
  const xStep = compact ? 230 : 300;
  const yStep = compact ? 120 : 145;

  const nodes: Node<CaseNodeData>[] = data.nodes.map((node) => {
    const row = laneCounts[node.node_type]++;
    return {
      id: node.id,
      type: "caseNode",
      position: {
        x: NODE_COLUMNS[node.node_type] * xStep,
        y: row * yStep,
      },
      data: {
        label: node.label,
        detail: node.detail,
        nodeType: node.node_type,
        pageRef: node.page_ref,
        active: currentPage != null && node.page_ref === currentPage,
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      draggable: false,
      selectable: true,
    };
  });

  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges: Edge[] = data.edges
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.relation,
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, color: "#64748b" },
      style: { stroke: "#64748b", strokeWidth: 1.2 },
      labelStyle: { fontSize: 10, fill: "#475569", fontWeight: 600 },
      animated: edge.relation === "next",
    }));

  return { nodes, edges };
}

export function CaseFlowGraph({
  documentId,
  currentPage,
  onNodePageJump,
  compact = false,
}: CaseFlowGraphProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<CaseFlowData | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    (async () => {
      const result = await getDocumentCaseFlow(documentId);
      if (cancelled) return;
      if (result.ok) {
        setData(result.data);
      } else {
        setError(result.error.message);
      }
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const flowElements = useMemo(() => {
    if (!data) return null;
    return toFlowGraph(data, currentPage, compact);
  }, [compact, currentPage, data]);

  if (loading) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-muted-foreground">Building case flow...</CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-muted-foreground">
          Could not build case flow: {error}
        </CardContent>
      </Card>
    );
  }

  if (!data || data.nodes.length === 0 || !flowElements) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-muted-foreground">
          Not enough extracted case structure yet to render a flow.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <CardContent className={cn("p-0", compact ? "h-[420px]" : "h-[68vh] min-h-[560px]")}>
        <ReactFlow
          nodes={flowElements.nodes}
          edges={flowElements.edges}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.5}
          maxZoom={1.4}
          nodesConnectable={false}
          elementsSelectable
          onNodeClick={(_event, node) => {
            const page = node.data.pageRef;
            if (page != null) onNodePageJump?.(page);
          }}
        >
          <Background color="#d1d5db" gap={24} size={1} />
          <Controls showInteractive />
        </ReactFlow>
      </CardContent>
    </Card>
  );
}
