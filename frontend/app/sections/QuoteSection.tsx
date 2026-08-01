"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export default function QuoteSection() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (!textRef.current) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        textRef.current,
        { opacity: 0, y: 60 },
        {
          opacity: 1,
          y: 0,
          duration: 1.4,
          ease: "power3.out",
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 70%",
            toggleActions: "play none none none",
          },
        }
      );
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-40 md:py-56 px-6 md:px-12">
      <div className="max-w-[1400px] mx-auto">
        <p
          ref={textRef}
          className="font-serif text-3xl md:text-5xl lg:text-6xl font-normal italic leading-snug text-cream-100 max-w-5xl opacity-0"
        >
          "Type what happened, we'll show you exactly where — and prove it."
        </p>
        <div className="mt-12 flex items-center gap-4">
          <div className="w-12 h-px bg-cream-700" />
          <span className="sd-label">Ask-N-Seek</span>
        </div>
      </div>
    </section>
  );
}
