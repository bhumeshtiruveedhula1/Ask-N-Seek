"use client";

import { useEffect, useState } from "react";

export default function Navigation() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => setVisible(window.scrollY > 100);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-700 ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-full"
      }`}
    >
      <div className="bg-black/80 backdrop-blur-md border-b border-white/5">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12 py-5 flex items-center justify-between">
          <a href="#" className="font-serif text-lg tracking-tight text-cream-100">
            Ask-N-Seek
          </a>
          <div className="hidden md:flex items-center gap-12">
            <a href="#about" className="sd-label hover:text-cream-100 transition-colors duration-500">About</a>
            <a href="#concept" className="sd-label hover:text-cream-100 transition-colors duration-500">Concept</a>
            <a href="#pipeline" className="sd-label hover:text-cream-100 transition-colors duration-500">Pipeline</a>
            <a href="#demo" className="sd-label hover:text-cream-100 transition-colors duration-500">Demo</a>
          </div>
          <span className="sd-label">v2.3</span>
        </div>
      </div>
    </nav>
  );
}
