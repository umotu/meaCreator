// file: src/components/MacHero.tsx
import * as React from "react";
import Typewriter from "./Typewriter";

export default function MacHero(): JSX.Element {
  const phrases = [
    "On-demand, fully customizable activities for teachers and curriculum developers.",
    "Project-based learning activity generator and curriculum expert.",
    "Designed by a team of PhD experts in learning and model-eliciting activities.",
    "Activities personalized to student interests, languages, and culture.",
  ];

  return (
    <section className="min-h-[70vh] grid place-content-center">
      <div className="w-full max-w-5xl px-6 md:pl-28">
        <h1 className="text-6xl md:text-7xl font-extrabold tracking-tight">
          MAC:
        </h1>
        <Typewriter
          phrases={phrases}
          prefix=">>> "
          typingSpeedMs={42}
          deletingSpeedMs={24}
          pauseBeforeDeleteMs={1200}
          pauseBetweenPhrasesMs={250}
          startDelayMs={300}
          loop
          className="mt-4 text-2xl md:text-3xl leading-snug text-left"
          ariaLabel="MAC product value statements"
        />
      </div>
    </section>
  );
}