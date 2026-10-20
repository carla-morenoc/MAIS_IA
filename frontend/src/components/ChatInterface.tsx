"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Sparkles, AlertCircle, FileText, Loader2, Play, ExternalLink, PlusCircle, RotateCcw } from "lucide-react";
import { queryChat, getChatHistory, ChatQueryResponse, SourceDocument, getPopularQuestions, FAQItem } from "../lib/api";
import { TrackedDocument } from "./DocumentSidebar";
import LatencyDisplay from "./LatencyDisplay";

interface ChatInterfaceProps {
  selectedDocIds: string[];
  selectedFilenames: string[];
  selectedDocuments?: TrackedDocument[];
  onOpenPdf: (docId: string, filename: string, pageNumber: number, snippet?: string, type?: "pdf" | "youtube", videoId?: string) => void;
  viewerPdf: { docId: string; filename: string; pageNumber: number; snippet?: string } | null;
  highlightEnabled: boolean;
  onToggleHighlight: () => void;
}

interface Message {
  id: string;
  sender: "user" | "bot";
  text: string;
  sources?: SourceDocument[];
  cragStatus?: string;
  latencyMs?: any;
}

export default function ChatInterface({
  selectedDocIds,
  selectedFilenames,
  selectedDocuments,
  onOpenPdf,
  viewerPdf,
  highlightEnabled,
  onToggleHighlight,
}: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "bot",
      text: "¡Hola! Soy Maisito, tu asistente inteligente. Sube un documento PDF o selecciona un videotutorial y hazme cualquier consulta para empezar.",
    },
  ]);
  const [sessionId, setSessionId] = useState<string>("");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [faqs, setFaqs] = useState<FAQItem[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const isSendingRef = useRef(false);
  const sessionIdRef = useRef(sessionId);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // Inicializar sessionId y recuperar historial persistente de PostgreSQL
  useEffect(() => {
    let sid = "";
    if (typeof window !== "undefined") {
      sid = localStorage.getItem("maisia_session_id") || "";
      if (!sid) {
        sid = (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : `sess_${Date.now()}`;
        localStorage.setItem("maisia_session_id", sid);
      }
      setSessionId(sid);

      getChatHistory(sid)
        .then((history) => {
          if (history && history.length > 0) {
            const loadedMessages: Message[] = history.map((m) => ({
              id: m.id,
              sender: m.role === "user" ? "user" : "bot",
              text: m.content,
              sources: m.sources,
              cragStatus: m.crag_status,
              latencyMs: m.latency_ms,
            }));
            setMessages(loadedMessages);
          }
        })
        .catch((e) => console.error("Error al cargar historial previo:", e));

      // Obtener FAQs dinámicas del backend
      getPopularQuestions()
        .then((fetchedFaqs) => {
          if (fetchedFaqs && fetchedFaqs.length > 0) {
            setFaqs(fetchedFaqs);
          }
        })
        .catch((e) => console.error("Error al cargar FAQs populares:", e));
    }
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleNewConversation = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    isSendingRef.current = false;
    setLoading(false);
    setError(null);

    const newSid = (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : `sess_${Date.now()}`;
    if (typeof window !== "undefined") {
      localStorage.setItem("maisia_session_id", newSid);
    }
    setSessionId(newSid);
    setMessages([
      {
        id: "welcome",
        sender: "bot",
        text: "¡Hola! Soy Maisito, tu asistente inteligente. Sube un documento PDF o selecciona un videotutorial y hazme cualquier consulta para empezar.",
      },
    ]);
  };

  const handleSend = async (e?: React.FormEvent, customQuery?: string) => {
    if (e) e.preventDefault();
    const queryToSend = customQuery ? customQuery.trim() : input.trim();
    if (!queryToSend || loading || isSendingRef.current) return;

    const currentSessionId = sessionId;

    isSendingRef.current = true;
    setInput("");
    setError(null);

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: queryToSend,
    };
    setMessages((prev) => [...prev, userMsg]);

    if (selectedDocIds.length === 0) {
      const warnMsg: Message = {
        id: `bot-warn-${Date.now()}`,
        sender: "bot",
        text: "⚠️ No hay ningún documento ni vídeo seleccionado. Por favor, marca al menos una casilla en el panel izquierdo para consultar.",
      };
      setMessages((prev) => [...prev, warnMsg]);
      isSendingRef.current = false;
      return;
    }

    setLoading(true);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await queryChat(queryToSend, selectedDocIds, currentSessionId, controller.signal);
      
      if (sessionIdRef.current !== currentSessionId) {
        return;
      }

      if (res.session_id && res.session_id !== currentSessionId) {
        setSessionId(res.session_id);
        if (typeof window !== "undefined") {
          localStorage.setItem("maisia_session_id", res.session_id);
        }
      }

      if (res.answer.includes("Error interno en la generación") || res.answer.includes("Error interno en")) {
        throw new Error("Lo siento, no puedo conectar con el servidor en este momento. Por favor, contacta con el servicio técnico de MAIS.");
      }

      const botMsg: Message = {
        id: `bot-${Date.now()}`,
        sender: "bot",
        text: res.answer,
        sources: res.sources,
        cragStatus: res.crag_status,
        latencyMs: res.latency_ms,
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (err: any) {
      if (err.name === "AbortError") {
        return;
      }
      if (sessionIdRef.current === currentSessionId) {
        setError(err.message || "Fallo al procesar la respuesta.");
      }
    } finally {
      if (sessionIdRef.current === currentSessionId) {
        isSendingRef.current = false;
        setLoading(false);
        abortControllerRef.current = null;
      }
    }
  };

  const getYoutubeUrl = (videoIdOrDocId: string, seconds: number, filename?: string) => {
    let ytUrl = "";
    const youtubeIdPattern = /^[A-Za-z0-9_-]{11}$/;
    if (videoIdOrDocId && youtubeIdPattern.test(videoIdOrDocId)) {
      // Los IDs de YouTube pueden contener guiones y guiones bajos.
      ytUrl = `https://www.youtube.com/watch?v=${videoIdOrDocId}&t=${seconds}s`;
    } else {
      const doc = selectedDocuments?.find(d => 
        d.id === videoIdOrDocId || 
        (filename && d.filename.toLowerCase().includes(filename.toLowerCase())) ||
        (filename && filename.toLowerCase().includes(d.filename.toLowerCase()))
      );
      if (doc?.file_path && doc.file_path.includes("youtube.com")) {
        const separator = doc.file_path.includes("?") ? "&" : "?";
        ytUrl = `${doc.file_path}${separator}t=${seconds}s`;
      } else if (filename) {
        ytUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(filename)}`;
      }
    }
    return ytUrl;
  };

  const openYoutubeUrl = (videoIdOrDocId: string, seconds: number, filename?: string) => {
    const ytUrl = getYoutubeUrl(videoIdOrDocId, seconds, filename);
    if (ytUrl) window.open(ytUrl, "_blank", "noopener,noreferrer");
  };

  const parseTimeToSeconds = (timeStr: string): number => {
    if (!timeStr) return 0;
    if (!timeStr.includes(":")) {
      return parseInt(timeStr, 10) || 0;
    }
    const parts = timeStr.split(":").map((p) => parseInt(p, 10) || 0);
    if (parts.length === 3) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    } else if (parts.length === 2) {
      return parts[0] * 60 + parts[1];
    }
    return parseInt(timeStr, 10) || 0;
  };

  const formatSecondsToTime = (totalSeconds: number): string => {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    }
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };

  const parseCitations = (text: string, sources: SourceDocument[] | undefined): React.ReactNode[] => {
    if (!text) return [];
    
    // Regex tolerante a formatos de tiempo: min. MM:SS, seg. X, o MM:SS
    const citationRegex = /[\[\u3010\uFF3B]([^\]\u3011\uFF3D\n]+?\.pdf)(?:[,\s]*(?:pág|pag|página|pagina|p)\.?\s*(\d+))?[\]\u3011\uFF3D]|[\[\u3010\uFF3B]Video:\s*([^,\n\]\u3011\uFF3D]+?),\s*(?:min\.|minuto|min|seg\.|segundo|seg|s)?\s*(\d+(?::\d+){0,2})[\]\u3011\uFF3D]/gi;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    const normalizeName = (n: string) =>
      n.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");

    while ((match = citationRegex.exec(text)) !== null) {
      const matchIndex = match.index;
      
      if (matchIndex > lastIndex) {
        parts.push(text.substring(lastIndex, matchIndex));
      }

      const isYt = match[3] !== undefined;
      const filename = (isYt ? match[3] : match[1]) || "";
      const rawTimeStr = isYt ? match[4] : (match[2] || "1");
      const pageNumber = isYt ? parseTimeToSeconds(rawTimeStr) : (parseInt(rawTimeStr, 10) || 1);
      const timeFormatted = isYt ? formatSecondsToTime(pageNumber) : "";
      const displayCitationText = isYt
        ? `[Video: ${filename}, min. ${timeFormatted}]`
        : `[${filename}, pág. ${pageNumber}]`;

      const sourceType = isYt ? "youtube" : "pdf";
      const matchingSources = (sources || []).filter((src) => (src.type || "pdf") === sourceType);
      const normalizedFilename = normalizeName(filename);
      const exactSources = matchingSources.filter(
        (src) => normalizeName(src.filename) === normalizedFilename
      );
      const partialSources = matchingSources.filter((src) => {
        const sourceName = normalizeName(src.filename);
        return sourceName.length >= 4 && normalizedFilename.length >= 4 &&
          (sourceName.includes(normalizedFilename) || normalizedFilename.includes(sourceName));
      });
      const sourceCandidates = exactSources.length > 0 ? exactSources : partialSources;
      const uniqueSources = [...new Map(sourceCandidates.map((src) => [src.doc_id, src])).values()];
      const uniqueTypeSources = [...new Map(matchingSources.map((src) => [src.doc_id, src])).values()];
      const matchingSource = uniqueSources.length === 1
        ? uniqueSources[0]
        : uniqueSources.length === 0 && uniqueTypeSources.length === 1
          ? uniqueTypeSources[0]
          : undefined;

      const matchingDocuments = (selectedDocuments || []).filter(
        (doc) => ((doc.document_type || "pdf") === "youtube" ? "youtube" : "pdf") === sourceType
      );
      const exactDocuments = matchingDocuments.filter(
        (doc) => normalizeName(doc.filename) === normalizedFilename
      );
      const partialDocuments = matchingDocuments.filter((doc) => {
        const documentName = normalizeName(doc.filename);
        return documentName.length >= 4 && normalizedFilename.length >= 4 &&
          (documentName.includes(normalizedFilename) || normalizedFilename.includes(documentName));
      });
      const documentCandidates = exactDocuments.length > 0 ? exactDocuments : partialDocuments;
      const uniqueDocuments = [...new Map(documentCandidates.map((doc) => [doc.id, doc])).values()];
      const uniqueTypeDocuments = [...new Map(matchingDocuments.map((doc) => [doc.id, doc])).values()];
      const matchingDocument = uniqueDocuments.length === 1
        ? uniqueDocuments[0]
        : uniqueDocuments.length === 0 && uniqueTypeDocuments.length === 1
          ? uniqueTypeDocuments[0]
          : undefined;
      const docId = matchingSource?.doc_id || matchingDocument?.id;
      const targetFilename = matchingSource?.filename || matchingDocument?.filename || filename;
      const snippetText = matchingSource?.snippet ? matchingSource.snippet.slice(0, 50) : undefined;
      const videoId = matchingSource?.video_id;

      if (!docId) {
        parts.push(match[0]);
        lastIndex = citationRegex.lastIndex;
        continue;
      }

      if (isYt) {
        const youtubeUrl = getYoutubeUrl(videoId || docId, pageNumber, targetFilename);
        parts.push(
          <a
            key={`cite-${matchIndex}`}
            href={youtubeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="px-2 py-0.5 mx-1 rounded-md bg-red-600/90 hover:bg-red-500 active:bg-red-700 text-white font-semibold text-xs transition-all duration-150 cursor-pointer inline-flex items-center gap-1.5 focus:outline-none shadow-sm hover:shadow-red-500/20 border border-red-400/30"
            title={`Abrir vídeo en YouTube en el minuto ${timeFormatted}`}
          >
            <Play className="h-3.5 w-3.5 shrink-0 text-red-200" />
            <span>{displayCitationText}</span>
            <ExternalLink className="h-2.5 w-2.5 opacity-70" />
          </a>
        );
      } else {
        parts.push(
          <button
            key={`cite-${matchIndex}`}
            onClick={() => onOpenPdf(docId, targetFilename, pageNumber, snippetText, "pdf")}
            className="px-2 py-0.5 mx-1 rounded-md bg-blue-600/90 hover:bg-blue-500 active:bg-blue-700 text-white font-semibold text-xs transition-all duration-150 cursor-pointer inline-flex items-center gap-1.5 focus:outline-none shadow-sm hover:shadow-blue-500/20 border border-blue-400/30"
            title={`Abrir página ${pageNumber} en el visor de ${targetFilename}`}
          >
            <FileText className="h-3.5 w-3.5 shrink-0 text-blue-200" />
            <span>{displayCitationText}</span>
          </button>
        );
      }

      lastIndex = citationRegex.lastIndex;
    }

    if (lastIndex === 0) {
      return [text];
    }

    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts;
  };

  const parseLinksAndCitations = (
    text: string,
    sources?: SourceDocument[]
  ): React.ReactNode[] => {
    const linkRegex = /\[\[([^\]\n]+)\]\]\((https?:\/\/[^\s)]+)\)|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s<]+)/gi;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = linkRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(...parseCitations(text.slice(lastIndex, match.index), sources));
      }

      const label = (match[1] || match[3] || match[5] || "")
        .replace(/^[\[【［]|[\]】］]$/g, "");
      const matchedUrl = match[2] || match[4] || match[5] || "";
      const url = match[5] ? matchedUrl.replace(/[.,!?;:]+$/, "") : matchedUrl;
      const trailingPunctuation = match[5] ? matchedUrl.slice(url.length) : "";
      parts.push(
        <a
          key={`link-${match.index}`}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-300 underline decoration-blue-400/50 underline-offset-2 hover:text-blue-200 break-all"
        >
          {label}
          <ExternalLink className="ml-1 inline h-3 w-3" />
        </a>
      );
      if (trailingPunctuation) {
        parts.push(trailingPunctuation);
      }
      lastIndex = linkRegex.lastIndex;
    }

    if (lastIndex < text.length) {
      parts.push(...parseCitations(text.slice(lastIndex), sources));
    }
    return parts;
  };

  const parseBoldText = (text: string, sources?: SourceDocument[]): React.ReactNode[] => {
    const parts = text.split(/(\*\*.*?\*\*)/g);
    const result: React.ReactNode[] = [];

    parts.forEach((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        const boldInner = part.slice(2, -2);
        const parsedInner = parseLinksAndCitations(boldInner, sources);

        result.push(
          <strong key={`bold-${index}`} className="font-extrabold text-zinc-50">
            {parsedInner}
          </strong>
        );
      } else if (part) {
        const parsed = parseLinksAndCitations(part, sources);
        result.push(...parsed);
      }
    });

    return result;
  };

  const renderFormattedText = (text: string, sources?: SourceDocument[]) => {
    if (!text) return null;
    
    const lines = text.split("\n");
    const formattedElements: React.ReactNode[] = [];
    
    let keyCounter = 0;
    let listItems: React.ReactNode[] = [];

    const flushList = () => {
      if (listItems.length > 0) {
        formattedElements.push(
          <ul
            key={`list-${keyCounter++}`}
            className="list-disc pl-5 my-2 space-y-1.5 text-zinc-300"
          >
            {listItems}
          </ul>
        );
        listItems = [];
      }
    };

    lines.forEach((line) => {
      const trimmedLine = line.trim();
      
      const isNumbered = /^(?:(\d+)\.\s*|([1-9]\uFE0F?\u20E3)\s*)(.+)$/.exec(trimmedLine);
      const isBullet = /^[-*]\s(.*)/.exec(trimmedLine);

      if (isNumbered) {
        flushList();
        const content = isNumbered[3];

        formattedElements.push(
          <div
            key={`num-${keyCounter++}`}
            className="flex gap-2 pl-2 my-2 leading-relaxed text-zinc-300"
          >
            <span className="font-bold text-blue-400 shrink-0">
              {isNumbered[1] ? `${isNumbered[1]}.` : isNumbered[2]}
            </span>
            <span className="flex-1">
              {parseBoldText(content, sources)}
            </span>
          </div>
        );
      } else if (isBullet) {
        const content = isBullet[1];

        listItems.push(
          <li key={`bullet-item-${keyCounter++}`} className="leading-relaxed">
            {parseBoldText(content, sources)}
          </li>
        );
      } else {
        flushList();

        if (trimmedLine) {
          formattedElements.push(
            <p
              key={`p-${keyCounter++}`}
              className="my-2 leading-relaxed text-zinc-300"
            >
              {parseBoldText(trimmedLine, sources)}
            </p>
          );
        } else {
          formattedElements.push(
            <div key={`spacer-${keyCounter++}`} className="h-2" />
          );
        }
      }
    });

    flushList();

    return <div className="space-y-1">{formattedElements}</div>;
  };

  const firstSelectedDoc = selectedDocuments?.find(d => d.id === selectedDocIds[0]);
  const isFirstYt = firstSelectedDoc?.document_type === "youtube";

  return (
    <section className="flex-1 flex flex-col h-full bg-zinc-900/10">

      {/* Header del Chat */}
      <div className="h-16 border-b border-zinc-800/80 px-8 flex items-center justify-between bg-zinc-950/20">
        <div>
          <h1 className="text-sm font-semibold text-zinc-100 flex items-center gap-1.5">
            <Sparkles className="h-4 w-4 text-blue-400" />
            Asistente Mais
          </h1>

          <p className="text-xs text-zinc-500 mt-0.5">
            {selectedFilenames.length === 0
              ? "⚠️ Ningún documento seleccionado"
              : selectedFilenames.length === 1
              ? `Buscando en: ${selectedFilenames[0]}`
              : `Buscando en: ${selectedFilenames.length} documentos seleccionados`}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {/* Botón para Iniciar Nueva Conversación / Limpiar Contexto */}
          <button
            onClick={handleNewConversation}
            className="text-xs px-3 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-300 hover:text-zinc-100 hover:bg-zinc-800 hover:border-zinc-700 transition-all duration-150 flex items-center gap-1.5 font-medium cursor-pointer shadow-sm"
            title="Iniciar una conversación nueva con contexto limpio"
          >
            <PlusCircle className="h-3.5 w-3.5 text-blue-400" />
            <span>Nueva Consulta</span>
          </button>

          {/* Botón Global para Activar / Desactivar Resaltado de Citas */}
          <button
            onClick={onToggleHighlight}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all duration-150 flex items-center gap-1.5 font-semibold cursor-pointer ${
              highlightEnabled
                ? "bg-amber-500/20 border-amber-500/50 text-amber-300 hover:bg-amber-500/30 shadow-sm shadow-amber-500/10"
                : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            }`}
            title={
              highlightEnabled
                ? "Desactivar resaltado automático de citas en el PDF"
                : "Activar resaltado automático de citas en el PDF"
            }
          >
            <Sparkles
              className={`h-3.5 w-3.5 ${
                highlightEnabled
                  ? "text-amber-400 animate-pulse"
                  : "text-zinc-500"
              }`}
            />
            <span>
              Resaltar Citas: {highlightEnabled ? "ON" : "OFF"}
            </span>
          </button>

          {selectedDocIds.length > 0 && (
            isFirstYt ? (
              <button
                onClick={() => {
                  const ytUrl = firstSelectedDoc?.file_path || `https://www.youtube.com/watch?v=${selectedDocIds[0]}`;
                  window.open(ytUrl, "_blank");
                }}
                className="flex items-center gap-1.5 text-xs bg-red-950/40 border border-red-900/60 hover:bg-red-900/40 text-red-300 hover:text-red-100 px-3 py-1.5 rounded-lg transition-colors font-medium shadow-sm cursor-pointer"
                title="Abrir videotutorial en YouTube"
              >
                <Play className="h-3.5 w-3.5 text-red-400" />
                <span>{selectedDocIds.length === 1 ? "Ver tutorial en YouTube" : "Ver primer tutorial"}</span>
                <ExternalLink className="h-3 w-3 opacity-70" />
              </button>
            ) : (
              <button
                onClick={() =>
                  onOpenPdf(selectedDocIds[0], selectedFilenames[0], 1)
                }
                className="flex items-center gap-1.5 text-xs bg-zinc-900 border border-zinc-800/80 hover:bg-zinc-800 text-zinc-300 hover:text-zinc-100 px-3 py-1.5 rounded-lg transition-colors font-medium shadow-sm cursor-pointer"
                title="Visualizar el documento PDF seleccionado"
              >
                <FileText className="h-3.5 w-3.5 text-blue-400" />
                {selectedDocIds.length === 1
                  ? "Ver documento"
                  : "Ver primer documento"}
              </button>
            )
          )}
        </div>
      </div>

      {/* Historial de Mensajes */}
      <div className="flex-1 overflow-y-auto p-8 space-y-6">
        <div className="max-w-3xl mx-auto space-y-6">

          {messages.map((msg, index) => {
            const isBot = msg.sender === "bot";

            return (
              <div
                key={msg.id}
                className={`flex gap-4 ${
                  isBot ? "justify-start" : "justify-end"
                }`}
              >

                {/* Avatar */}
                {isBot && (
                  <div className="h-8 w-8 rounded-lg bg-blue-950/50 border border-blue-500/20 flex items-center justify-center shrink-0">
                    <Bot className="h-4 w-4 text-blue-400" />
                  </div>
                )}

                <div className="max-w-xl space-y-3 min-w-0">

                  {/* Burbuja de Texto */}
                  <div
                    className={`rounded-2xl px-5 py-4 text-sm leading-relaxed border ${
                      isBot
                        ? "bg-zinc-900/40 border-zinc-800/80 text-zinc-200 shadow-md shadow-zinc-950/25"
                        : "bg-blue-600 border-blue-500 text-white font-medium shadow-md shadow-blue-950/25"
                    }`}
                  >
                    {isBot
                      ? renderFormattedText(msg.text, msg.sources)
                      : msg.text}
                  </div>

                  {/* Latencias */}
                  {isBot && msg.latencyMs && (
                    <LatencyDisplay
                      latencies={msg.latencyMs}
                      cragStatus={msg.cragStatus || ""}
                    />
                  )}

                </div>

                {/* Avatar del Usuario */}
                {!isBot && (
                  <div className="h-8 w-8 rounded-lg bg-zinc-850 border border-zinc-700 flex items-center justify-center shrink-0">
                    <User className="h-4 w-4 text-zinc-300" />
                  </div>
                )}
              </div>
            );
          })}

          {/* Tarjetas de Preguntas Frecuentes (FAQs) */}
          {messages.length === 1 && messages[0].id === "welcome" && !loading && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 max-w-2xl mx-auto">
              {(faqs.length > 0 ? faqs : [
                { text: "¿Cómo realizo el cierre de ejercicio contable?", desc: "Procedimientos de cierre y apertura de la contabilidad." },
                { text: "¿Qué requisitos tiene la Ley de Fraude Fiscal / Veri*factu?", desc: "Cambios en series, firmas digitales y firmas de registros." },
                { text: "¿Cómo hago una copia de seguridad interna?", desc: "Resguardar la base de datos de la empresa de forma local." },
                { text: "¿Cómo configuro el límite de registros en los GRID?", desc: "Optimizar la visualización de registros en las rejillas." }
              ]).map((faq, fIdx) => (
                <button
                  key={fIdx}
                  onClick={() => handleSend(undefined, faq.text)}
                  disabled={loading}
                  className="bg-zinc-900/60 border border-zinc-800/80 hover:bg-zinc-850 hover:border-blue-500/50 disabled:hover:bg-zinc-900/60 disabled:hover:border-zinc-800/80 disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none text-zinc-300 hover:text-zinc-100 rounded-xl p-4 transition-all duration-200 cursor-pointer shadow-sm text-left flex flex-col gap-1 group active:scale-[0.98] outline-none"
                >
                  <span className="font-semibold text-xs text-blue-400 group-hover:text-blue-300 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-blue-500 group-hover:animate-pulse" />
                    Pregunta sugerida
                  </span>
                  <span className="font-medium text-sm mt-0.5 leading-snug">{faq.text}</span>
                  <span className="text-[11px] text-zinc-500 group-hover:text-zinc-400 mt-1 leading-normal">{faq.desc}</span>
                </button>
              ))}
            </div>
          )}

          {/* Loader del Bot */}
          {loading && (
            <div className="flex gap-4 justify-start">

              <div className="h-8 w-8 rounded-lg bg-blue-950/50 border border-blue-500/20 flex items-center justify-center shrink-0">
                <Bot className="h-4 w-4 text-blue-400" />
              </div>

              <div className="max-w-xl space-y-3">

                <div className="rounded-2xl px-5 py-4 border bg-zinc-900/40 border-zinc-800/80 text-zinc-400 text-sm">

                  <div className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />
                    <span>
                      Consultando motor CRAG y generando respuesta...
                    </span>
                  </div>

                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="max-w-xl mx-auto my-4 bg-red-950/20 border border-red-900/50 p-4 rounded-xl flex items-center gap-3 text-red-400 text-sm">
              <AlertCircle className="h-5 w-5 shrink-0" />

              <div>
                <p className="font-semibold">
                  Error al obtener respuesta
                </p>

                <p className="text-xs text-red-500/90 mt-0.5">
                  {error}
                </p>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>
      </div>

      {/* Input de Chat */}
      <div className="p-8 border-t border-zinc-800/80 bg-zinc-950/10">

        <form
          onSubmit={handleSend}
          className="max-w-3xl mx-auto relative"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            placeholder={
              selectedFilenames.length === 0
                ? "Pregunta sobre la documentación indexada..."
                : selectedFilenames.length === 1
                ? `Pregunta sobre ${selectedFilenames[0]}...`
                : `Pregunta sobre los ${selectedFilenames.length} PDFs seleccionados...`
            }
            className="w-full bg-zinc-900/50 hover:bg-zinc-900/70 focus:bg-zinc-900/80 text-zinc-100 placeholder-zinc-500 text-sm rounded-2xl pl-5 pr-14 py-4 border border-zinc-800 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all duration-300 shadow-inner"
          />
<button
  type="submit"
  disabled={!input.trim() || loading}
  className="absolute right-3.5 top-3.5 p-2 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-850 disabled:text-zinc-600 text-white transition-all duration-300 shadow-md shadow-blue-950/30"
>
  <Send className="h-4 w-4 text-white" />
</button>
        </form>

        <p className="text-[10px] text-zinc-600 text-center mt-3">
          Respuestas formuladas usando Corrective RAG (CRAG) con búsqueda híbrida y re-ranking local.
        </p>

      </div>
    </section>
  );
}