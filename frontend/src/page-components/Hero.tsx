"use client";
import React from "react";
import { useNavigate } from "react-router-dom";
import AtomsBackground from "../components/3D/AtomsBackground";

const Hero: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="relative min-h-screen w-full flex flex-col items-center justify-center bg-white overflow-hidden">
      {/* The 3D Canvas Layer */}
      <AtomsBackground />

      {/* Main Content Layer */}
      <div className="z-10 text-center max-w-4xl px-6 animate-in fade-in zoom-in duration-1000">
        <h1 className="text-6xl md:text-8xl font-black text-slate-900 mb-6 tracking-tighter leading-none">
          Healing with <br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-600 to-indigo-500">
            Hope
          </span>
        </h1>

        <p className="text-lg md:text-2xl text-slate-500 mb-12 leading-relaxed max-w-2xl mx-auto font-light">
          A neuroscience-backed digital sanctuary designed to help you rename
          your story and rebuild your future.
        </p>

        <div className="flex justify-center">
          <button
            onClick={() => navigate("/signup")}
            className="px-16 py-6 bg-purple-600 text-white rounded-full font-black text-xl shadow-[0_20px_50px_rgba(124,58,237,0.3)] hover:bg-purple-700 transition-all hover:scale-105 active:scale-95 uppercase tracking-widest"
          >
            Get Started
          </button>
        </div>
      </div>

      {/* Bottom subtle copyright or version (optional, kept it minimal) */}
      <div className="absolute bottom-8 text-[10px] font-bold text-slate-300 uppercase tracking-[0.5em]">
        Neural Sanctuary Protocol
      </div>
    </div>
  );
};

export default Hero;
