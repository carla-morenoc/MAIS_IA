"use client";

import React, { useState } from "react";
import dynamic from "next/dynamic";
import DocumentSidebar, { TrackedDocument } from "../components/DocumentSidebar";
import ChatInterface from "../components/ChatInterface";

const PdfViewer = dynamic(() => import("../components/PdfViewer"), {
  ssr: false,
});

export default function Home() {
  const [documents, setDocuments] = useState<TrackedDocument[]>([]);
  const [viewerPdf, setViewerPdf] = useState<{
    docId: string;
    filename: string;
    pageNumber: number;
    snippet?: string;
  } | null>(null);
  const [highlightEnabled, setHighlightEnabled] = useState(true);

  const handleOpenPdf = (docId: string, filename: string, pageNumber: number, snippet?: string, type: "pdf" | "youtube" = "pdf", videoId?: string) => {
    if (type === "youtube" || videoId) {
      const value = videoId || docId;
      const videoUrl = value.includes("youtube.com")
        ? value
        : `https://www.youtube.com/watch?v=${value}`;
      const separator = videoUrl.includes("?") ? "&" : "?";
      const ytUrl = `${videoUrl}${separator}t=${Math.max(0, Math.floor(pageNumber))}s`;
      window.open(ytUrl, "_blank");
      return;
    }

    setViewerPdf({ docId, filename, pageNumber, snippet });
  };

  const handleToggleHighlight = () => {
    setHighlightEnabled((prev) => !prev);
  };

  const selectedDocuments = documents.filter(
    (document) => document.status === "COMPLETED" && document.is_active
  );
  const selectedDocIds = selectedDocuments.map((document) => document.id);
  const selectedFilenames = selectedDocuments.map((document) => document.filename);

  return (
    <div className="flex h-screen w-screen bg-zinc-950 text-zinc-100 overflow-hidden font-sans antialiased">
      {/* Fondo decorativo con gradiente suave */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-indigo-950/10 via-zinc-950 to-zinc-950 pointer-events-none z-0"></div>

      <div className="flex h-full w-full relative z-10">
        {/* Barra Lateral Izquierda (Documentos y Carga) */}
        <DocumentSidebar
          onDocumentsChange={setDocuments}
          onOpenDocument={(docId, filename, type, filePath) => handleOpenPdf(docId, filename, 1, undefined, type, filePath)}
        />

        {/* Ventana de Chat Conversacional RAG */}
        <ChatInterface
          selectedDocIds={selectedDocIds}
          selectedFilenames={selectedFilenames}
          selectedDocuments={selectedDocuments}
          onOpenPdf={handleOpenPdf}
          viewerPdf={viewerPdf}
          highlightEnabled={highlightEnabled}
          onToggleHighlight={handleToggleHighlight}
        />

        {/* Panel Visor Interactivo Lateral Derecho (PDF) */}
        {viewerPdf && (
          <PdfViewer
            docId={viewerPdf.docId}
            filename={viewerPdf.filename}
            pageNumber={viewerPdf.pageNumber}
            snippet={viewerPdf.snippet}
            highlightEnabled={highlightEnabled}
            onToggleHighlight={handleToggleHighlight}
            onClose={() => setViewerPdf(null)}
          />
        )}
      </div>
    </div>
  );
}

