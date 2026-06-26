"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  TrendingUp,
  ArrowLeft,
  Target,
  Zap,
  Clock,
  Activity,
  ShieldCheck,
  CalendarDays,
} from "lucide-react";
import { collection, onSnapshot, query, where, doc } from "firebase/firestore";
import { db } from "../../services/firebase";

interface UserStats {
  healing_points: number;
  streak_days: number;
  chat_count: number;
  current_state: string;
  session_risk_level: string;
  mood_trajectory: string;
}

const ProgressDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [bloomGoals, setBloomGoals] = useState<any[]>([]);
  const [tinySteps, setTinySteps] = useState<any[]>([]);
  const [today, setToday] = useState(new Date());
  const [userStats, setUserStats] = useState<UserStats>({
    healing_points: 0,
    streak_days: 0,
    chat_count: 0,
    current_state: "neutral",
    session_risk_level: "normal",
    mood_trajectory: "unknown",
  });

  const [userId] = useState(() => {
    const saved = localStorage.getItem("chat_user_id");
    return saved || `user_${Math.random().toString(36).substring(2, 11)}`;
  });

  // ── MATCHING TINYSTEPS LOGIC: Mon=0 ... Sun=6 ─────────────────────────────
  const currentDayIdx = (today.getDay() + 6) % 7;

  useEffect(() => {
    const timer = setInterval(() => setToday(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);

  // ── Firestore Listeners ───────────────────────────────────────────────────
  useEffect(() => {
    const q = query(collection(db, "hope_tasks"));
    return onSnapshot(q, (snapshot) => {
      setBloomGoals(snapshot.docs.map((d) => ({ id: d.id, ...d.data() })));
    });
  }, []);

  useEffect(() => {
    const q = query(
      collection(db, "tiny_steps"),
      where("userId", "==", userId),
    );
    return onSnapshot(q, (snapshot) => {
      setTinySteps(snapshot.docs.map((d) => ({ id: d.id, ...d.data() })));
    });
  }, [userId]);

  useEffect(() => {
    const statsRef = doc(db, "user_stats", userId);
    return onSnapshot(statsRef, (snap) => {
      if (snap.exists()) setUserStats(snap.data() as UserStats);
    });
  }, [userId]);

  // ── DATA CALCULATIONS ─────────────────────────────────────────────────────
  const completedTasks = tinySteps.filter((t) => t.completed).length;
  const totalTasks = tinySteps.length;
  const habitCompletion =
    totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  const weeklyData = useMemo(() => {
    const counts = Array(7).fill(0);
    const totals = Array(7).fill(0);

    tinySteps.forEach((t) => {
      // Use current day for completion visualization
      // In TinySteps, completion is toggled for "Today"
      if (t.completed) {
        counts[currentDayIdx] += 1;
      }
      totals[currentDayIdx] += 1;
    });

    return totals.map((total, i) =>
      total > 0 ? Math.round((counts[i] / total) * 100) : 0,
    );
  }, [tinySteps, currentDayIdx]);

  const formattedDate = today.toLocaleDateString("en-US", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const formattedDay = today.toLocaleDateString("en-US", { weekday: "long" });

  return (
    <div className="fixed inset-0 w-screen h-screen flex flex-col font-sans select-none overflow-hidden bg-slate-100">
      <div
        className="absolute inset-0 z-0 bg-cover bg-center transition-transform duration-[10s] scale-110"
        style={{ backgroundImage: "url('/background_Image.png')" }}
      />
      <div className="absolute inset-0 z-10 bg-white/40 backdrop-blur-[3px]" />

      <header className="relative z-30 h-[8vh] flex items-center justify-between px-10 bg-white/30 backdrop-blur-2xl border-b border-white/50 shadow-sm">
        <div className="flex items-center gap-6">
          <button
            onClick={() => navigate("/matrix")}
            className="flex items-center gap-2 bg-white/80 hover:bg-white px-4 py-2 rounded-xl shadow-sm border border-slate-200 transition-all active:scale-95"
          >
            <ArrowLeft size={16} className="text-[#7c3aed]" />
            <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">
              Back
            </span>
          </button>
          <div className="flex items-center gap-3">
            <ShieldCheck className="text-[#7c3aed]" size={24} />
            <h1 className="text-2xl font-black italic text-[#2d1656] tracking-tighter uppercase">
              Growth <span className="text-[#7c3aed] not-italic">Engine</span>
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 bg-white/70 backdrop-blur-md px-5 py-2 rounded-2xl border border-white/60 shadow-sm">
            <CalendarDays size={14} className="text-[#7c3aed]" />
            <div className="flex flex-col items-start leading-tight">
              <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">
                {formattedDay}
              </span>
              <span className="text-[11px] font-black text-[#2d1656]">
                {formattedDate}
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="relative z-20 flex-1 grid grid-cols-12 grid-rows-6 gap-6 p-8 h-[92vh]">
        {/* TOP STATS */}
        <div className="col-span-12 row-span-1 grid grid-cols-4 gap-6">
          {[
            {
              label: "Active Streak",
              val: `${userStats.streak_days} Days`,
              icon: <Zap />,
              color: "bg-amber-100 text-amber-600",
            },
            {
              label: "Consistency",
              val: `${habitCompletion}%`,
              icon: <TrendingUp />,
              color: "bg-emerald-100 text-emerald-600",
            },
            {
              label: "Target Goals",
              val: bloomGoals.length,
              icon: <Target />,
              color: "bg-purple-100 text-purple-600",
            },
            {
              label: "Healing Points",
              val: userStats.healing_points,
              icon: <Clock />,
              color: "bg-blue-100 text-blue-600",
            },
          ].map((item, i) => (
            <div
              key={i}
              className="bg-white/60 backdrop-blur-md border border-white/60 rounded-3xl shadow-sm flex items-center px-8 gap-5"
            >
              <div className={`p-3 rounded-2xl ${item.color}`}>{item.icon}</div>
              <div className="text-left">
                <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">
                  {item.label}
                </p>
                <p className="text-xl font-black text-slate-800 tracking-tight">
                  {item.val}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* WEEKLY CHART */}
        <div className="col-span-7 row-span-5 bg-white/70 backdrop-blur-xl border border-white rounded-[3.5rem] shadow-2xl p-10 flex flex-col">
          <div className="flex justify-between items-start mb-8 text-left">
            <div>
              <h2 className="text-3xl font-black text-[#2d1656] uppercase tracking-tighter italic">
                Weekly Bloom
              </h2>
              <p className="text-slate-400 text-[10px] font-black uppercase tracking-[0.3em] mt-2">
                Current Completion Progress
              </p>
            </div>
            <div className="flex bg-slate-100/50 p-1 rounded-xl gap-1">
              {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => (
                <div
                  key={i}
                  className={`w-7 h-7 flex items-center justify-center text-[10px] font-black rounded-lg ${i === currentDayIdx ? "bg-[#7c3aed] text-white" : "text-slate-400"}`}
                >
                  {d}
                </div>
              ))}
            </div>
          </div>

          <div className="flex-1 flex items-end justify-between gap-6 px-4 pb-4">
            {weeklyData.map((h, i) => (
              <div
                key={i}
                className="flex-1 flex flex-col items-center gap-4 group h-full justify-end"
              >
                <div className="w-full relative flex items-end justify-center">
                  <div
                    className={`w-full rounded-2xl transition-all duration-1000 ${i === currentDayIdx ? "bg-gradient-to-t from-[#5b21b6] to-[#a855f7]" : "bg-slate-200"}`}
                    style={{
                      height: `${i === currentDayIdx ? Math.max((h / 100) * 260, 20) : 10}px`,
                    }}
                  />
                  {i === currentDayIdx && (
                    <div className="absolute -top-10 bg-[#2d1656] text-white text-[10px] font-black px-3 py-1.5 rounded-xl transition-all">
                      {h}%
                    </div>
                  )}
                </div>
                <span
                  className={`text-[10px] font-black uppercase tracking-tighter ${i === currentDayIdx ? "text-[#7c3aed]" : "text-slate-400"}`}
                >
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i]}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* COMPLETION RING */}
        <div className="col-span-5 row-span-5 bg-[#7c3aed] rounded-[3.5rem] shadow-2xl p-10 flex flex-col items-center justify-center text-center relative overflow-hidden">
          <div className="relative w-52 h-52">
            <svg className="w-full h-full transform -rotate-90">
              <circle
                cx="104"
                cy="104"
                r="90"
                stroke="rgba(255,255,255,0.15)"
                strokeWidth="16"
                fill="transparent"
              />
              <circle
                cx="104"
                cy="104"
                r="90"
                stroke="white"
                strokeWidth="16"
                fill="transparent"
                strokeDasharray="565"
                strokeDashoffset={565 - (565 * habitCompletion) / 100}
                className="transition-all duration-1000 ease-out"
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-5xl font-black text-white tracking-tighter">
                {habitCompletion}%
              </span>
              <span className="text-[10px] font-black text-white/50 uppercase tracking-widest mt-1">
                Today
              </span>
            </div>
          </div>
          <h3 className="mt-8 text-2xl font-black text-white uppercase italic">
            Life Transformation
          </h3>
          <p className="text-white/60 text-[11px] font-bold uppercase tracking-widest mt-2">
            {completedTasks} / {totalTasks} tasks done
          </p>
          <div className="mt-6 w-full bg-white/10 rounded-3xl px-6 py-5 flex items-center justify-between text-white">
            <div className="text-left">
              <p className="text-[9px] font-black opacity-50 uppercase">
                Current Streak
              </p>
              <p className="text-3xl font-black">
                {userStats.streak_days}{" "}
                <span className="text-lg opacity-70">days</span>
              </p>
            </div>
            <Zap size={36} className="text-amber-300" />
          </div>
        </div>
      </main>
    </div>
  );
};

export default ProgressDashboard;
