// file: src/components/Typewriter.tsx
import * as React from "react";

export type TypewriterProps = {
  phrases: string[];
  prefix?: string;
  typingSpeedMs?: number;               // slower → larger
  deletingSpeedMs?: number;             // slower → larger
  pauseBeforeDeleteMs?: number;    // pause when a phrase finishes typing
  pauseBetweenPhrasesMs?: number;  // pause between normal phrases
  restartDelayMs?: number;         // extra pause when looping (last → first)
  startDelayMs?: number;
  loop?: boolean;
  align?: "left" | "center" | "right";
  showCaret?: boolean;
  className?: string;
  ariaLabel?: string;
};

export default function Typewriter({
  phrases,
  prefix = "",
  typingSpeedMs = 42,
  deletingSpeedMs = 24,
  pauseBeforeDeleteMs = 1200,
  pauseBetweenPhrasesMs = 250,
  restartDelayMs = 1500,           // ← pause before it starts over
  startDelayMs = 300,
  loop = true,
  align = "left",
  showCaret = false,
  className,
  ariaLabel,
}: TypewriterProps): JSX.Element {
  const [phraseIdx, setPhraseIdx] = React.useState(0);
  const [charIdx, setCharIdx] = React.useState(0);
  const [deleting, setDeleting] = React.useState(false);
  const timerRef = React.useRef<number | null>(null);

  const prefersReduced = React.useMemo(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }, []);

  // Clear timer helper
  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  // Pause when tab not visible
  React.useEffect(() => {
    const onVis = () => {
      if (document.hidden) clearTimer();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  // Core animation loop
  React.useEffect(() => {
    if (!phrases.length) return;
    clearTimer();

    // Reduced motion: just rotate phrases with pauses, honoring restartDelayMs on wrap
    if (prefersReduced) {
      const isLast = phraseIdx === phrases.length - 1;
      const delay = isLast ? restartDelayMs : pauseBeforeDeleteMs + pauseBetweenPhrasesMs;
      timerRef.current = window.setTimeout(() => {
        setPhraseIdx((i) => {
          const next = i + 1;
          if (next >= phrases.length) return loop ? 0 : i;
          return next;
        });
      }, delay);
      return () => clearTimer();
    }

    if (typeof document !== "undefined" && document.hidden) return;

    const current = phrases[phraseIdx] ?? "";
    const atEnd = charIdx === current.length;
    const atStart = charIdx === 0;

    // Finished typing the current phrase → pause, then start deleting
    if (!deleting && atEnd) {
      timerRef.current = window.setTimeout(() => setDeleting(true), pauseBeforeDeleteMs);
      return () => clearTimer();
    }

    // Finished deleting → advance to next phrase (with extra pause on wrap)
    if (deleting && atStart) {
      const isLast = phraseIdx === phrases.length - 1;
      const delay = isLast ? restartDelayMs : pauseBetweenPhrasesMs;
      timerRef.current = window.setTimeout(() => {
        setDeleting(false);
        setPhraseIdx((i) => {
          const next = i + 1;
          if (next >= phrases.length) return loop ? 0 : i;
          return next;
        });
      }, delay);
      return () => clearTimer();
    }

    // Normal per-character tick
    const delay = deleting
      ? deletingSpeedMs
      : charIdx === 0
      ? startDelayMs
      : typingSpeedMs;

    timerRef.current = window.setTimeout(() => {
      setCharIdx((c) => (deleting ? Math.max(0, c - 1) : Math.min(current.length, c + 1)));
    }, delay);

    return () => clearTimer();
  }, [
    phrases,
    phraseIdx,
    charIdx,
    deleting,
    typingSpeedMs,
    deletingSpeedMs,
    pauseBeforeDeleteMs,
    pauseBetweenPhrasesMs,
    restartDelayMs,
    startDelayMs,
    loop,
    prefersReduced,
  ]);

  // Reset typing index when phrase changes
  React.useEffect(() => {
    setCharIdx(0);
  }, [phraseIdx]);

  const visible = prefersReduced
    ? (phrases[phraseIdx] ?? "")
    : (phrases[phraseIdx] ?? "").slice(0, charIdx);

  if (!phrases.length) {
    return <></>;
  }

  return (
    <div
      className={className}
      role="status"
      aria-live="polite"
      aria-label={ariaLabel ?? "Animated headline"}
      style={{ textAlign: align }}
    >
      {prefix ? <span style={{ opacity: 0.7 }}>{prefix}</span> : null}
      <span>{visible}</span>
      {showCaret ? (
        <span
          aria-hidden
          style={{
            display: "inline-block",
            width: 1,
            height: "1em",
            marginLeft: 4,
            background: "currentColor",
            verticalAlign: "baseline",
            animation: "tpulse 1s steps(1) infinite",
          }}
        />
      ) : null}
      <style>{`@keyframes tpulse {0%,49%{opacity:1}50%,100%{opacity:0}}`}</style>
    </div>
  );
}

// file: src/App.tsx (snippet — how to use slower, left-justified, with loop pause)
// ...
// import Typewriter from "./components/Typewriter";
// ...
// {messages.length === 0 && (
//   <div className="chat-empty">
//     <h1 style={{ margin: 0, fontSize: "clamp(28px,4vw,40px)" }}>MAC:</h1>
//     <Typewriter
//       align="left"                // ← left-justified
//       typingMs={90}               // ← slower typing
//       deletingMs={50}             // ← slower deleting
//       pauseBeforeDeleteMs={1500}  // ← pause after fully typed
//       pauseBetweenPhrasesMs={500} // ← pause between normal phrases
//       restartDelayMs={2000}       // ← extra pause before starting over
//       phrases={[
//         "On-demand, fully customizable activities for teachers and curriculum developers.",
//         "Project-based learning activity generator and curriculum expert.",
//         "Designed by a team of PhD experts in learning and model-eliciting activities.",
//         "Activities personalized to student interests, languages, and culture.",
//       ]}
//     />
//   </div>
// )}
// ...

// file: src/App.css (optional — ensure empty-state is not center-justifying)
// .chat-empty { text-align: left; }
// .chat-empty-typed { text-align: left; }
