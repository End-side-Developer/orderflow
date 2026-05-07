"use client";

import { type MouseEvent, useEffect, useRef, useState } from "react";

interface NormalizedBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface VisualRef {
  page_number: number;
  bbox: NormalizedBox;
  text: string;
  source: "native_pdf" | "ocr" | "synthetic";
  granularity: "char" | "word" | "line" | "clause";
}

interface Annotation {
  id: string;
  page_number: number;
  annotation_type: "highlight" | "note" | "obligation";
  text_content: string | null;
  bbox: { x: number; y: number; width: number; height: number } | null;
  boxes?: NormalizedBox[];
  color: string | null;
  tooltip_text: string | null;
}

interface PdfOverlayLayerProps {
  annotations: Annotation[];
  currentPage: number;
  scale: number;
  activeRefs?: VisualRef[];
  onAnnotationClick?: (annotation: Annotation) => void;
}

type HoveredAnnotation = {
  annotation: Annotation;
  anchor: {
    left: number;
    top: number;
    width: number;
    height: number;
  };
  placement: "above" | "below";
};

export function PdfOverlayLayer({
  annotations,
  currentPage,
  scale,
  activeRefs = [],
  onAnnotationClick,
}: PdfOverlayLayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [hoveredAnnotation, setHoveredAnnotation] = useState<HoveredAnnotation | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setContainerWidth(entry.contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const pageAnnotations = annotations.filter((a) => a.page_number === currentPage);
  const pageActiveRefs = activeRefs.filter((ref) => ref.page_number === currentPage);

  const getColorClass = (color: string | null) => {
    switch (color) {
      case "red":
        return "bg-red-500/30 border-red-500";
      case "orange":
        return "bg-orange-500/30 border-orange-500";
      case "yellow":
        return "bg-yellow-500/30 border-yellow-500";
      case "blue":
        return "bg-blue-500/30 border-blue-500";
      default:
        return "bg-gray-500/30 border-gray-500";
    }
  };

  const handleBoxMouseEnter = (annotation: Annotation, event: MouseEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    const targetRect = event.currentTarget.getBoundingClientRect();
    const containerRect = container?.getBoundingClientRect();
    const left = containerRect ? targetRect.left - containerRect.left : 0;
    const top = containerRect ? targetRect.top - containerRect.top : 0;
    const placement = top > 96 ? "above" : "below";

    setHoveredAnnotation({
      annotation,
      anchor: {
        left,
        top,
        width: targetRect.width,
        height: targetRect.height,
      },
      placement,
    });
  };

  const tooltipLeft = (left: number) => {
    if (!containerWidth) return Math.max(0, left);
    return Math.max(0, Math.min(left, Math.max(0, containerWidth - 320)));
  };

  return (
    <div ref={containerRef} className="pdf-overlay-layer absolute inset-0 pointer-events-none">
      {pageAnnotations.map((annotation) => {
        const boxes = annotation.boxes?.length
          ? annotation.boxes.map((box) => ({ kind: "normalized" as const, box }))
          : annotation.bbox
            ? [{ kind: "legacy" as const, box: annotation.bbox }]
            : [];
        if (boxes.length === 0) return null;

        return (
          <div key={annotation.id}>
            {boxes.map((entry, index) => {
              const style =
                entry.kind === "normalized"
                  ? {
                      left: `${entry.box.left * 100}%`,
                      top: `${entry.box.top * 100}%`,
                      width: `${entry.box.width * 100}%`,
                      height: `${entry.box.height * 100}%`,
                    }
                  : {
                      left: `${entry.box.x * scale}px`,
                      top: `${entry.box.y * scale}px`,
                      width: `${entry.box.width * scale}px`,
                      height: `${entry.box.height * scale}px`,
                    };
              return (
                <div
                  key={`${annotation.id}-${index}`}
                  className={`absolute cursor-pointer border-2 pointer-events-auto transition-opacity hover:opacity-80 ${getColorClass(annotation.color)}`}
                  style={style}
                  onMouseEnter={(event) => handleBoxMouseEnter(annotation, event)}
                  onMouseLeave={() => setHoveredAnnotation(null)}
                  onClick={() => onAnnotationClick?.(annotation)}
                />
              );
            })}
          </div>
        );
      })}

      {pageActiveRefs.map((ref, index) => (
        <div
          key={`active-${index}-${ref.text}`}
          className="absolute border-2 border-sky-600 bg-sky-400/25 shadow-[0_0_0_2px_rgba(2,132,199,0.2)]"
          style={{
            left: `${ref.bbox.left * 100}%`,
            top: `${ref.bbox.top * 100}%`,
            width: `${ref.bbox.width * 100}%`,
            height: `${ref.bbox.height * 100}%`,
          }}
          title={`${ref.source} ${ref.granularity}: ${ref.text}`}
        />
      ))}

      {hoveredAnnotation ? (
        <div
          className="absolute z-50 max-w-xs rounded bg-gray-900 p-2 text-sm text-white shadow-lg pointer-events-none"
          style={{
            left: `${tooltipLeft(hoveredAnnotation.anchor.left)}px`,
            top:
              hoveredAnnotation.placement === "above"
                ? `${hoveredAnnotation.anchor.top - 8}px`
                : `${hoveredAnnotation.anchor.top + hoveredAnnotation.anchor.height + 8}px`,
            transform: hoveredAnnotation.placement === "above" ? "translateY(-100%)" : undefined,
          }}
        >
          <div className="mb-1 font-semibold capitalize">
            {hoveredAnnotation.annotation.annotation_type}
          </div>
          {hoveredAnnotation.annotation.tooltip_text ? (
            <div className="text-gray-300">{hoveredAnnotation.annotation.tooltip_text}</div>
          ) : null}
          {hoveredAnnotation.annotation.text_content ? (
            <div className="mt-1 text-xs italic text-gray-400">
              &ldquo;{hoveredAnnotation.annotation.text_content.substring(0, 100)}...&rdquo;
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
