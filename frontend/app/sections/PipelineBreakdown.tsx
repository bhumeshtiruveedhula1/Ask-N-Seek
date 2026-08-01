"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const STEPS = [
  { num: "01", title: "Scene Detection", desc: "PySceneDetect finds natural cuts. No wasted frames." },
  { num: "02", title: "Keyframe Extraction", desc: "OpenCV seek-based extraction at scene boundaries." },
  { num: "03", title: "Object Detection", desc: "YOLO-World-M draws real boxes. 800+ classes." },
  { num: "04", title: "Color Extraction", desc: "Center-weighted crop + k-means in CIELAB space." },
  { num: "05", title: "Spatial Relations", desc: "Left/right geometry from bounding box centroids." },
  { num: "06", title: "Structured Storage", desc: "Qdrant payload filters. Keyword-indexed. Fast." },
];

export default function PipelineBreakdown() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [startX, setStartX] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(".pipeline-item", { opacity: 0, y: 40 }, {
        opacity: 1, y: 0, duration: 0.8, stagger: 0.1, ease: "power3.out",
        scrollTrigger: { trigger: sectionRef.current, start: "top 70%" }
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setStartX(e.pageX - (scrollRef.current?.offsetLeft || 0));
    setScrollLeft(scrollRef.current?.scrollLeft || 0);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging || !scrollRef.current) return;
    e.preventDefault();
    const x = e.pageX - (scrollRef.current.offsetLeft || 0);
    const walk = (x - startX) * 2;
    scrollRef.current.scrollLeft = scrollLeft - walk;
  };

  const handleMouseUp = () => setIsDragging(false);

  return (
    <section id="pipeline" ref={sectionRef} className="py-32 md:py-48 px-6 md:px-12 border-t border-white/5 overflow-hidden">
      <div className="max-w-[1400px] mx-auto">
        <div className="flex items-end justify-between mb-16">
          <div>
            <span className="sd-label block mb-4">Pipeline</span>
            <h2 className="sd-headline-mid text-cream-100">Six steps. Zero guessing.</h2>
          </div>
          <span className="sd-label hidden md:block">hold and move →</span>
        </div>

        {/* Draggable horizontal scroll */}
        <div
          ref={scrollRef}
          className="flex gap-px overflow-x-auto cursor-grab active:cursor-grabbing select-none"
          style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          {STEPS.map((step) => (
            <div
              key={step.num}
              className="pipeline-item flex-shrink-0 w-[300px] md:w-[380px] p-8 md:p-12 bg-neutral-950 border border-white/5 hover:border-white/10 transition-colors duration-500 group"
            >
              <span className="font-serif text-5xl md:text-6xl text-cream-800 group-hover:text-cream-400 transition-colors duration-500 block mb-8">
                {step.num}
              </span>
              <h3 className="font-serif text-xl md:text-2xl text-cream-100 mb-4">
                {step.title}
              </h3>
              <p className="sd-body text-sm">
                {step.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
