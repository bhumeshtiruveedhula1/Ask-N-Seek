"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export default function CinematicSection() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Parallax on image
      gsap.fromTo(imgRef.current, { y: 100, scale: 1.1 }, {
        y: -100, scale: 1,
        ease: "none",
        scrollTrigger: {
          trigger: sectionRef.current,
          start: "top bottom",
          end: "bottom top",
          scrub: 1,
        }
      });

      // Text reveal
      gsap.fromTo(textRef.current, { opacity: 0, y: 60 }, {
        opacity: 1, y: 0, duration: 1.4, ease: "power3.out",
        scrollTrigger: { trigger: textRef.current, start: "top 80%" }
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-32 md:py-48 px-6 md:px-12 overflow-hidden">
      <div className="max-w-[1400px] mx-auto">
        <div className="relative aspect-[16/9] md:aspect-[21/9] overflow-hidden bg-neutral-900">
          <div ref={imgRef} className="absolute inset-0 will-change-transform">
            {/* Abstract geometric pattern as placeholder for video frame */}
            <div className="w-full h-full bg-gradient-to-br from-neutral-900 via-neutral-800 to-black flex items-center justify-center">
              <div className="grid grid-cols-6 gap-1 opacity-20">
                {Array.from({ length: 36 }).map((_, i) => (
                  <div key={i} className={`w-8 h-8 md:w-16 md:h-16 rounded-sm ${i % 7 === 0 ? 'bg-sand' : 'bg-cream-800'}`} />
                ))}
              </div>
            </div>
          </div>
        </div>

        <div ref={textRef} className="mt-16 md:mt-24 opacity-0">
          <h2 className="sd-headline-italic text-cream-100">
            See you in the results.
          </h2>
          <p className="sd-body mt-8 max-w-xl">
            Every match comes with bounding boxes, confidence scores, and a plain-English
            explanation of exactly why it matched. No black boxes. No similarity scores you cannot interpret.
          </p>
        </div>
      </div>
    </section>
  );
}
