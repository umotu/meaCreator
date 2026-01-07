import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import "./App.css";
import MacHero from "./components/MacHero";
import Typewriter from "./components/Typewriter";

type Role = "user" | "assistant";

interface ChatMessage {
  id: string;
  role: Role;
  content: string;
}
/*
interface ChatResponse {
  reply: string;
}
*/
// Dec 1 replacement for traces       
interface TraceEvent {
  label: string;
  detail: string;
  timestamp: string;
}

interface ChatResponse {
  reply: string;
  trace?: TraceEvent[];
}


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8010";

/* ---------- Markdown helpers for PDF ---------- */

const isTableRow = (line: string): boolean => {
  return /^\s*\|.+\|\s*$/.test(line.trim());
};

const isSeparatorRow = (line: string): boolean => {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|")) return false;
  const cells = trimmed
    .slice(1, trimmed.endsWith("|") ? -1 : undefined)
    .split("|")
    .map((c) => c.trim());
  return cells.every((c) => /^:?-{3,}:?$/.test(c));
};

const parseRow = (line: string): string[] => {
  const trimmed = line.trim();
  const core = trimmed.replace(/^\|/, "").replace(/\|$/, "");
  return core.split("|").map((cell) => cell.trim());
};

// Strip markdown for PDF (headings, bullets, bold/italic, inline code)
const stripMdFormatting = (text: string): string => {
  let s = text;

  // Headings like "### Title" at the start of ANY line
  s = s.replace(/^#{1,6}\s+/gm, "");

  // Bullets and numbered list prefixes at line start
  s = s.replace(/^\s*[-*+]\s+/gm, "");
  s = s.replace(/^\s*\d+\.\s+/gm, "");

  // Bold / italic
  s = s.replace(/\*\*(.+?)\*\*/g, "$1");
  s = s.replace(/__(.+?)__/g, "$1");
  s = s.replace(/\*(.+?)\*/g, "$1");
  s = s.replace(/_(.+?)_/g, "$1");

  // Inline code
  s = s.replace(/`([^`]+)`/g, "$1");

  return s;
};

// Extract [TAG]...[/TAG] (case-insensitive, flexible)
const extractTaggedSection = (full: string, tag: string): string | null => {
  const re = new RegExp(`\\[${tag}\\s*\\]([\\s\\S]*?)\\[\\/${tag}\\s*\\]`, "i");
  const match = full.match(re);
  if (!match) return null;
  return match[1].trim();
};

// Strip special tags like [STUDENT_PAGES] from the content before rendering
const stripCustomTags = (text: string): string => {
  let s = text;
  // Use a single regex for efficiency
  s = s.replace(/\[\/?(STUDENT_PAGES|TEACHER_PAGES|PAGE_BREAK)\s*\]/gi, "");
  return s.trim();
};

/* ------------------------------------------------ */

function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }, [input]);

  const handleSubmit = async (
    event?: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    if (event) {
      event.preventDefault();
    }
    const trimmed = input.trim();
    if (!trimmed || isSending) return;

    const userMessage: ChatMessage = {
      id: `${Date.now().toString()}-${Math.random()
        .toString(36)
        .slice(2)}`,
      role: "user",
      content: trimmed,
    };

    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInput("");
    setIsSending(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          messages: newMessages.map(({ role, content }) => ({
            role,
            content,
          })),
        }),
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data: ChatResponse = await response.json();

      // If we got a trace, turn it into a special "thinking" message first
      if (data.trace && data.trace.length > 0) {
        const traceText = data.trace
          .map(
            (ev) =>
              `• [${new Date(ev.timestamp).toLocaleTimeString()}] ${ev.label}: ${
                ev.detail
              }`
          )
          .join("\n");

        const traceMessage: ChatMessage = {
          id: `${Date.now().toString()}-trace`,
          role: "assistant",
          content: `**Thinking trace**:\n\n${traceText}`,
        };

        setMessages((prev) => [...prev, traceMessage]);
      }

      // Then add the actual assistant reply
      const assistantMessage: ChatMessage = {
        id: `${Date.now().toString()}-${Math.random().toString(36).slice(2)}`,
        role: "assistant",
        content: data.reply,
      };

      setMessages((prev) => [...prev, assistantMessage]);

      // previously was just this, updated on Dec 1

      /*
      const assistantMessage: ChatMessage = {
        id: `${Date.now().toString()}-${Math.random()
          .toString(36)
          .slice(2)}`,
        role: "assistant",
        content: data.reply,
      };

      setMessages((prev) => [...prev, assistantMessage]);  */

    } catch (err: any) {
      console.error(err);
      setError(err.message || "Something went wrong");
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (
    event: React.KeyboardEvent<HTMLTextAreaElement>
  ): void => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!isSending && input.trim()) {
        void handleSubmit();
      }
    }
  };

  /* ---------- PDF export core (markdown → text + tables) ---------- */

  const exportMarkdownToPdf = (
    raw: string,
    title: string,
    filename: string,
    options?: { forceStudentPageBreaks?: boolean }
  ): void => {
    const forceStudentPageBreaks = options?.forceStudentPageBreaks ?? false;

    const doc = new jsPDF("p", "mm", "a4");
    const marginX = 10;
    const marginY = 15;
    const lineHeight = 6;

    let y = marginY;

    const getPageSize = () => {
      const pageWidth = doc.internal.pageSize.getWidth();
      const pageHeight = doc.internal.pageSize.getHeight();
      return { pageWidth, pageHeight };
    };

    const { pageWidth, pageHeight } = getPageSize();
    const maxWidth = pageWidth - marginX * 2;

    const ensureSpace = (needed = lineHeight) => {
      const { pageHeight } = getPageSize();
      if (y + needed > pageHeight - marginY) {
        doc.addPage();
        y = marginY;
      }
    };

    // Title
    doc.setFontSize(14);
    doc.setFont("helvetica", "bold");
    doc.text(stripMdFormatting(title || "MEA Materials"), marginX, y);
    y += lineHeight * 1.5;

    doc.setFontSize(10);
    doc.setFont("helvetica", "normal");

    const addParagraph = (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      const cleaned = stripMdFormatting(trimmed);

      // TS: splitTextToSize is typed as string | string[], cast to string[]
      const wrappedLines = doc.splitTextToSize(cleaned, maxWidth) as string[];

      wrappedLines.forEach((ln) => {
        ensureSpace();
        doc.text(ln, marginX, y);
        y += lineHeight;
      });
    };

    const lines = raw.split(/\r?\n/);
    let buffer: string[] = [];
    let i = 0;

    const flushBuffer = () => {
      if (buffer.length === 0) return;
      addParagraph(buffer.join("\n"));
      buffer = [];
      y += lineHeight * 0.5;
    };

    while (i < lines.length) {
      const line = lines[i];
      const trimmedLine = line.trim();

      // Hard page breaks for student pages
      if (
        forceStudentPageBreaks &&
        /^\[PAGE_BREAK\]$/i.test(trimmedLine)
      ) {
        flushBuffer();
        doc.addPage();
        y = marginY;
        i++;
        continue;
      }

      // Tables
      if (
        isTableRow(line) &&
        i + 1 < lines.length &&
        isSeparatorRow(lines[i + 1])
      ) {
        flushBuffer();

        const headerLine = lines[i];
        const sepLine = lines[i + 1];
        const tableLines = [headerLine, sepLine];
        i += 2;

        while (i < lines.length && isTableRow(lines[i])) {
          tableLines.push(lines[i]);
          i++;
        }

        const header = parseRow(tableLines[0]).map(stripMdFormatting);
        const body = tableLines
          .slice(2)
          .map(parseRow)
          .map((row) => row.map(stripMdFormatting))
          .filter((row) => row.some((cell) => cell.length > 0));

        ensureSpace(lineHeight * 3);

        autoTable(doc, {
          head: [header],
          body,
          startY: y,
          margin: { left: marginX, right: marginX },
          styles: {
            fontSize: 9,
          },
          headStyles: {
            fontStyle: "bold",
          },
          theme: "grid",
        });

        // @ts-expect-error - jspdf-autotable attaches lastAutoTable
        y = doc.lastAutoTable.finalY + lineHeight;
      } else {
        buffer.push(line);
        i++;
      }
    }

    flushBuffer();

    // Add page numbers
    const pageCount = doc.getNumberOfPages();
    doc.setFontSize(9);
    doc.setFont("helvetica", "normal");

    for (let page = 1; page <= pageCount; page++) {
      doc.setPage(page);
      const { pageWidth, pageHeight } = getPageSize();
      const label = `Page ${page} / ${pageCount}`;
      doc.text(label, pageWidth - marginX, pageHeight - 8, {
        align: "right",
      });
    }

    doc.save(filename);
  };

  /* ---------- PDF export handlers (student vs teacher) ---------- */

  const getLastAssistantMessage = (): ChatMessage | null => {
    const reversed = [...messages].reverse();
    return reversed.find((m) => m.role === "assistant") ?? null;
  };

  const handleDownloadStudentPdf = (): void => {
    const lastAssistant = getLastAssistantMessage();
    if (!lastAssistant) {
      setError("No assistant response to export yet.");
      return;
    }

    const studentSection =
      extractTaggedSection(lastAssistant.content, "STUDENT_PAGES") ||
      lastAssistant.content;

    exportMarkdownToPdf(
      studentSection,
      "Student MEA Materials",
      "mea-student.pdf",
      { forceStudentPageBreaks: true }
    );
  };

  const handleDownloadTeacherPdf = (): void => {
    const lastAssistant = getLastAssistantMessage();
    if (!lastAssistant) {
      setError("No assistant response to export yet.");
      return;
    }

    const raw = lastAssistant.content;

    // Ideal path: we have a dedicated [TEACHER_PAGES] block
    const teacherBlock = extractTaggedSection(raw, "TEACHER_PAGES");

    let contentToUse: string;

    if (teacherBlock) {
      contentToUse = teacherBlock;
    } else {
      // Fallback: remove any [STUDENT_PAGES]...[/STUDENT_PAGES] block,
      // and use what remains as "teacher-ish" content.
      const withoutStudent = raw
        .replace(/\[STUDENT_PAGES\s*\][\s\S]*?\[\/STUDENT_PAGES\s*\]/i, "")
        .trim();

      contentToUse = withoutStudent || raw;
    }

    exportMarkdownToPdf(
      contentToUse,
      "Teacher MEA Materials",
      "mea-teacher.pdf",
      { forceStudentPageBreaks: false }
    );
  };

  /* -------------------------------------------------------------- */

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="brand">
            <div className="brand-logo">◎</div>
            <span className="brand-name">MAC</span>
          </div>
          <nav className="nav">
            <button className="nav-item nav-item-active">Chat</button>
            <button className="nav-item">History</button>
            <button className="nav-item">Settings</button>
            {/* Header-level PDF buttons */}
            <button className="nav-item" onClick={handleDownloadStudentPdf}>
              Student PDF
            </button>
            <button className="nav-item" onClick={handleDownloadTeacherPdf}>
              Teacher PDF
            </button>
          </nav>
        </div>
      </header>

      <main className="app-main">
        <div className="chat-layout">
          <aside className="sidebar">
            <div className="sidebar-header">Conversations</div>
            <button className="sidebar-new">+ New chat</button>
            <div className="sidebar-empty">Conversation list goes here.</div>
          </aside>

          <section className="chat-panel">
            <div className="chat-messages">
              {messages.length === 0 && (
                <div className="chat-empty">
                    <h1 style={{ margin: 0, fontSize: "clamp(28px, 4vw, 40px)" }}>Modeling Activity Creator</h1>
                    <div className="tabbed-left">
                      <Typewriter
                        className="chat-empty-typed"
                        ariaLabel="MAC product value statements"
                        prefix=""
                        phrases={[
                          "On-demand, fully customizable activities for teachers and curriculum developers.",
                          "Project-based learning activity generator and curriculum expert.",
                          "Designed by a team of PhD experts in learning and model-eliciting activities.",
                          "Activities personalized to student interests, languages, and culture.",
                        ]}
                      />
                    </div>
                
                </div>
              )}

              {messages.map((message, index) => (
                <div
                  key={message.id}
                  className={`message-row message-row-${message.role}`}
                >
                  <div className="message-avatar">
                    {message.role === "assistant" ? "🤖" : "🧑"}
                  </div>
                  <div className="message-bubble">
                    <div className="message-role">
                      {message.role === "assistant" ? "Assistant" : "You"}
                    </div>
                    <div className="message-content markdown-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {message.role === "assistant"
                          ? stripCustomTags(message.content)
                          : message.content}
                      </ReactMarkdown>

                      {/* Inline chips on the LAST assistant message */}
                      {message.role === "assistant" &&
                        index === messages.length - 1 && (
                          <div className="message-download">
                            <button
                              type="button"
                              className="download-chip"
                              onClick={handleDownloadStudentPdf}
                            >
                              ⬇️ Student PDF
                            </button>
                            <button
                              type="button"
                              className="download-chip"
                              onClick={handleDownloadTeacherPdf}
                            >
                              ⬇️ Teacher PDF
                            </button>
                          </div>
                        )}
                    </div>
                  </div>
                </div>
              ))}

              {isSending && (
                <div className="message-row message-row-assistant">
                  <div className="message-avatar">🤖</div>
                  <div className="message-bubble">
                    <div className="message-role">Assistant</div>
                    <div className="message-content message-typing">
                      <span className="dot" />
                      <span className="dot" />
                      <span className="dot" />
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            <div className="chat-input-wrapper">
              {error && (
                <div className="error-banner">
                  {error}
                  <button
                    className="error-close"
                    onClick={() => setError(null)}
                  >
                    ×
                  </button>
                </div>
              )}

              <form className="chat-input-bar" onSubmit={handleSubmit}>
                <textarea
                  ref={textareaRef}
                  className="chat-textarea"
                  placeholder="Name a topic to learn and describe the learners, or ask for guidance..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                />
                <button
                  type="submit"
                  className="send-button"
                  disabled={isSending || !input.trim()}
                  aria-label="Send message"
                >
                  ➤
                </button>
              </form>

              <div className="chat-footer-hint">
                Press <kbd>Enter</kbd> to send, <kbd>Shift</kbd> +{" "}
                <kbd>Enter</kbd> for a new line.
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
