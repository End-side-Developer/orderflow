"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { ChevronLeft, ChevronRight, Loader2, Minus, Plus } from "lucide-react";

import { CachedPageExtractionSidebar } from "./cached-page-extraction-sidebar";
import { PdfOverlayLayer } from "./pdf-overlay-layer";
import { Button } from "@/components/ui/button";
import { downloadDocument, listPageSummaries, type PageSummaryRecord } from "@/lib/api/client";
import type { ExtractedPlace } from "./case-incidence-map";

const CaseIncidenceMap = dynamic(
  () => import("./case-incidence-map").then((mod) => mod.CaseIncidenceMap),
  {
    ssr: false,
    loading: () => (
      <div style={{ padding: "16px", color: "#94a3b8", fontSize: "13px" }}>
        Loading locations...
      </div>
    ),
  },
);

// Dynamic import of pdfjs-dist to avoid SSR issues
let pdfjsLib: typeof import("pdfjs-dist") | null = null;

async function getPdfJs() {
  if (!pdfjsLib) {
    pdfjsLib = await import("pdfjs-dist");
    pdfjsLib.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;
  }
  return pdfjsLib;
}

export interface Annotation {
  id: string;
  page_number: number;
  annotation_type: "highlight" | "note" | "obligation";
  text_content: string | null;
  bbox: { x: number; y: number; width: number; height: number } | null;
  color: string | null;
  tooltip_text: string | null;
}

export interface PdfTextItem {
  str: string;
  dir: string;
  width: number;
  height: number;
  transform: number[];
  fontName: string;
  hasEOL: boolean;
}

export interface PdfTextPosition {
  text: string;
  bbox: { x: number; y: number; width: number; height: number };
  page: number;
}

interface PdfViewerProps {
  documentId: string;
  onPageChange?: (pageNumber: number) => void;
  initialPage?: number;
  annotations?: Annotation[];
  onTextExtracted?: (positions: PdfTextPosition[]) => void;
  places?: ExtractedPlace[];
}

