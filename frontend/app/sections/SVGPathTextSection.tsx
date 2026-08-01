"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export default function SVGPathTextSection() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const pathTextRef = useRef<SVGTextPathElement>(null);
  const pathRef = useRef<SVGPathElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Animate the text along the path as user scrolls
      if (pathTextRef.current && pathRef.current) {
        const pathLength = pathRef.current.getTotalLength();

        gsap.fromTo(
          pathTextRef.current,
          { attr: { startOffset: "100%" } },
          {
            attr: { startOffset: "-20%" },
            ease: "none",
            scrollTrigger: {
              trigger: sectionRef.current,
              start: "top bottom",
              end: "bottom top",
              scrub: 1.5,
            },
          }
        );
      }

      // Fade in the section
      gsap.fromTo(
        sectionRef.current,
        { opacity: 0 },
        {
          opacity: 1,
          duration: 1,
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 80%",
          },
        }
      );
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-32 md:py-48 px-6 md:px-12 overflow-hidden opacity-0">
      <div className="max-w-[1400px] mx-auto">
        <span className="sd-label block mb-12">Where the data speaks</span>

        <svg
          ref={svgRef}
          viewBox="0 0 1200 400"
          className="w-full h-auto"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <path
              ref={pathRef}
              id="textPath"
              d="M 0 200 Q 300 50 600 200 T 1200 200"
              fill="none"
            />
          </defs>
          <text className="font-serif italic" style={{ fontSize: "64px", fill: "#f5f3ef" }}>
            <textPath ref={pathTextRef} href="#textPath" startOffset="100%">
              objects · colors · spatial relations · confidence · proof ·
            </textPath>
          </text>
        </svg>

        <div className="mt-16 grid grid-cols-1 md:grid-cols-2 gap-16">
          <div>
            <h3 className="sd-headline-mid text-cream-100 mb-6">Every pixel matters.</h3>
            <p className="sd-body-large">
              We do not compress your video into a single embedding vector. We preserve
              every object, every color, every spatial relation as structured facts.
              This is what makes negation, counting, and spatial queries possible.
            </p>
          </div>
          <div className="relative aspect-[4/3] bg-neutral-900 overflow-hidden">
            {/* Animated data visualization */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-48 h-48 border border-cream-800 rounded-full animate-pulse opacity-30" />
              <div className="absolute w-32 h-32 border border-sand rounded-full animate-pulse opacity-20" style={{ animationDelay: "0.5s" }} />
              <div className="absolute w-16 h-16 bg-sand/10 rounded-full animate-pulse" style={{ animationDelay: "1s" }} />
            </div>
            <div className="absolute bottom-4 left-4 right-4">
              <div className="flex justify-between text-[10px] font-mono text-cream-700">
                <span>YOLO-World-M</span>
                <span>800+ classes</span>
                <span>CIELAB color</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
