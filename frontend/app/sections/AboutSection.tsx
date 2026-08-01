"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export default function AboutSection() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(labelRef.current, { opacity: 0, y: 20 }, {
        opacity: 1, y: 0, duration: 0.8, ease: "power3.out",
        scrollTrigger: { trigger: sectionRef.current, start: "top 75%" }
      });
      gsap.fromTo(headingRef.current, { opacity: 0, y: 40 }, {
        opacity: 1, y: 0, duration: 1.2, ease: "power3.out",
        scrollTrigger: { trigger: sectionRef.current, start: "top 70%" }
      });
      gsap.fromTo(bodyRef.current, { opacity: 0, y: 30 }, {
        opacity: 1, y: 0, duration: 1, ease: "power3.out", delay: 0.2,
        scrollTrigger: { trigger: sectionRef.current, start: "top 65%" }
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <section id="about" ref={sectionRef} className="py-32 md:py-48 px-6 md:px-12 border-t border-white/5">
      <div className="max-w-[1400px] mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-16 lg:gap-24">
          <div className="lg:col-span-5">
            <span ref={labelRef} className="sd-label block mb-8 opacity-0">About the System</span>
            <h2 ref={headingRef} className="sd-headline-mid opacity-0">
              Ask-N-Seek is a natural language video retrieval system.
            </h2>
          </div>
          <div ref={bodyRef} className="lg:col-span-7 lg:pt-16 opacity-0">
            <p className="sd-body-large mb-8">
              Most teams use embedding similarity — turning everything into numbers
              and hoping for the best. That fails on compositional queries, negation,
              counting, and spatial relations. It cannot tell you <em>why</em> something matched.
            </p>
            <p className="sd-body-large mb-8">
              We do the opposite. YOLO-World draws real bounding boxes around every object.
              We read colors from actual pixels. We compute left/right geometry. We store
              everything as structured facts in Qdrant — then answer with provable database
              logic, not AI guessing.
            </p>
            <p className="sd-body-large">
              When nothing matches, we do not fake an answer. We show you exactly which
              constraints were found, which were missing, and the closest partial match.
              That is the difference between a demo and a product.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