export function PdfViewer({
  documentId,
  onPageChange,
  initialPage = 1,
  annotations = [],
  onTextExtracted,
  places = [],
}: PdfViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pdf, setPdf] = useState<any>(null);
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [totalPages, setTotalPages] = useState(0);
  const [scale, setScale] = useState(1.0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageSummaries, setPageSummaries] = useState<PageSummaryRecord[]>([]);
  const [summariesLoading, setSummariesLoading] = useState(true);
  const [summariesError, setSummariesError] = useState<string | null>(null);

  useEffect(() => {
    setCurrentPage(initialPage);
  }, [documentId, initialPage]);

  const currentPageSummary = useMemo(
    () => pageSummaries.find((summary) => summary.page_number === currentPage) ?? null,
    [currentPage, pageSummaries],
  );

  const loadCachedPageSummaries = useCallback(async () => {
    setSummariesLoading(true);
    setSummariesError(null);

    try {
      const response = await listPageSummaries(documentId);
      if (response.ok) {
        setPageSummaries(response.data.items);
      } else {
        setPageSummaries([]);
        setSummariesError(response.error.message);
      }
    } catch (requestError) {
      setPageSummaries([]);
      setSummariesError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load cached page extractions.",
      );
    } finally {
      setSummariesLoading(false);
    }
  }, [documentId]);

  // Extract local text positions for deterministic highlight alignment only.
  async function extractAllTextPositions(pdfDoc: any) {
    const allPositions: PdfTextPosition[] = [];

    for (let pageNum = 1; pageNum <= pdfDoc.numPages; pageNum++) {
      const page = await pdfDoc.getPage(pageNum);
      const textContent = await page.getTextContent();
      const viewport = page.getViewport({ scale: 1.0 });

      // Process text items
      textContent.items.forEach((item: any) => {
        if (item.str && item.transform) {
          const transform = item.transform;

          // Calculate bbox from transform matrix
          // transform[4] = x, transform[5] = y
          const x = transform[4];
          const y = viewport.height - transform[5]; // Flip Y coordinate
          const width = item.width || 0;
          const height = item.height || 0;

          allPositions.push({
            text: String(item.str).trim(),
            bbox: { x, y, width, height },
            page: pageNum,
          });
        }
      });
    }

    onTextExtracted?.(allPositions);
    return allPositions;
  }

  // Load PDF document
  useEffect(() => {
    async function loadPdf() {
      try {
        setLoading(true);
        setError(null);

        const [downloadResult] = await Promise.all([
          downloadDocument(documentId),
          loadCachedPageSummaries(),
        ]);

        const arrayBuffer = await downloadResult.blob.arrayBuffer();
        const pdfjs = await getPdfJs();
        if (!pdfjs) throw new Error("Failed to load PDF library");
        const loadingTask = pdfjs.getDocument({ data: arrayBuffer });
        const pdfDocument = await loadingTask.promise;

        setPdf(pdfDocument);
        setTotalPages(pdfDocument.numPages);

        // Extract text positions from all pages
        await extractAllTextPositions(pdfDocument);

        setLoading(false);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setError(message);
        setLoading(false);
      }
    }

    loadPdf();
    // extractAllTextPositions is stable across renders for this component;
    // depending on documentId is the intended trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, loadCachedPageSummaries]);

  // Render current page
  useEffect(() => {
    async function renderPage() {
      if (loading || !pdf || !canvasRef.current) return;

      try {
        const page = await pdf.getPage(currentPage);
        const canvas = canvasRef.current;
        const context = canvas.getContext("2d");

        if (!context) return;

        const viewport = page.getViewport({ scale });
        canvas.height = viewport.height;
        canvas.width = viewport.width;

        const renderContext = {
          canvasContext: context,
          viewport: viewport,
          canvas: canvas,
        };

        await page.render(renderContext).promise;
      } catch (err) {
        console.error("Error rendering page:", err);
      }
    }

    void renderPage();
  }, [loading, pdf, currentPage, scale]);

  // Handle page change
  function handlePageChange(newPage: number) {
    if (newPage < 1 || newPage > totalPages) return;
    setCurrentPage(newPage);
    onPageChange?.(newPage);
  }

  // Handle zoom
  function handleZoom(direction: "in" | "out") {
    const newScale = direction === "in" ? scale + 0.25 : scale - 0.25;
    if (newScale >= 0.5 && newScale <= 5.0) {
      setScale(newScale);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-full items-center justify-center p-8">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="animate-spin" />
          Loading PDF
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-full items-center justify-center p-8">
        <div className="max-w-md rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Error: {error}
        </div>
      </div>
    );
  }

  const currentPageHasPlaces = places.some((place) => {
    return (
      place.source_page_number === currentPage &&
      typeof place.lat === "number" &&
      typeof place.lng === "number"
    );
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => handlePageChange(currentPage - 1)}
            disabled={currentPage === 1}
          >
            <ChevronLeft data-icon="inline-start" />
            Previous
          </Button>
          <span className="min-w-28 text-center text-sm font-medium text-card-foreground">
            Page {currentPage} of {totalPages}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => handlePageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
          >
            Next
            <ChevronRight data-icon="inline-end" />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => handleZoom("out")}
            disabled={scale <= 0.5}
          >
            <Minus data-icon="inline-start" />
            Zoom
          </Button>
          <span className="w-14 text-center text-sm font-medium tabular-nums text-card-foreground">
            {Math.round(scale * 100)}%
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => handleZoom("in")}
            disabled={scale >= 5.0}
          >
            <Plus data-icon="inline-start" />
            Zoom
          </Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[8fr_10fr]">
        <div className="min-w-0 overflow-auto bg-background p-4 relative">
          <div className="relative mx-auto rounded-md shadow-2xl flex justify-center w-fit">
            <canvas ref={canvasRef} className="rounded-md bg-white" style={{ maxWidth: 'none' }} />
            <PdfOverlayLayer
            annotations={annotations}
            currentPage={currentPage}
            scale={scale}
          />
          </div>
        </div>

        <div className="flex h-full min-w-0 flex-col overflow-y-auto border-l border-border bg-card">
          <CachedPageExtractionSidebar
            currentPage={currentPage}
            pageSummary={currentPageSummary}
            loading={summariesLoading}
            error={summariesError}
            onRetry={() => void loadCachedPageSummaries()}
            onJumpToPage={handlePageChange}
          />
          {currentPageHasPlaces ? (
            <details
              open
              className="border-l border-border bg-card px-4 pb-4"
            >
              <summary className="cursor-pointer py-3 text-sm font-semibold text-card-foreground">
                Locations on this page
              </summary>
              <div>
                <CaseIncidenceMap
                  places={places}
                  mode="single-page"
                  currentPage={currentPage}
                />
              </div>
            </details>
          ) : null}
        </div>
      </div>
    </div>
  );
}


