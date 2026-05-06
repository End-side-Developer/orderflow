"use client";

import { useEffect, useRef, useState } from "react";

interface Annotation {
  id: string;
  page_number: number;
  annotation_type: "highlight" | "note" | "obligation";
  text_content: string | null;
  bbox: { x: number; y: number; width: number; height: number } | null;
  color: string | null;
  tooltip_text: string | null;
}

interface PdfOverlayLayerProps {
  annotations: Annotation[];
  currentPage: number;
  scale: number;
  onAnnotationClick?: (annotation: Annotation) => void;
}

export function PdfOverlayLayer({
  annotations,
  currentPage,
  scale,
  onAnnotationClick,
}: PdfOverlayLayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredAnnotation, setHoveredAnnotation] = useState<Annotation | null>(null);

  const pageAnnotations = annotations.filter((a) => a.page_number === currentPage);

  const handleMouseEnter = (annotation: Annotation) => {
    setHoveredAnnotation(annotation);
  };

  const handleMouseLeave = () => {
    setHoveredAnnotation(null);
  };

  const handleClick = (annotation: Annotation) => {
    onAnnotationClick?.(annotation);
  };

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

  return (
    <div ref={containerRef} className="pdf-overlay-layer absolute inset-0 pointer-events-none">
      {pageAnnotations.map((annotation) => {
        if (!annotation.bbox) return null;

        const { x, y, width, height } = annotation.bbox;
        const scaledX = x * scale;
        const scaledY = y * scale;
        const scaledWidth = width * scale;
        const scaledHeight = height * scale;

        return (
          <div
            key={annotation.id}
            className={`absolute border-2 cursor-pointer pointer-events-auto transition-opacity hover:opacity-80 ${getColorClass(annotation.color)}`}
            style={{
              left: `${scaledX}px`,
              top: `${scaledY}px`,
              width: `${scaledWidth}px`,
              height: `${scaledHeight}px`,
            }}
            onMouseEnter={() => handleMouseEnter(annotation)}
            onMouseLeave={handleMouseLeave}
            onClick={() => handleClick(annotation)}
          />
        );
      })}

      {/* Floating Tooltip */}
      {hoveredAnnotation && (
        <div
          className="absolute bg-gray-900 text-white text-sm p-2 rounded shadow-lg max-w-xs z-50 pointer-events-none"
          style={{
            left: `${(hoveredAnnotation.bbox?.x || 0) * scale}px`,
            top: `${(hoveredAnnotation.bbox?.y || 0) * scale - 50}px`,
          }}
        >
          <div className="font-semibold mb-1 capitalize">
            {hoveredAnnotation.annotation_type}
          </div>
          {hoveredAnnotation.tooltip_text && (
            <div className="text-gray-300">{hoveredAnnotation.tooltip_text}</div>
          )}
          {hoveredAnnotation.text_content && (
            <div className="text-muted-foreground text-xs mt-1 italic">
              &ldquo;{hoveredAnnotation.text_content.substring(0, 100)}…&rdquo;
            </div>
          )}
        </div>
      )}
    </div>
  );
}


