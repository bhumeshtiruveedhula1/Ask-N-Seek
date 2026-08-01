"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";

export default function Hero() {
  const containerRef = useRef<HTMLDivElement>(null);
  const line1Ref = useRef<HTMLDivElement>(null);
  const line2Ref = useRef<HTMLDivElement>(null);
  const line3Ref = useRef<HTMLDivElement>(null);
  const subRef = useRef<HTMLDivElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const tl = gsap.timeline({ delay: 0.3 });
    tl.fromTo(line1Ref.current, { y: 100, opacity: 0 }, { y: 0, opacity: 1, duration: 1.2, ease: "power3.out" })
      .fromTo(line2Ref.current, { y: 100, opacity: 0 }, { y: 0, opacity: 1, duration: 1.2, ease: "power3.out" }, "-=0.9")
      .fromTo(line3Ref.current, { y: 100, opacity: 0 }, { y: 0, opacity: 1, duration: 1.2, ease: "power3.out" }, "-=0.9")
      .fromTo(subRef.current, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 1, ease: "power3.out" }, "-=0.6")
      .fromTo(ctaRef.current, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 1, ease: "power3.out" }, "-=0.8");
    return () => { tl.kill(); };
  }, []);

  return (
    <section ref={containerRef} className="min-h-screen flex flex-col justify-center px-6 md:px-12 pt-24 relative overflow-hidden">
      <div className="max-w-[1400px] mx-auto w-full">
        <div className="overflow-hidden mb-2">
          <div ref={line1Ref} className="opacity-0">
            <span className="sd-label block mb-8">Natural Language Video Retrieval</span>
          </div>
        </div>

        <div className="overflow-hidden">
          <h1 ref={line2Ref} className="sd-headline opacity-0">
            Ask-N-Seek
          </h1>
        </div>

        <div className="overflow-hidden mt-4">
          <h2 ref={line3Ref} className="sd-headline-italic opacity-0 text-cream-400">
            Find anything in video.
          </h2>
        </div>

        <div ref={subRef} className="opacity-0 mt-16 max-w-xl">
          <p className="sd-body-large">
            Drop any video. Describe what you are looking for in plain English.
            We detect every object, read every color, compute spatial relations —
            and prove exactly why each result matched.
          </p>
        </div>

        <div ref={ctaRef} className="opacity-0 mt-12 flex items-center gap-8">
          <a href="#demo" className="group inline-flex items-center gap-3">
            <span className="sd-label text-cream-100 group-hover:text-sand transition-colors duration-500">Try the demo</span>
            <span className="text-cream-100 group-hover:translate-x-1 transition-transform duration-500">→</span>
          </a>
          <a href="#about" className="sd-label hover:text-cream-100 transition-colors duration-500">Learn more ↓</a>
        </div>
      </div>
    </section>
  );
}
