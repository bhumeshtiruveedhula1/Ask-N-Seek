"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const FACTS = [
  { num: "800+", label: "Object Classes", desc: "YOLO-World vocabulary" },
  { num: "0.3s", label: "Query Time", desc: "Rule-based parser + Qdrant" },
  { num: "30s", label: "Ingest Time", desc: "3-minute 1080p video" },
  { num: "98%", label: "Test Pass Rate", desc: "Zero regressions" },
];

export default function InfrastructureGrid() {
  const sectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(".infra-item", { opacity: 0, y: 50 }, {
        opacity: 1, y: 0, duration: 1, stagger: 0.15, ease: "power3.out",
        scrollTrigger: { trigger: sectionRef.current, start: "top 70%" }
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-32 md:py-48 px-6 md:px-12 border-t border-white/5">
      <div className="max-w-[1400px] mx-auto">
        <span className="sd-label block mb-16">Key Facts</span>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-white/5">
          {FACTS.map((fact) => (
            <div
              key={fact.label}
              className="infra-item bg-black p-8 md:p-12 group hover:bg-neutral-950 transition-colors duration-700"
            >
              <span className="font-serif text-5xl md:text-7xl text-cream-100 group-hover:text-sand transition-colors duration-700 block mb-6">
                {fact.num}
              </span>
              <span className="font-serif text-lg text-cream-200 block mb-2">
                {fact.label}
              </span>
              <span className="sd-mono">{fact.desc}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
