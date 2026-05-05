"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";

import { PdfOverlayLayer } from "./pdf-overlay-layer";
import { AiPageSummaryOverlay } from "./ai-page-summary-overlay";
import { RecommendedAdvocatesPanel } from "./recommended-advocates-panel";
import { getDocument, getAuthToken } from "@/lib/api/client";
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
  const [textPositions, setTextPositions] = useState<PdfTextPosition[]>([]);
  const [documentLanguage, setDocumentLanguage] = useState<string | null>(null);

  useEffect(() => {
    setCurrentPage(initialPage);
  }, [documentId, initialPage]);

  // Extract text positions from all pages
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

    setTextPositions(allPositions);
    onTextExtracted?.(allPositions);
    return allPositions;
  }

  // Load PDF document
  useEffect(() => {
    async function loadPdf() {
      try {
        setLoading(true);
        setError(null);
        setDocumentLanguage(null);

        const [response, documentResult] = await Promise.all([
          fetch(
            `${process.env.NEXT_PUBLIC_ORDERFLOW_API_BASE_URL ?? "http://localhost:8000/api/v1"}/documents/${documentId}/download`,
            {
              headers: {
                ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}),
              },
            },
          ),
          getDocument(documentId),
        ]);

        if (documentResult.ok) {
          setDocumentLanguage(
            documentResult.data.auto_detected_language ?? documentResult.data.source_language ?? "en",
          );
        }

        if (!response.ok) {
          throw new Error(`Failed to download PDF: ${response.status}`);
        }

        const arrayBuffer = await response.arrayBuffer();
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
  }, [documentId]);

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
    if (newScale >= 0.5 && newScale <= 3.0) {
      setScale(newScale);
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyItems: 'center', padding: '32px' }}>
        <div style={{ color: '#4b5563' }}>Loading PDF...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyItems: 'center', padding: '32px' }}>
        <div style={{ color: '#dc2626' }}>Error: {error}</div>
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
    <div className="pdf-viewer">
      {/* Toolbar */}
      <div className="pdf-toolbar" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', background: 'rgba(255,255,255,0.05)', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button
            onClick={() => handlePageChange(currentPage - 1)}
            disabled={currentPage === 1}
            style={{ padding: '4px 12px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '6px', opacity: currentPage === 1 ? 0.5 : 1, cursor: currentPage === 1 ? 'default' : 'pointer', color: '#fff' }}
          >
            Previous
          </button>
          <span style={{ fontSize: '14px' }}>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => handlePageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            style={{ padding: '4px 12px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '6px', opacity: currentPage === totalPages ? 0.5 : 1, cursor: currentPage === totalPages ? 'default' : 'pointer', color: '#fff' }}
          >
            Next
          </button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={() => handleZoom("out")}
            disabled={scale <= 0.5}
            style={{ padding: '4px 12px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '6px', opacity: scale <= 0.5 ? 0.5 : 1, cursor: scale <= 0.5 ? 'default' : 'pointer', color: '#fff' }}
          >
            -
          </button>
          <span style={{ fontSize: '14px', width: '64px', textAlign: 'center' }}>{Math.round(scale * 100)}%</span>
          <button
            onClick={() => handleZoom("in")}
            disabled={scale >= 3.0}
            style={{ padding: '4px 12px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '6px', opacity: scale >= 3.0 ? 0.5 : 1, cursor: scale >= 3.0 ? 'default' : 'pointer', color: '#fff' }}
          >
            +
          </button>
        </div>
      </div>

      {/* Canvas Container */}
      <div className="pdf-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'flex-start', gap: '32px', padding: '24px', overflow: 'auto', height: "calc(100vh - 200px)", background: "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)" }}>

        {/* PDF Document Viewer */}
        <div style={{ position: 'relative', display: 'inline-block', flexShrink: 0, transition: 'all 300ms', boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)", background: '#fff', borderRadius: '8px' }}>
          <canvas ref={canvasRef} style={{ borderRadius: '8px', background: '#fff' }} />
          <PdfOverlayLayer
            annotations={annotations}
            currentPage={currentPage}
            scale={scale}
            onAnnotationClick={(annotation) => {
              console.log("Annotation clicked:", annotation);
            }}
          />
        </div>

        {/* AI Insight Sidebar */}
        <div style={{ position: 'sticky', top: '24px', flexShrink: 0, zIndex: 10, width: "380px", display: "flex", flexDirection: "column", gap: "12px" }}>
          <AiPageSummaryOverlay
            currentPage={currentPage}
            pageText={textPositions.filter(t => t.page === currentPage).map(t => t.text).join(" ")}
            documentId={documentId}
            preferredLanguage={documentLanguage}
            onJumpToPage={handlePageChange}
          />
          <RecommendedAdvocatesPanel documentId={documentId} />
          {currentPageHasPlaces ? (
            <details
              open
              style={{
                border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: "12px",
                background: "rgba(15,23,42,0.82)",
                padding: "12px",
              }}
            >
              <summary
                style={{
                  cursor: "pointer",
                  fontSize: "14px",
                  fontWeight: 700,
                  color: "#e2e8f0",
                }}
              >
                Locations on this page
              </summary>
              <div style={{ marginTop: "12px" }}>
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
