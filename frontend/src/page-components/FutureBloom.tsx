"use client";
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Sprout, Plus, Trash2, Clock, Edit2 } from "lucide-react";
import {
  collection,
  onSnapshot,
  query,
  addDoc,
  deleteDoc,
  doc,
  Timestamp,
} from "firebase/firestore";
import { db } from "../../services/firebase";

const FutureBloom: React.FC = () => {
  const navigate = useNavigate();
  const [goals, setGoals] = useState<any[]>([]);
  const [colNames, setColNames] = useState({
    col1: "3 Months",
    col2: "1 Year",
    col3: "2 Years",
  });
  const [editingCol, setEditingCol] = useState<string | null>(null);

  useEffect(() => {
    const q = query(collection(db, "hope_tasks"));
    const unsubscribe = onSnapshot(q, (snapshot) => {
      setGoals(snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() })));
    });
    return () => unsubscribe();
  }, []);

  const getDaysRemaining = (targetDate: any) => {
    if (!targetDate) return "";
    const now = new Date();
    const target = targetDate.toDate();
    const diffTime = target.getTime() - now.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays > 0 ? `${diffDays} days left` : "Milestone reached";
  };

  const addGoal = async (type: string) => {
    const title = prompt(`Define your ${type} vision:`);
    if (!title) return;
    const target = new Date();
    if (type === colNames.col1) target.setMonth(target.getMonth() + 3);
    else if (type === colNames.col2)
      target.setFullYear(target.getFullYear() + 1);
    else if (type === colNames.col3)
      target.setFullYear(target.getFullYear() + 2);

    await addDoc(collection(db, "hope_tasks"), {
      title,
      category: type,
      createdAt: Timestamp.now(),
      targetDate: Timestamp.fromDate(target),
    });
  };

  const GoalColumn = ({ id, title }: { id: string; title: string }) => (
    <div className="flex-1 min-w-[340px] bg-white/15 backdrop-blur-2xl rounded-[3rem] border border-white/30 p-10 flex flex-col shadow-2xl transition-transform hover:scale-[1.01]">
      <div className="flex justify-between items-center mb-10">
        {editingCol === id ? (
          <input
            autoFocus
            className="bg-transparent border-b-2 border-white outline-none text-white font-black uppercase tracking-widest text-xl w-full mr-4"
            value={title}
            onChange={(e) => setColNames({ ...colNames, [id]: e.target.value })}
            onBlur={() => setEditingCol(null)}
          />
        ) : (
          <div
            className="flex items-center gap-4 group cursor-pointer"
            onClick={() => setEditingCol(id)}
          >
            {/* INCREASED FONT SIZE HERE: text-xl and font-black */}
            <h2 className="text-white font-black uppercase tracking-[0.15em] text-xl italic drop-shadow-md">
              {title}
            </h2>
            <Edit2
              size={16}
              className="text-white/30 opacity-0 group-hover:opacity-100 transition-all"
            />
          </div>
        )}
        <button
          onClick={() => addGoal(title)}
          className="w-12 h-12 bg-purple-500/80 hover:bg-purple-400 text-white rounded-full flex items-center justify-center transition-all shadow-lg active:scale-90 border border-white/20"
        >
          <Plus size={24} />
        </button>
      </div>

      <div className="space-y-5 overflow-y-auto pr-2 scrollbar-hide flex-1">
        {goals
          .filter((g) => g.category === title)
          .map((goal) => (
            <div
              key={goal.id}
              className={`group border p-6 rounded-[2rem] transition-all relative shadow-sm
                ${
                  goal.sage_highlighted
                    ? "bg-purple-500/30 border-purple-300/60 hover:bg-purple-500/40"
                    : "bg-white/20 border-white/10 hover:bg-white/30"
                }`}
            >
              <button
                onClick={async () => {
                  if (confirm("Remove goal?"))
                    await deleteDoc(doc(db, "hope_tasks", goal.id));
                }}
                className="absolute top-5 right-5 text-white/40 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
              >
                <Trash2 size={16} />
              </button>
              <p className="text-[15px] font-bold text-white mb-3 leading-relaxed">
                {goal.title}
                {goal.sage_suggested && (
                  <span className="ml-2 text-[9px] bg-purple-400/40 text-purple-100 px-2 py-0.5 rounded-full font-black uppercase tracking-widest">
                    SAGE ✦
                  </span>
                )}
              </p>
              <div className="flex items-center gap-2 text-[10px] text-purple-100 font-black uppercase tracking-widest">
                <Clock size={12} /> {getDaysRemaining(goal.targetDate)}
              </div>
            </div>
          ))}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen w-full flex flex-col font-sans relative overflow-hidden">
      {/* 1. BACKGROUND ENGINE */}
      <div
        className="fixed inset-0 z-0 bg-center bg-cover scale-105"
        style={{ backgroundImage: "url('/background_Image.png')" }}
      />

      {/* 2. FROSTED ATMOSPHERE */}
      <div className="fixed inset-0 z-10 bg-white/5 backdrop-blur-[2px] pointer-events-none" />

      {/* 3. NAVIGATION BAR */}
      <nav className="relative z-30 h-24 flex items-center justify-between px-12 border-b border-white/10 backdrop-blur-3xl bg-white/5">
        <button
          onClick={() => navigate("/matrix")}
          className="flex items-center gap-3 text-white/70 hover:text-white transition-all group"
        >
          <div className="p-2 border border-white/20 rounded-xl group-hover:border-white/50 bg-white/5">
            <ArrowLeft size={18} />
          </div>
          <span className="text-[10px] font-black uppercase tracking-[0.4em]">
            Return
          </span>
        </button>

        <div className="flex items-center gap-4">
          <div className="p-2 bg-purple-500/20 rounded-xl border border-white/20">
            <Sprout className="text-white" size={24} />
          </div>
          <h1 className="text-3xl font-black italic tracking-tighter uppercase text-white drop-shadow-xl">
            Future<span className="text-purple-300">Bloom</span>
          </h1>
        </div>
        <div className="w-28" />
      </nav>

      {/* 4. MAIN LAYOUT */}
      <main className="relative z-20 flex-1 flex flex-col p-10 lg:p-16 gap-16 max-w-[1800px] mx-auto w-full">
        <header className="text-center pt-4">
          <h2 className="text-white text-4xl md:text-6xl font-black tracking-tighter leading-[1.1] max-w-5xl mx-auto drop-shadow-2xl">
            Design the life you haven't{" "}
            <span className="text-purple-300 italic">met yet</span>. <br />
            Your future self is{" "}
            <span className="text-white">built in the now</span>.
          </h2>
        </header>

        {/* COLUMNS WITH INCREASED HEADER SIZES */}
        <div className="flex-1 flex flex-wrap lg:flex-nowrap gap-10 overflow-visible pb-24">
          <GoalColumn id="col1" title={colNames.col1} />
          <GoalColumn id="col2" title={colNames.col2} />
          <GoalColumn id="col3" title={colNames.col3} />
        </div>
      </main>
    </div>
  );
};

export default FutureBloom;
