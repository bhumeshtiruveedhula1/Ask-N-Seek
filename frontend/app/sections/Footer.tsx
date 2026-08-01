"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export default function Footer() {
  const sectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(sectionRef.current, { opacity: 0, y: 40 }, {
        opacity: 1, y: 0, duration: 1.2, ease: "power3.out",
        scrollTrigger: { trigger: sectionRef.current, start: "top 80%" }
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <footer ref={sectionRef} className="py-32 md:py-48 px-6 md:px-12 border-t border-white/5">
      <div className="max-w-[1400px] mx-auto">
        <h2 className="sd-headline-mid text-cream-100 mb-12">
          From query
          <br />
          <span className="text-cream-400 italic">to proof.</span>
        </h2>
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
          <p className="sd-body text-sm max-w-md">
            Ask-N-Seek v2.3 · Built for Hackathon · YOLO-World · Qdrant · spaCy
          </p>
          <span className="sd-label">Natural Language Video Retrieval</span>
        </div>
      </div>
    </footer>
  );
}
