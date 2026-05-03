"use client";

import Link from "next/link";
import { use } from "react";

import { CaseFlowGraph } from "@/components/case-flow-graph";
import { Button } from "@/components/ui/button";

export default function DocumentFlowPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <div className="flex flex-col gap-4 py-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Case flow graph</h1>
        <Button asChild variant="outline" size="sm">
          <Link href={`/document-summary?document_id=${encodeURIComponent(id)}`}>Back to summary</Link>
        </Button>
      </div>
      <CaseFlowGraph documentId={id} />
    </div>
  );
}

