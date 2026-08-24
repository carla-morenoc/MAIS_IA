"use client";

import React, { useState, useRef, useEffect } from "react";
import { Upload, FileText, CheckCircle2, AlertCircle, Loader2, Trash2, Search, Video, RotateCw, Play } from "lucide-react";
import { uploadDocument, getDocumentStatus, listDocuments, deleteDocument, DocumentStatusResponse, syncYoutubeVideos, getYoutubeChannelConfig } from "../lib/api";

export interface TrackedDocument {
  id: string;
  filename: string;
  file_path?: string;
  status: string;
  document_type?: string;
  totalChunks: number | null;
  errorMessage: string | null;
}

interface DocumentSidebarProps {
  onSelectionChange: (docIds: string[], filenames: string[], selectedDocs?: TrackedDocument[]) => void;
  selectedDocIds: string[];
}

export default function DocumentSidebar({ onSelectionChange, selectedDocIds }: DocumentSidebarProps) {
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<TrackedDocument[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [syncingYt, setSyncingYt] = useState(false);
  const activePollsRef = useRef<{ [key: string]: NodeJS.Timeout }>({});
  
  const [channelUrl, setChannelUrl] = useState("");
  const [toast, setToast] = useState<{message: string, type: "success" | "error"} | null>(null);

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 5000);
  };

  useEffect(() => {
    const savedUrl = localStorage.getItem("mais_youtube_channel_url");
    if (savedUrl) {
      setChannelUrl(savedUrl);
    } else {
      getYoutubeChannelConfig()
        .then((cfg) => {
          if (cfg && cfg.channel_url) {
            setChannelUrl(cfg.channel_url);
          }
        })
        .catch((err) => {
          console.warn("No se pudo cargar el canal por defecto del backend:", err);
        });
    }
  }, []);

  const handleChannelUrlChange = (val: string) => {
    setChannelUrl(val);
    localStorage.setItem("mais_youtube_channel_url", val);
  };


  const handleSyncYoutube = async () => {
    setSyncingYt(true);
    setError(null);
    try {
      const result = await syncYoutubeVideos(channelUrl);
      const data = await listDocuments();
      const formatted: TrackedDocument[] = data.map((d) => ({
        id: d.document_id,
        filename: d.filename,
        file_path: d.file_path,
        status: d.status,
        document_type: d.document_type || "pdf",
        totalChunks: d.total_chunks,
        errorMessage: d.error_message,
      }));
      setDocuments(formatted);
      
      formatted.forEach((doc) => {
        if (doc.status === "PENDING" || doc.status === "PROCESSING") {
          startPolling(doc.id, doc.filename);
        }
      });
      if (result.added && result.added > 0) {
        showToast(`Se han encontrado y encolado ${result.added} vídeos nuevos.`, "success");
      } else {
        showToast("Sincronización completada. No hay vídeos nuevos.", "success");
      }
    } catch (err: any) {
      setError(err.message || "Error al sincronizar vídeos de YouTube.");
    } finally {
      setSyncingYt(false);
    }
  };

  useEffect(() => {
    async function loadDocs() {
      try {
        const data = await listDocuments();
        const formatted: TrackedDocument[] = data.map((d) => ({
          id: d.document_id,
          filename: d.filename,
          file_path: d.file_path,
          status: d.status,
          document_type: d.document_type || "pdf",
          totalChunks: d.total_chunks,
          errorMessage: d.error_message,
        }));
        setDocuments(formatted);

        if (selectedDocIds.length === 0) {
          const completedDocs = formatted.filter((d) => d.status === "COMPLETED");
          if (completedDocs.length > 0) {
            onSelectionChange(
              completedDocs.map((d) => d.id),
              completedDocs.map((d) => d.filename),
              completedDocs
            );
          }
        }
        
        formatted.forEach((doc) => {
          if (doc.status === "PENDING" || doc.status === "PROCESSING") {
            startPolling(doc.id, doc.filename);
          }
        });
      } catch (err: any) {
        console.error("Error al inicializar documentos:", err);
        setError("Error al cargar la lista de documentos del servidor.");
      }
    }
    loadDocs();

    return () => {
      Object.values(activePollsRef.current).forEach((interval) => clearInterval(interval));
    };
  }, []);

  const startPolling = (docId: string, filename: string) => {
    if (activePollsRef.current[docId]) {
      clearInterval(activePollsRef.current[docId]);
    }

    const interval = setInterval(async () => {
      try {
        const data = await getDocumentStatus(docId);
        
        setDocuments((prev) =>
          prev.map((doc) =>
            doc.id === docId
              ? {
                  ...doc,
                  status: data.status,
                  totalChunks: data.total_chunks,
                  errorMessage: data.error_message,
                }
              : doc
          )
        );

        if (data.status === "COMPLETED" || data.status === "FAILED") {
          clearInterval(interval);
          delete activePollsRef.current[docId];
        }
      } catch (err) {
        console.error("Error polling document:", err);
      }
    }, 1500);

    activePollsRef.current[docId] = interval;
  };

  const handleDelete = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation(); 
    
    if (!confirm("¿Estás seguro de que deseas eliminar este documento y todas sus citas asociadas?")) {
      return;
    }

    try {
      if (activePollsRef.current[docId]) {
        clearInterval(activePollsRef.current[docId]);
        delete activePollsRef.current[docId];
      }

      await deleteDocument(docId);
      
      const nextDocs = documents.filter((doc) => doc.id !== docId);
      setDocuments(nextDocs);
      
      if (selectedDocIds.includes(docId)) {
        const nextDocIds = selectedDocIds.filter((id) => id !== docId);
        const nextFilenames = nextDocs
          .filter((d) => nextDocIds.includes(d.id))
          .map((d) => d.filename);
        const nextSelectedDocs = nextDocs.filter((d) => nextDocIds.includes(d.id));
        onSelectionChange(nextDocIds, nextFilenames, nextSelectedDocs);
      }
    } catch (err: any) {
      setError(err.message || "Error al eliminar documento.");
    }
  };

  const handleToggleDocument = (docId: string, filename: string) => {
    let nextDocIds: string[];
    let nextFilenames: string[];

    if (selectedDocIds.includes(docId)) {
      nextDocIds = selectedDocIds.filter((id) => id !== docId);
    } else {
      nextDocIds = [...selectedDocIds, docId];
    }

    nextFilenames = documents
      .filter((d) => nextDocIds.includes(d.id))
      .map((d) => d.filename);

    const nextSelectedDocs = documents.filter((d) => nextDocIds.includes(d.id));
    onSelectionChange(nextDocIds, nextFilenames, nextSelectedDocs);
  };

  const handleSelectAllPdfs = () => {
    const completedPdfIds = documents
      .filter((d) => (d.document_type || "pdf") === "pdf" && d.status === "COMPLETED")
      .map((d) => d.id);
    
    // Mantener los vídeos que ya estaban seleccionados
    const currentVideoIds = selectedDocIds.filter((id) => {
      const doc = documents.find((d) => d.id === id);
      return doc && doc.document_type === "youtube";
    });

    const combinedIds = Array.from(new Set([...currentVideoIds, ...completedPdfIds]));
    const combinedDocs = documents.filter((d) => combinedIds.includes(d.id));
    const combinedFilenames = combinedDocs.map((d) => d.filename);
    onSelectionChange(combinedIds, combinedFilenames, combinedDocs);
  };

  const handleDeselectAllPdfs = () => {
    // Mantener únicamente los vídeos seleccionados
    const currentVideoIds = selectedDocIds.filter((id) => {
      const doc = documents.find((d) => d.id === id);
      return doc && doc.document_type === "youtube";
    });
    const combinedDocs = documents.filter((d) => currentVideoIds.includes(d.id));
    const combinedFilenames = combinedDocs.map((d) => d.filename);
    onSelectionChange(currentVideoIds, combinedFilenames, combinedDocs);
  };

  const handleSelectAllVideos = () => {
    const completedVideoIds = documents
      .filter((d) => d.document_type === "youtube" && d.status === "COMPLETED")
      .map((d) => d.id);
    
    // Mantener los PDFs que ya estaban seleccionados
    const currentPdfIds = selectedDocIds.filter((id) => {
      const doc = documents.find((d) => d.id === id);
      return doc && (doc.document_type || "pdf") === "pdf";
    });

    const combinedIds = Array.from(new Set([...currentPdfIds, ...completedVideoIds]));
    const combinedDocs = documents.filter((d) => combinedIds.includes(d.id));
    const combinedFilenames = combinedDocs.map((d) => d.filename);
    onSelectionChange(combinedIds, combinedFilenames, combinedDocs);
  };

  const handleDeselectAllVideos = () => {
    // Mantener únicamente los PDFs seleccionados
    const currentPdfIds = selectedDocIds.filter((id) => {
      const doc = documents.find((d) => d.id === id);
      return doc && (doc.document_type || "pdf") === "pdf";
    });
    const combinedDocs = documents.filter((d) => currentPdfIds.includes(d.id));
    const combinedFilenames = combinedDocs.map((d) => d.filename);
    onSelectionChange(currentPdfIds, combinedFilenames, combinedDocs);
  };


  const handleUpload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Solo se aceptan archivos PDF.");
      return;
    }

    setUploading(true);
    setError(null);

    const tempId = "temp-" + Date.now();
    const tempDoc: TrackedDocument = {
      id: tempId,
      filename: file.name,
      status: "UPLOADING",
      document_type: "pdf",
      totalChunks: null,
      errorMessage: null,
    };
    setDocuments((prev) => [tempDoc, ...prev]);

    try {
      const res = await uploadDocument(file);
      
      setDocuments((prev) => 
        prev.map(d => d.id === tempId ? {
          ...d,
          id: res.document_id,
          status: "PENDING",
        } : d)
      );
      
      const nextDocIds = [...selectedDocIds, res.document_id];
      const nextFilenames = [
        ...documents.filter((d) => selectedDocIds.includes(d.id)).map((d) => d.filename),
        file.name
      ];
      onSelectionChange(nextDocIds, nextFilenames);
      
      startPolling(res.document_id, file.name);
    } catch (err: any) {
      setDocuments((prev) => prev.filter(d => d.id !== tempId));
      setError(err.message || "Error al subir documento.");
    } finally {
      setUploading(false);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleUpload(e.dataTransfer.files[0]);
    }
  };

  return (
    <aside className="w-80 bg-zinc-950 border-r border-zinc-800 flex flex-col h-full relative">
      {toast && (
        <div className={`absolute bottom-4 left-4 right-4 p-3 rounded-xl text-xs font-medium border shadow-xl z-50 transition-all ${
          toast.type === "success" 
            ? "bg-green-950/90 border-green-900/50 text-green-400" 
            : "bg-red-950/90 border-red-900/50 text-red-400"
        }`}>
          {toast.message}
        </div>
      )}

      <div className="p-6 border-b border-zinc-800 flex items-center justify-between">
        <h2 className="text-xl font-bold text-zinc-100 flex items-center gap-2 tracking-tight">
          <span className="w-3 h-3 rounded-full bg-blue-500 animate-pulse"></span>
          MAIS
        </h2>
        <span className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded font-mono">v0.1.0</span>
      </div>

      <div className="p-6 border-b border-zinc-800">
        <div
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border border-dashed rounded-xl p-5 text-center cursor-pointer transition-all duration-300 flex flex-col items-center justify-center gap-3 ${
            dragActive
              ? "border-blue-500 bg-blue-950/20"
              : "border-zinc-800 hover:border-zinc-700 bg-zinc-900/30 hover:bg-zinc-900/50"
          }`}
        >
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            accept=".pdf"
            onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
          />
          {uploading ? (
            <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
          ) : (
            <Upload className="h-8 w-8 text-zinc-500 transition-transform group-hover:-translate-y-1" />
          )}
          <div>
            <p className="text-sm font-semibold text-zinc-300">Sube tu PDF</p>
            <p className="text-xs text-zinc-500 mt-1">Arrastra y suelta aquí</p>
          </div>
        </div>
        {error && (
          <p className="text-xs text-red-500 mt-3 flex items-center gap-1.5 bg-red-950/20 border border-red-900/50 p-2 rounded-lg">
            <AlertCircle className="h-3.5 w-3.5" />
            {error}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {(() => {
          const completedPdfs = documents.filter(d => (d.document_type || "pdf") === "pdf" && d.status === "COMPLETED");
          const allPdfsSelected = completedPdfs.length > 0 && completedPdfs.every(d => selectedDocIds.includes(d.id));
          const selectedPdfCount = completedPdfs.filter(d => selectedDocIds.includes(d.id)).length;

          return (
            <div className="flex items-center justify-between mb-1">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={allPdfsSelected}
                  disabled={completedPdfs.length === 0}
                  onChange={() => {
                    if (allPdfsSelected) {
                      handleDeselectAllPdfs();
                    } else {
                      handleSelectAllPdfs();
                    }
                  }}
                  className="h-3.5 w-3.5 rounded border-zinc-700 text-blue-600 focus:ring-blue-500 bg-zinc-900 cursor-pointer disabled:opacity-40"
                  title={allPdfsSelected ? "Deseleccionar todos los PDFs" : "Seleccionar todos los PDFs"}
                />
                <h3 className="text-xs font-bold text-zinc-400 hover:text-zinc-200 uppercase tracking-widest transition-colors">
                  Documentos Activos
                </h3>
              </label>
              <span className="text-[10px] text-zinc-500 font-mono">
                {selectedPdfCount}/{completedPdfs.length}
              </span>
            </div>
          );
        })()}

        <div className="relative">
          <input
            type="text"
            placeholder="Buscar PDF por nombre..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-zinc-900/50 hover:bg-zinc-900/80 focus:bg-zinc-900/90 border border-zinc-800 text-zinc-200 text-xs rounded-xl pl-9 pr-4 py-2.5 outline-none focus:border-blue-500/80 transition-all placeholder-zinc-500"
          />
          <Search className="absolute left-3 top-3 h-3.5 w-3.5 text-zinc-500" />
        </div>

        {selectedDocIds.length > 0 && (
          <button
            onClick={() => onSelectionChange([], [])}
            className="w-full text-center p-2 rounded-xl text-[10px] text-blue-400 hover:text-blue-300 hover:bg-blue-950/20 border border-blue-900/30 transition-all font-semibold uppercase tracking-wider cursor-pointer"
          >
            Limpiar selección ({selectedDocIds.length} seleccionados)
          </button>
        )}
        
        {(() => {
          const pdfDocs = documents.filter(d => (d.document_type || "pdf") === "pdf");
          const filteredDocs = pdfDocs.filter((doc) =>
            doc.filename.toLowerCase().includes(searchTerm.toLowerCase())
          );

          return (
            <div className="space-y-2">
              {filteredDocs.length === 0 ? (
                <p className="text-center text-xs text-zinc-600 py-6">
                  No hay manuales PDF indexados.
                </p>
              ) : (
                filteredDocs.map((doc) => {
                  const isSelected = selectedDocIds.includes(doc.id);
                  return (
                    <div
                      key={doc.id}
                      onClick={() => doc.status === "COMPLETED" && handleToggleDocument(doc.id, doc.filename)}
                      className={`p-3 rounded-xl border transition-all duration-300 relative group ${
                        doc.status === "COMPLETED" ? "cursor-pointer" : "opacity-60 cursor-not-allowed"
                      } ${
                        isSelected
                          ? "border-blue-500/50 bg-blue-950/10 shadow-lg shadow-blue-950/10"
                          : "border-zinc-900 hover:border-zinc-800 bg-zinc-900/20 hover:bg-zinc-900/40"
                      }`}
                    >
                      <button
                        onClick={(e) => handleDelete(doc.id, e)}
                        className="absolute top-3 right-3 text-zinc-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10 cursor-pointer"
                        title="Eliminar documento"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>

                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          disabled={doc.status !== "COMPLETED"}
                          onChange={(e) => {
                            e.stopPropagation();
                            if (doc.status === "COMPLETED") {
                              handleToggleDocument(doc.id, doc.filename);
                            }
                          }}
                          className="mt-1 h-3.5 w-3.5 rounded border-zinc-700 text-blue-600 focus:ring-blue-500 bg-zinc-900 shrink-0 cursor-pointer disabled:opacity-40"
                        />
                        
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <FileText className={`h-4 w-4 shrink-0 ${isSelected ? "text-blue-400" : "text-zinc-500"}`} />
                            <p className="text-sm font-medium text-zinc-200 truncate pr-6">{doc.filename}</p>
                          </div>
                          
                          <div className="flex items-center gap-1.5 mt-1.5 pl-5">
                            {doc.status === "COMPLETED" && (
                              <>
                                <CheckCircle2 className="h-3 w-3 text-green-500" />
                                <span className="text-xs text-zinc-500">{doc.totalChunks} chunks</span>
                              </>
                            )}
                            {doc.status === "FAILED" && (
                              <div className="mt-1">
                                <div className="flex items-center gap-1.5">
                                  <AlertCircle className="h-3 w-3 text-red-500 shrink-0" />
                                  <span className="text-xs font-bold text-red-500">Error</span>
                                </div>
                              </div>
                            )}
                            {(doc.status === "PENDING" || doc.status === "PROCESSING" || doc.status === "UPLOADING") && (
                              <div className="flex items-center gap-1.5">
                                <Loader2 className="h-3 w-3 text-blue-400 animate-spin" />
                                <span className="text-xs text-blue-400">Procesando...</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          );
        })()}

        <div className="pt-4 border-t border-zinc-900 space-y-4">
          <div className="flex flex-col gap-3">
            {(() => {
              const completedVideos = documents.filter(d => d.document_type === "youtube" && d.status === "COMPLETED");
              const allVideosSelected = completedVideos.length > 0 && completedVideos.every(d => selectedDocIds.includes(d.id));
              const selectedVideoCount = completedVideos.filter(d => selectedDocIds.includes(d.id)).length;

              return (
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={allVideosSelected}
                      disabled={completedVideos.length === 0}
                      onChange={() => {
                        if (allVideosSelected) {
                          handleDeselectAllVideos();
                        } else {
                          handleSelectAllVideos();
                        }
                      }}
                      className="h-3.5 w-3.5 rounded border-zinc-700 text-red-600 focus:ring-red-500 bg-zinc-900 cursor-pointer disabled:opacity-40"
                      title={allVideosSelected ? "Deseleccionar todos los vídeos" : "Seleccionar todos los vídeos"}
                    />
                    <h3 className="text-xs font-bold text-zinc-400 hover:text-zinc-200 uppercase tracking-widest flex items-center gap-1.5 transition-colors">
                      <Video className="h-4 w-4 text-red-500 shrink-0" />
                      Videotutoriales
                    </h3>
                  </label>

                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-zinc-500 font-mono">
                      {selectedVideoCount}/{completedVideos.length}
                    </span>
                    <button
                      onClick={handleSyncYoutube}
                      disabled={syncingYt}
                      className="p-1.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 hover:text-zinc-200 text-zinc-400 cursor-pointer disabled:opacity-40 transition-all flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider"
                      title="Sincronizar videotutoriales de YouTube"
                    >
                      {syncingYt ? (
                        <Loader2 className="h-3.5 w-3.5 text-red-500 animate-spin" />
                      ) : (
                        <RotateCw className="h-3.5 w-3.5 text-zinc-400" />
                      )}
                      <span>Sincronizar</span>
                    </button>
                  </div>
                </div>
              );
            })()}
            
            <input
              type="text"
              value={channelUrl}
              onChange={(e) => handleChannelUrlChange(e.target.value)}
              placeholder="Enlace o ID del canal de YouTube..."
              className="w-full bg-zinc-900/50 hover:bg-zinc-900/80 focus:bg-zinc-900/90 border border-zinc-800 text-zinc-200 text-xs rounded-xl px-3 py-2 outline-none focus:border-red-500/80 transition-all placeholder-zinc-600"
            />
          </div>

          {(() => {
            const ytDocs = documents.filter(d => d.document_type === "youtube");
            const filteredYt = ytDocs.filter(d => d.filename.toLowerCase().includes(searchTerm.toLowerCase()));

            return (
              <div className="space-y-2">
                {filteredYt.length === 0 ? (
                  <div className="text-center py-6 border border-zinc-900 rounded-xl bg-zinc-950/10">
                    <p className="text-xs text-zinc-600">No hay vídeos indexados. Haz clic en "Sincronizar" para buscarlos.</p>
                  </div>
                ) : (
                  filteredYt.map((doc) => {
                    const isSelected = selectedDocIds.includes(doc.id);
                    return (
                      <div
                        key={doc.id}
                        onClick={() => doc.status === "COMPLETED" && handleToggleDocument(doc.id, doc.filename)}
                        className={`p-3 rounded-xl border transition-all duration-300 relative group ${
                          doc.status === "COMPLETED" ? "cursor-pointer" : "opacity-60 cursor-not-allowed"
                        } ${
                          isSelected
                            ? "border-red-500/50 bg-red-950/10 shadow-lg shadow-red-950/10"
                            : "border-zinc-900 hover:border-zinc-800 bg-zinc-900/20 hover:bg-zinc-900/40"
                        }`}
                      >
                        <button
                          onClick={(e) => handleDelete(doc.id, e)}
                          className="absolute top-3 right-3 text-zinc-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10 cursor-pointer"
                          title="Eliminar videotutorial"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>

                        <div className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            disabled={doc.status !== "COMPLETED"}
                            onChange={(e) => {
                              e.stopPropagation();
                              if (doc.status === "COMPLETED") {
                                handleToggleDocument(doc.id, doc.filename);
                              }
                            }}
                            className="mt-1 h-3.5 w-3.5 rounded border-zinc-700 text-red-600 focus:ring-red-500 bg-zinc-900 shrink-0 cursor-pointer disabled:opacity-40"
                          />
                          
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <Play className={`h-3.5 w-3.5 shrink-0 ${isSelected ? "text-red-400" : "text-zinc-500"}`} />
                              <p className="text-xs font-semibold text-zinc-200 truncate pr-6">{doc.filename}</p>
                            </div>
                            
                            <div className="flex items-center gap-1.5 mt-1.5 pl-5">
                              {doc.status === "COMPLETED" && (
                                <>
                                  <CheckCircle2 className="h-3 w-3 text-green-500 animate-pulse" />
                                  <span className="text-[10px] text-zinc-500 font-medium">{doc.totalChunks} chunks</span>
                                </>
                              )}
                              {doc.status === "FAILED" && (
                                <span className="text-[10px] text-red-500 font-bold">Error en procesado</span>
                              )}
                              {(doc.status === "PENDING" || doc.status === "PROCESSING" || doc.status === "UPLOADING") && (
                                <div className="flex items-center gap-1.5">
                                  <Loader2 className="h-3 w-3 text-red-400 animate-spin" />
                                  <span className="text-[10px] text-red-400">Indexando...</span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            );
          })()}
        </div>

      </div>
    </aside>
  );
}
