"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export default function ConceptSection() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const subRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(labelRef.current, { opacity: 0, y: 20 }, {
        opacity: 1, y: 0, duration: 0.8, ease: "power3.out",
        scrollTrigger: { trigger: sectionRef.current, start: "top 75%" }
      });
      gsap.fromTo(headingRef.current, { opacity: 0, y: 50 }, {
        opacity: 1, y: 0, duration: 1.4, ease: "power3.out",
        scrollTrigger: { trigger: sectionRef.current, start: "top 70%" }
      });
      gsap.fromTo(subRef.current, { opacity: 0, y: 30 }, {
        opacity: 1, y: 0, duration: 1, ease: "power3.out", delay: 0.3,
        scrollTrigger: { trigger: sectionRef.current, start: "top 65%" }
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <section id="concept" ref={sectionRef} className="py-32 md:py-48 px-6 md:px-12 border-t border-white/5">
      <div className="max-w-[1400px] mx-auto">
        <span ref={labelRef} className="sd-label block mb-8 opacity-0">Concept</span>
        <h2 ref={headingRef} className="sd-headline-mid max-w-4xl mb-12 opacity-0">
          Grounded detection, structured storage, provable retrieval.
        </h2>
        <p ref={subRef} className="sd-body-large max-w-3xl opacity-0">
          Every object gets a real bounding box. Every color is read from actual pixels.
          Every spatial relation is computed from geometry. Nothing is guessed. Everything is proven.
          <br /><br />
          <span className="text-cream-400 font-serif italic text-lg">
            Об'єкти, кольори, просторові відносини — все реальне, все перевірене.
          </span>
        </p>
      </div>
    </section>
  );
}
