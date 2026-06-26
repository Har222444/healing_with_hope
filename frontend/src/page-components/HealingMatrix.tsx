"use client";

import React from "react";
import { useNavigate } from "react-router-dom";
import {
  Footprints,
  ShieldCheck,
  Wind,
  Flower2,
  ArrowRight,
  Sparkles,
} from "lucide-react";

export default function HealingMatrix() {
  const navigate = useNavigate();

  const pathways = [
    {
      Icon: Footprints,
      title: "TINY STEPS",
      desc: "Focus on small, manageable daily actions.",
      color: "text-emerald-600",
      bg: "group-hover:bg-emerald-500/10",
      path: "/tiny-steps",
    },
    {
      Icon: Flower2,
      title: "FUTURE BLOOM",
      desc: "Visualizing your future self.",
      color: "text-rose-600",
      bg: "group-hover:bg-rose-500/10",
      path: "/futurebloom",
    },
  ];

  return (
    <div className="fixed inset-0 w-screen h-screen flex flex-col font-sans overflow-hidden bg-white">
      {/* --- BACKGROUND ENGINE --- */}
      <div
        className="absolute inset-0 z-0 bg-cover bg-center transition-transform duration-[10s] scale-110"
        style={{ backgroundImage: "url('/background_Image.png')" }}
      />
      <div className="absolute inset-0 z-10 bg-white/60 backdrop-blur-[2px]" />

      {/* --- CONTENT WRAPPER (92vh used for content, 8vh for top margin) --- */}
      <div className="relative z-20 h-full w-full flex flex-col p-12 px-16">
        {/* HEADER SECTION - Compacted to save vertical space */}
        <div className="mb-10 max-w-4xl">
          <div className="flex items-center gap-3 mb-2">
            <Sparkles className="text-purple-600" size={20} />
            <span className="text-[10px] font-black uppercase tracking-[0.4em] text-purple-900/40">
              Recovery Navigation
            </span>
          </div>
          <h1 className="text-6xl font-black tracking-tighter text-purple-950 leading-none">
            HEALING <span className="text-purple-600 italic">MATRIX</span>
          </h1>
        </div>

        {/* GRID SECTION - Forced to fit remaining height */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 mb-4 max-h-[60vh]">
          {pathways.map((item, i) => (
            <div
              key={i}
              onClick={() => item.path !== "#" && navigate(item.path)}
              className="group relative p-8 rounded-[3.5rem] bg-white/70 border border-white hover:border-purple-200 transition-all duration-500 cursor-pointer flex flex-col justify-between shadow-2xl backdrop-blur-3xl overflow-hidden active:scale-95"
            >
              <div
                className={`absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 ${item.bg}`}
              />

              <div className="relative z-10">
                <div className="w-14 h-14 rounded-2xl bg-white flex items-center justify-center mb-6 shadow-sm border border-purple-50 group-hover:scale-110 transition-transform duration-500">
                  <item.Icon className={item.color} size={28} />
                </div>
                <h2 className="text-xl font-black tracking-widest mb-3 uppercase text-purple-950">
                  {item.title}
                </h2>
                <p className="text-[11px] text-purple-900/60 leading-relaxed font-bold uppercase tracking-wider">
                  {item.desc}
                </p>
              </div>

              <div className="relative z-10 flex items-center justify-between opacity-0 group-hover:opacity-100 transition-all duration-500 translate-y-2 group-hover:translate-y-0">
                <span className="text-[10px] font-black tracking-widest uppercase text-purple-600">
                  {item.path === "#" ? "Coming Soon" : "Enter Path"}
                </span>
                <ArrowRight size={16} className="text-purple-600" />
              </div>
            </div>
          ))}
        </div>

        {/* FOOTER DECOR - Keeps it professional */}
        <div className="mt-auto pt-6 border-t border-purple-900/5 flex justify-between items-center">
          <p className="text-[9px] font-black text-purple-900/30 uppercase tracking-[0.5em]">
            Safe Space Environment v2.0
          </p>
          <div className="flex gap-4">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <div className="w-2 h-2 rounded-full bg-purple-400 opacity-50" />
            <div className="w-2 h-2 rounded-full bg-purple-400 opacity-20" />
          </div>
        </div>
      </div>
    </div>
  );
}
