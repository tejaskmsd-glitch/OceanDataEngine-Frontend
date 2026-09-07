"use client";

import { useEffect, useState } from "react";

const PHRASES = [
  "Explore the Ocean",
  "Explore Marine Data",
  "Explore the Indian Ocean",
  "Discover Marine Insights",
];

const TYPING_SPEED_MS = 80;
const COMPLETED_PAUSE_MS = 2000;
const DELETING_SPEED_MS = 45;
const NEXT_PHRASE_PAUSE_MS = 400;

export function TypingHeading() {
  const [phraseIndex, setPhraseIndex] = useState(0);
  const [charIndex, setCharIndex] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isPaused, setIsPaused] = useState(false);

  useEffect(() => {
    // Respect accessibility motion preferences
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setCharIndex(PHRASES[0].length);
      return;
    }

    const currentPhrase = PHRASES[phraseIndex];
    let timer: NodeJS.Timeout;

    if (isPaused) {
      // Completed phrase pause: wait ~2000ms before deleting
      timer = setTimeout(() => {
        setIsPaused(false);
        setIsDeleting(true);
      }, COMPLETED_PAUSE_MS);
    } else if (isDeleting) {
      if (charIndex > 0) {
        // Erase character by character
        timer = setTimeout(() => {
          setCharIndex((prev) => prev - 1);
        }, DELETING_SPEED_MS);
      } else {
        // Fully erased: pause briefly (~400ms) before starting next phrase
        timer = setTimeout(() => {
          setIsDeleting(false);
          setPhraseIndex((prev) => (prev + 1) % PHRASES.length);
        }, NEXT_PHRASE_PAUSE_MS);
      }
    } else {
      // Typing phase
      if (charIndex < currentPhrase.length) {
        // Type next character
        timer = setTimeout(() => {
          setCharIndex((prev) => prev + 1);
        }, TYPING_SPEED_MS);
      } else {
        // Completed typing full phrase: pause
        setIsPaused(true);
      }
    }

    return () => clearTimeout(timer);
  }, [charIndex, isDeleting, isPaused, phraseIndex]);

  const currentPhrase = PHRASES[phraseIndex];
  const displayed = currentPhrase.slice(0, charIndex);

  return (
    <>
      {/* Screen reader complete title accessibility */}
      <span className="sr-only" aria-live="polite">
        {currentPhrase}
      </span>

      {/* Visual typewriter container reserving space to prevent vertical layout shift */}
      <span aria-hidden="true" className="grid grid-cols-1 grid-rows-1 justify-items-center items-center w-full">
        {/* Invisible ghosts for all phrases guaranteeing constant height & width */}
        {PHRASES.map((phrase, i) => (
          <span
            key={i}
            className="col-start-1 row-start-1 invisible select-none pointer-events-none"
            aria-hidden="true"
          >
            {phrase}
          </span>
        ))}

        {/* Active visible typed phrase with baseline-aligned inline cursor */}
        <span className="col-start-1 row-start-1">
          <span>{displayed}</span>
          <span
            className={`inline-block w-[2px] h-[0.82em] align-baseline bg-[#F4F7F5]/75 rounded-[1px] animate-pulse pointer-events-none ${
              displayed.length > 0 ? "ml-1 sm:ml-1.5" : ""
            }`}
            aria-hidden="true"
          />
        </span>
      </span>
    </>
  );
}
