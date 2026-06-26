"use client";
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  User,
  UserRound,
  ArrowLeft,
  Sparkles,
  ShieldCheck,
} from "lucide-react";

interface Avatar {
  id: "male" | "female";
  label: string;
  tone: string;
  description: string;
  icon: React.ReactNode;
}

const AvatarSelection: React.FC = () => {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<"male" | "female" | null>(null);

  const avatars: Avatar[] = [
    {
      id: "male",
      label: "Supportive Guide",
      tone: "Steady • Analytical • Protective",
      description:
        "A grounded presence focusing on cognitive strength and structured recovery.",
      icon: <UserRound size={44} strokeWidth={1.5} />,
    },
    {
      id: "female",
      label: "Empathetic Partner",
      tone: "Warm • Intuitive • Nurturing",
      description:
        "A compassionate mirror for emotional processing and deep, active listening.",
      icon: <User size={44} strokeWidth={1.5} />,
    },
  ];

  const handleContinue = () => {
    if (!selected) return;
    localStorage.setItem("userAvatar", selected);
    navigate("/chat");
  };

  return (
    // Forced bg-white ensures that transparency looks BRIGHT, not dark
    <div className="relative h-screen w-full flex flex-col items-center justify-center overflow-hidden font-sans bg-white select-none">
      {/* 1. VIVID BACKGROUND LAYER */}
      <div
        className="absolute inset-0 bg-cover bg-center transition-transform duration-[3000ms]"
        style={{
          backgroundImage: "url('/background_Image.png')",
          transform: selected ? "scale(1.08)" : "scale(1)",
          // Slightly boosting brightness and saturation for that "Professional" pop
          filter: "brightness(1.05) saturate(1.1)",
        }}
      >
        {/* White-tinted glass overlay - This 'lifts' the brightness of the image */}
        <div className="absolute inset-0 bg-white/20 backdrop-blur-[1px]" />
      </div>

      {/* 2. TOP NAVIGATION */}
      <nav className="absolute top-0 w-full p-10 flex justify-between items-center z-50">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-3 text-purple-900/60 hover:text-purple-900 transition-all group"
        >
          <div className="w-10 h-10 rounded-full border border-purple-900/10 flex items-center justify-center group-hover:border-purple-900/40 transition-all bg-white/40 backdrop-blur-md shadow-sm">
            <ArrowLeft size={18} />
          </div>
          <span className="text-[10px] font-black uppercase tracking-[0.4em] hidden md:block">
            Back to Entry
          </span>
        </button>

        <div className="flex items-center gap-3 px-5 py-2 rounded-full bg-white/60 border border-white/80 backdrop-blur-md shadow-sm">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-[9px] font-black text-purple-900 tracking-[0.4em] uppercase">
            System Ready
          </span>
        </div>
      </nav>

      {/* 3. HEADER CONTENT */}
      <div className="z-10 text-center mb-12 animate-in fade-in slide-in-from-top-4 duration-1000">
        <h2 className="text-5xl md:text-6xl font-black text-purple-900 tracking-tighter mb-4 leading-none">
          Choose Your <span className="text-purple-600 italic">Companion</span>
        </h2>
        <p className="text-purple-800/40 text-[10px] font-black uppercase tracking-[0.5em]">
          Select the frequency of your healing journey
        </p>
      </div>

      {/* 4. SELECTION CARDS (High-Clarity Glass) */}
      <div className="z-10 flex flex-row gap-8 w-full max-w-5xl px-10 justify-center items-center">
        {avatars.map((av) => (
          <button
            key={av.id}
            onClick={() => setSelected(av.id)}
            className={`group relative flex-1 max-w-[340px] h-[420px] rounded-[3.5rem] border-2 transition-all duration-700 flex flex-col items-center justify-center p-10 overflow-hidden backdrop-blur-2xl ${
              selected === av.id
                ? "bg-white border-purple-400 shadow-[0_40px_80px_-15px_rgba(124,58,237,0.2)] scale-[1.05]"
                : "bg-white/60 border-white/80 hover:border-purple-200 hover:bg-white/80 scale-100 shadow-xl"
            }`}
          >
            {/* Avatar Icon Sphere */}
            <div
              className={`mb-10 w-28 h-28 rounded-full flex items-center justify-center transition-all duration-700 border ${
                selected === av.id
                  ? "bg-purple-600 text-white border-purple-600 shadow-lg scale-110"
                  : "bg-purple-50 text-purple-300 border-purple-100 group-hover:border-purple-300"
              }`}
            >
              {av.icon}
            </div>

            <div className="relative z-10">
              <span
                className={`text-[8px] font-black tracking-[0.4em] uppercase transition-colors ${
                  selected === av.id ? "text-purple-600" : "text-purple-900/30"
                }`}
              >
                {av.tone}
              </span>
              <h3 className="text-2xl font-bold text-purple-900 mt-3 mb-4 tracking-tight uppercase leading-none">
                {av.label}
              </h3>
              <p className="text-purple-800/60 text-[11px] leading-relaxed font-medium px-4">
                {av.description}
              </p>
            </div>

            {/* Selection Checkmark */}
            <div
              className={`absolute bottom-8 transition-all duration-500 ${selected === av.id ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}
            >
              <CheckCircle2 size={24} className="text-purple-600" />
            </div>
          </button>
        ))}
      </div>

      {/* 5. ACTION AREA */}
      <div className="z-10 mt-16 flex flex-col items-center gap-6">
        <button
          disabled={!selected}
          onClick={handleContinue}
          className={`relative px-24 py-6 rounded-full font-black text-[11px] uppercase tracking-[0.5em] transition-all duration-500 active:scale-95 ${
            selected
              ? "bg-purple-600 text-white shadow-[0_20px_40px_-5px_rgba(124,58,237,0.4)] hover:px-28 hover:bg-purple-700"
              : "bg-purple-100 text-purple-300 border border-purple-50 cursor-not-allowed"
          }`}
        >
          <span className="flex items-center gap-3">
            Enter Sanctuary {selected && <Sparkles size={16} />}
          </span>
        </button>

        <div className="flex gap-10 mt-2">
          <div className="flex items-center gap-2 text-[8px] font-black text-purple-900/30 uppercase tracking-[0.3em]">
            <ShieldCheck size={12} className="text-purple-400" /> Private
            Session
          </div>
          <div className="flex items-center gap-2 text-[8px] font-black text-purple-900/30 uppercase tracking-[0.3em]">
            <Sparkles size={12} className="text-purple-400" /> Neural Guidance
          </div>
        </div>
      </div>

      {/* Subtle Grain Overlay (removes the 'flat' digital look) */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.03] bg-[url('https://grainy-gradients.vercel.app/noise.svg')]" />
    </div>
  );
};

export default AvatarSelection;
