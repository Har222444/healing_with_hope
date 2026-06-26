"use client";

import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  ArrowLeft,
  Heart,
  Plus,
  Shield,
  Trophy,
  Clock,
  Lock,
  Trash2,
  Sparkles,
} from "lucide-react";
import {
  collection,
  onSnapshot,
  query,
  where,
  addDoc,
  updateDoc,
  deleteDoc,
  doc,
  setDoc,
  serverTimestamp,
} from "firebase/firestore";
import { db } from "../../services/firebase";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TaskHabit {
  id: string;
  task: string;
  category: string;
  time: string;
  domain: string;
  completed: boolean;
  source: "chatbot" | "manual";
  history: boolean[];
  sage_priority?: number;
  sage_highlighted?: boolean;
  sage_reason?: string | null;
  sage_suggested?: boolean;
  _isNew?: boolean;
}

// ── 5 default daily tasks ─────────────────────────────────────────────────────

const DEFAULT_TASKS: (Omit<TaskHabit, "id" | "history" | "_isNew"> & {
  seedKey: string;
})[] = [
  {
    seedKey: "water",
    task: "Drink 8 glasses of water",
    category: "Health",
    time: "All day",
    domain: "HEALTH",
    completed: false,
    source: "manual",
  },
  {
    seedKey: "sleep",
    task: "Get at least 7 hours of sleep",
    category: "Health",
    time: "10:30 PM",
    domain: "HEALTH",
    completed: false,
    source: "manual",
  },
  {
    seedKey: "move",
    task: "Move your body for 20 minutes",
    category: "Self",
    time: "7:00 AM",
    domain: "WELLNESS",
    completed: false,
    source: "manual",
  },
  {
    seedKey: "focus",
    task: "Spend 30 min on your top priority",
    category: "Focus",
    time: "9:00 AM",
    domain: "WORK",
    completed: false,
    source: "manual",
  },
  {
    seedKey: "gratitude",
    task: "Write 3 things you are grateful for",
    category: "Self",
    time: "9:00 PM",
    domain: "WELLNESS",
    completed: false,
    source: "manual",
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

const domainToCategory = (domain: string): string => {
  const map: Record<string, string> = {
    STUDY: "Study",
    HEALTH: "Health",
    WELLNESS: "Self",
    WORK: "Focus",
    GENERAL: "New",
    EMOTIONAL: "Self",
    SOCIAL: "Self",
    PHYSICAL: "Health",
    PURPOSE: "Self",
    OVERLOAD: "Focus",
    UNDIRECTED: "New",
    CAREER: "Focus",
  };
  return map[domain] ?? domain ?? "New";
};

const seedDefaultTasks = async (userId: string) => {
  await Promise.all(
    DEFAULT_TASKS.map(({ seedKey, ...t }) => {
      const seedDocId = `seed_${userId}_${seedKey}`;
      return setDoc(
        doc(db, "tiny_steps", seedDocId),
        {
          ...t,
          userId,
          history: Array(31).fill(false),
          date: serverTimestamp(),
        },
        { merge: true },
      );
    }),
  );
};

// ── NewTaskToast ──────────────────────────────────────────────────────────────

const NewTaskToast = ({
  task,
  onDismiss,
}: {
  task: string;
  onDismiss: () => void;
}) => {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div className="fixed bottom-24 right-6 z-50 animate-in slide-in-from-bottom-4 fade-in duration-300">
      <div className="bg-[#7c3aed] text-white px-5 py-3 rounded-2xl shadow-2xl flex items-center gap-3 max-w-xs">
        <Sparkles size={16} className="shrink-0 animate-pulse" />
        <div>
          <p className="text-[9px] font-black uppercase tracking-widest text-purple-200 mb-0.5">
            Hope detected a new step for you ✦
          </p>
          <p className="text-xs font-bold leading-tight">{task}</p>
        </div>
      </div>
    </div>
  );
};

// ── Component ─────────────────────────────────────────────────────────────────

const TinySteps: React.FC = () => {
  const navigate = useNavigate();

  const [shortGoal, setShortGoal] = useState("Achieve 90% Consistency");
  const [longGoal, setLongGoal] = useState("Complete Life Transformation");
  const [habits, setHabits] = useState<TaskHabit[]>([]);
  const [loading, setLoading] = useState(true);
  const [newTaskToast, setNewTaskToast] = useState<string | null>(null);

  const seededRef = useRef(false);
  const knownIdsRef = useRef<Set<string>>(new Set());
  const isFirstLoad = useRef(true);

  const [userId] = useState(() => {
    const saved = localStorage.getItem("chat_user_id");
    if (saved) return saved;
    const newId = `user_${Math.random().toString(36).substring(2, 11)}`;
    localStorage.setItem("chat_user_id", newId);
    return newId;
  });

  const today = new Date();
  const currentDay = today.getDate();
  const currentMonthName = today.toLocaleString("default", { month: "long" });
  const currentYear = today.getFullYear();
  const dayOfWeek = (today.getDay() + 6) % 7;
  const daysInMonth = new Date(currentYear, today.getMonth() + 1, 0).getDate();
  const firstDayOfMonth = new Date(currentYear, today.getMonth(), 1).getDay();
  const firstDayIndex = (firstDayOfMonth + 6) % 7;

  // ── Seed defaults ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (seededRef.current) return;
    seededRef.current = true;
    seedDefaultTasks(userId).catch((e) => {
      console.warn("Could not seed default tasks:", e);
      seededRef.current = false;
    });
  }, [userId]);

  // ── Firestore real-time listener ─────────────────────────────────────────
  useEffect(() => {
    const q = query(
      collection(db, "tiny_steps"),
      where("userId", "==", userId),
    );

    const unsubscribe = onSnapshot(
      q,
      (snapshot) => {
        const tasks: TaskHabit[] = [];
        const freshIds = new Set<string>();

        snapshot.docs.forEach((docSnap) => {
          const data = docSnap.data();
          const id = docSnap.id;
          const isCompleted: boolean = data.completed ?? false;

          let history: boolean[] = Array(31).fill(false);
          if (Array.isArray(data.history) && data.history.length === 31) {
            history = [...data.history];
          }
          history[currentDay - 1] = isCompleted;

          const isNew =
            !isFirstLoad.current &&
            !knownIdsRef.current.has(id) &&
            data.source === "chatbot";

          freshIds.add(id);

          tasks.push({
            id,
            task: data.task ?? "Untitled task",
            category: domainToCategory(data.domain ?? "GENERAL"),
            time: data.time ?? "Anytime",
            domain: data.domain ?? "GENERAL",
            completed: isCompleted,
            source: data.source ?? "manual",
            history,
            sage_highlighted: data.sage_highlighted ?? false,
            sage_suggested: data.sage_suggested ?? false,
            sage_reason: data.sage_reason ?? null,
            _isNew: isNew,
          });

          if (isNew) {
            setNewTaskToast(data.task ?? "A new step was added for you.");
          }
        });

        isFirstLoad.current = false;
        knownIdsRef.current = freshIds;

        tasks.sort((a, b) => {
          if (a.completed !== b.completed) return a.completed ? 1 : -1;
          if (a.source !== b.source) return a.source === "chatbot" ? -1 : 1;
          return 0;
        });

        setHabits(tasks);
        setLoading(false);
      },
      (error) => {
        console.error("TinySteps Firestore error:", error);
        setLoading(false);
      },
    );

    return () => unsubscribe();
  }, [userId, currentDay]);

  // ── Write helpers ─────────────────────────────────────────────────────────

  const addHabit = async () => {
    try {
      await addDoc(collection(db, "tiny_steps"), {
        userId,
        task: "New Tiny Step",
        category: "New",
        time: "12:00 PM",
        domain: "GENERAL",
        completed: false,
        source: "manual",
        history: Array(31).fill(false),
        date: serverTimestamp(),
      });
    } catch (err) {
      console.error("Error creating explicit task documentation doc:", err);
    }
  };

  const updateHabitField = async (
    id: string,
    field: "task" | "time",
    value: string,
  ) => {
    setHabits((prev) =>
      prev.map((h) => (h.id === id ? { ...h, [field]: value } : h)),
    );
    await updateDoc(doc(db, "tiny_steps", id), { [field]: value });
  };

  const deleteHabit = async (id: string) => {
    try {
      await deleteDoc(doc(db, "tiny_steps", id));
    } catch (err) {
      console.error(
        "Failed to delete specific baseline task target reference:",
        err,
      );
    }
  };

  const toggleComplete = async (id: string, currentDone: boolean) => {
    const newVal = !currentDone;
    let updatedHistory: boolean[] = [];
    setHabits((prev) =>
      prev.map((h) => {
        if (h.id !== id) return h;
        const newHistory = h.history.map((v, i) =>
          i === currentDay - 1 ? newVal : v,
        );
        updatedHistory = newHistory;
        return { ...h, completed: newVal, history: newHistory };
      }),
    );
    await updateDoc(doc(db, "tiny_steps", id), {
      completed: newVal,
      history: updatedHistory,
      completed_at: newVal ? serverTimestamp() : null,
    });
  };

  // ✅ NEW: Handler to log compliance when clicking "I DID MY BEST"
  const handleCompleteDayCheck = () => {
    alert(
      `Amazing work today! You completed ${completedCount} out of ${totalCount} micro-steps. 🌟`,
    );
  };

  // ── Medal logic ───────────────────────────────────────────────────────────

  const getDayReward = (dayNum: number) => {
    const idx = dayNum - 1;
    const done = habits.filter((h) => h.history[idx]).length;
    const total = habits.length;
    if (total === 0 || done === 0) return null;
    if (done === total) return "🏆";
    if (done >= Math.ceil(total / 2)) return "🥈";
    if (done >= 3) return "🥉";
    return null;
  };

  const completedCount = habits.filter((h) => h.completed).length;
  const totalCount = habits.length;
  const progressPct =
    totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      className="fixed inset-0 w-screen h-screen flex flex-col font-sans select-none bg-cover bg-center"
      style={{ backgroundImage: "url('/background_Image.png')" }}
    >
      <div className="absolute inset-0 bg-slate-900/10 backdrop-blur-[2px]" />

      {newTaskToast && (
        <NewTaskToast
          task={newTaskToast}
          onDismiss={() => setNewTaskToast(null)}
        />
      )}

      <header className="fixed top-0 left-0 w-full h-[7vh] flex justify-between items-center px-10 z-50">
        <button
          onClick={() => navigate("/matrix")}
          className="flex items-center gap-2 bg-white/90 px-4 py-1.5 rounded-full shadow-lg border border-slate-200 active:scale-95 transition-all"
        >
          <ArrowLeft size={14} className="text-[#7c3aed]" />
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-800">
            Dashboard
          </span>
        </button>

        <div className="flex items-center gap-3 bg-white/90 px-4 py-1.5 rounded-full shadow-lg border border-slate-200">
          <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">
            Today
          </span>
          <div className="w-24 h-2 bg-slate-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-[#7c3aed] rounded-full transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <span className="text-[9px] font-black text-[#7c3aed]">
            {completedCount}/{totalCount}
          </span>
        </div>

        <Shield
          size={24}
          className="text-[#7c3aed] bg-white/90 p-1 rounded-lg shadow-sm"
        />
      </header>

      <main className="pt-[9vh] h-full flex gap-4 px-6 pb-6 relative z-10 overflow-hidden">
        {/* ── TASK LIST ── */}
        <section className="flex-[4] bg-white/95 backdrop-blur-md rounded-[2.5rem] p-7 shadow-2xl border border-white/50 flex flex-col h-full overflow-hidden">
          <div className="flex justify-between items-end mb-4 px-2">
            <div>
              <h1 className="text-3xl font-black italic text-[#2d1656] tracking-tighter uppercase">
                Tiny <span className="text-[#7c3aed] not-italic">Steps</span>
              </h1>
              <p className="text-[9px] text-slate-400 font-semibold mt-0.5">
                Small actions. Real change. 💜
              </p>
            </div>
            <div className="flex gap-1">
              <div className="w-24 text-center text-[10px] font-black text-slate-500 uppercase tracking-widest mr-4">
                Time
              </div>
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) => (
                <div
                  key={i}
                  className={`w-13 text-center text-[10px] font-black uppercase ${
                    i === dayOfWeek ? "text-[#7c3aed]" : "text-slate-900"
                  }`}
                >
                  {d}
                </div>
              ))}
            </div>
          </div>

          {loading && (
            <div className="flex-1 flex items-center justify-center">
              <div className="flex gap-2 items-center text-purple-400">
                {[0, 150, 300].map((delay) => (
                  <div
                    key={delay}
                    className="w-2 h-2 rounded-full bg-purple-400 animate-bounce"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </div>
            </div>
          )}

          {!loading && (
            <div className="flex-1 overflow-y-auto pr-2 space-y-2 custom-scrollbar scroll-smooth">
              {habits.map((habit) => (
                <div
                  key={habit.id}
                  className={`
                    group flex items-center border px-5 py-3 rounded-2xl shadow-sm
                    transition-all hover:shadow-md
                    ${habit._isNew ? "animate-in slide-in-from-top-2 fade-in duration-500" : ""}
                    ${
                      habit.sage_highlighted
                        ? "bg-purple-50 border-purple-300 hover:border-purple-400"
                        : habit.completed
                          ? "bg-slate-50 border-slate-200 opacity-60"
                          : "bg-white border-slate-100 hover:border-purple-200"
                    }
                  `}
                >
                  <button
                    onClick={() => deleteHabit(habit.id)}
                    className="mr-3 text-slate-300 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 size={14} />
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-[8px] font-black uppercase text-[#7c3aed] tracking-widest">
                        {habit.category}
                      </span>
                      {habit.source === "chatbot" && (
                        <span
                          className={`text-[7px] px-1.5 py-0.5 rounded-full font-black uppercase tracking-widest
                            ${habit._isNew ? "bg-[#7c3aed] text-white animate-pulse" : "bg-purple-100 text-purple-500"}`}
                        >
                          Hope ✦
                        </span>
                      )}
                    </div>
                    {habit.sage_reason && (
                      <span className="text-[8px] text-purple-400 font-semibold block mb-0.5 italic">
                        {habit.sage_reason}
                      </span>
                    )}
                    <input
                      type="text"
                      value={habit.task}
                      onChange={(e) =>
                        updateHabitField(habit.id, "task", e.target.value)
                      }
                      className={`bg-transparent w-full text-[14px] font-bold outline-none focus:text-[#7c3aed] ${
                        habit.completed
                          ? "line-through text-slate-400"
                          : "text-slate-900"
                      }`}
                    />
                  </div>

                  <div className="w-32 flex justify-center items-center border-x border-slate-100 mx-4 text-[11px] font-bold text-slate-700 bg-slate-50/80 p-2 rounded-lg">
                    <Clock size={12} className="mr-2 text-[#7c3aed]" />
                    <input
                      type="text"
                      value={habit.time}
                      onChange={(e) =>
                        updateHabitField(habit.id, "time", e.target.value)
                      }
                      className="bg-transparent w-full outline-none text-center"
                    />
                  </div>

                  <div className="flex gap-1">
                    {[0, 1, 2, 3, 4, 5, 6].map((idx) => {
                      const isToday = idx === dayOfWeek;
                      const isChecked = isToday && habit.completed;
                      return (
                        <button
                          key={idx}
                          disabled={!isToday}
                          onClick={() =>
                            isToday && toggleComplete(habit.id, habit.completed)
                          }
                          className={`w-11 h-11 rounded-xl border-2 flex items-center justify-center transition-all shadow-sm
                            ${
                              isToday
                                ? isChecked
                                  ? "bg-[#7c3aed] text-white border-[#7c3aed]"
                                  : "bg-white border-[#7c3aed] border-dashed hover:border-solid hover:shadow-purple-200"
                                : "bg-slate-100 opacity-20 cursor-not-allowed border-transparent"
                            }`}
                        >
                          {isChecked ? (
                            <CheckCircle2 size={22} strokeWidth={3} />
                          ) : (
                            !isToday && (
                              <Lock size={12} className="text-slate-400" />
                            )
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* ✅ FIXED: Click action handler successfully bound onto the action button element */}
          <button
            onClick={handleCompleteDayCheck}
            className="mt-4 w-full py-4 rounded-2xl bg-[#7c3aed] text-white font-black uppercase tracking-[0.4em] text-[12px] shadow-xl hover:bg-[#6d28d9] transition-all active:scale-95"
          >
            I DID MY BEST TODAY{" "}
            <Heart size={16} fill="white" className="inline ml-2" />
          </button>
        </section>

        {/* ── SIDEBAR ── */}
        <section className="flex-[1.5] flex flex-col h-full gap-4">
          <div className="bg-[#2d1656] p-5 rounded-[2.5rem] shadow-2xl border border-white/10 shrink-0">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase text-purple-300 tracking-widest mb-3">
              <Trophy size={14} /> Mission Control
            </div>
            <div className="space-y-3">
              <div className="group border-b border-white/5 pb-1">
                <span className="text-[7px] font-black text-purple-400/60 uppercase block">
                  3-Month Target
                </span>
                <input
                  value={shortGoal}
                  onChange={(e) => setShortGoal(e.target.value)}
                  className="bg-transparent w-full text-white text-xs font-bold outline-none focus:text-purple-400"
                />
              </div>
              <div className="group">
                <span className="text-[7px] font-black text-purple-400/60 uppercase block">
                  Long-term Vision
                </span>
                <input
                  value={longGoal}
                  onChange={(e) => setLongGoal(e.target.value)}
                  className="bg-transparent w-full text-white text-xs font-bold outline-none focus:text-purple-400"
                />
              </div>
            </div>
          </div>

          {/* ── CALENDAR ── */}
          <div className="bg-white/95 rounded-[2.5rem] p-5 shadow-2xl border border-white flex flex-col flex-1 overflow-hidden min-h-0">
            <h2 className="text-center text-lg font-black uppercase text-slate-900 mb-2">
              {currentMonthName} {currentYear}
            </h2>
            <div className="grid grid-cols-7 gap-1 w-full border-b border-slate-100 pb-1 mb-2">
              {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
                <div
                  key={i}
                  className="text-[9px] font-black text-slate-900 text-center"
                >
                  {d}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1 w-full text-center flex-1 items-center">
              {Array.from({ length: firstDayIndex }).map((_, i) => (
                <div key={`e-${i}`} />
              ))}
              {Array.from({ length: daysInMonth }).map((_, i) => {
                const dayNum = i + 1;
                const isToday = dayNum === currentDay;
                const reward = getDayReward(dayNum);
                return (
                  <div
                    key={dayNum}
                    className={`aspect-square flex items-center justify-center rounded-lg transition-all font-black
                      ${
                        isToday
                          ? "bg-[#7c3aed] text-white shadow-lg scale-105 text-base"
                          : "text-[10px] text-slate-900 hover:bg-slate-50"
                      }`}
                  >
                    {reward ?? dayNum}
                  </div>
                );
              })}
            </div>
            <div className="mt-4 bg-slate-900 text-white rounded-2xl p-3 flex justify-around items-center shrink-0">
              {[
                { emoji: "🏆", label: "100%" },
                { emoji: "🥈", label: "50%" },
                { emoji: "🥉", label: "3+" },
              ].map(({ emoji, label }) => (
                <div key={label} className="flex flex-col items-center">
                  <span className="text-sm">{emoji}</span>
                  <span className="text-[6px] font-black uppercase text-purple-300">
                    {label}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <button
            onClick={addHabit}
            className="w-full py-4 bg-slate-900 text-white rounded-[2rem] flex items-center justify-center gap-3 font-black text-[11px] uppercase tracking-[0.2em] hover:bg-[#7c3aed] transition-all shadow-2xl shrink-0 active:scale-95"
          >
            <Plus size={18} strokeWidth={3} /> Add Task
          </button>
        </section>
      </main>
    </div>
  );
};

export default TinySteps;
