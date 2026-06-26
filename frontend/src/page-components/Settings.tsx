"use client";
import React, { useState } from "react";
import {
  User,
  Bell,
  Shield,
  Palette,
  Save,
  Moon,
  Zap,
  Lock,
} from "lucide-react";

const Settings: React.FC = () => {
  const [name, setName] = useState("Alex");
  const [darkMode, setDarkMode] = useState(true);
  const [notifications, setNotifications] = useState(true);

  return (
    <div
      className="min-h-screen text-white p-6 lg:p-12 bg-cover bg-center bg-fixed"
      style={{ backgroundImage: "url('/background_Image.png')" }}
    >
      <div className="max-w-4xl mx-auto">
        {/* HEADER */}
        <header className="mb-12">
          <h1 className="text-5xl font-black tracking-tighter text-white">
            SET<span className="text-indigo-500">TINGS</span>
          </h1>
          <p className="text-white/40 mt-3 font-medium uppercase tracking-[0.2em] text-xs">
            Personalize your sanctuary and neural preferences.
          </p>
        </header>

        <div className="space-y-8">
          {/* PROFILE SECTION - GLASS CARD */}
          <section className="bg-black/40 backdrop-blur-3xl p-10 rounded-[40px] border border-white/10 shadow-2xl">
            <div className="flex items-center gap-3 mb-8 text-indigo-400 font-black tracking-widest uppercase text-sm">
              <User size={20} strokeWidth={3} /> <h2>Account Profile</h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div className="space-y-3">
                <label className="text-[10px] font-black text-white/30 uppercase tracking-widest ml-1">
                  Display Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full p-5 rounded-2xl bg-white/5 border border-white/10 focus:border-indigo-500 focus:bg-indigo-500/5 outline-none transition-all text-sm"
                />
              </div>
              <div className="space-y-3">
                <label className="text-[10px] font-black text-white/30 uppercase tracking-widest ml-1">
                  System ID (Email)
                </label>
                <div className="w-full p-5 rounded-2xl bg-white/[0.02] border border-white/5 text-white/20 text-sm flex items-center justify-between">
                  user@iit.ac.lk
                  <Lock size={14} />
                </div>
              </div>
            </div>
          </section>

          {/* PREFERENCES GRID */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <section className="bg-black/40 backdrop-blur-3xl p-10 rounded-[40px] border border-white/10 shadow-2xl">
              <div className="flex items-center gap-3 mb-8 text-emerald-400 font-black tracking-widest uppercase text-sm">
                <Palette size={20} strokeWidth={3} /> <h2>Appearance</h2>
              </div>
              <div className="flex items-center justify-between p-5 bg-white/5 rounded-2xl border border-white/5">
                <div className="flex items-center gap-3">
                  <Moon size={18} className="text-white/40" />
                  <span className="text-sm font-bold">Dark Mode</span>
                </div>
                <button
                  onClick={() => setDarkMode(!darkMode)}
                  className={`w-14 h-7 rounded-full relative transition-colors duration-300 ${
                    darkMode ? "bg-indigo-600" : "bg-white/10"
                  }`}
                >
                  <div
                    className={`absolute top-1 w-5 h-5 bg-white rounded-full transition-all duration-300 ${
                      darkMode ? "left-8" : "left-1"
                    }`}
                  />
                </button>
              </div>
            </section>

            <section className="bg-black/40 backdrop-blur-3xl p-10 rounded-[40px] border border-white/10 shadow-2xl">
              <div className="flex items-center gap-3 mb-8 text-rose-400 font-black tracking-widest uppercase text-sm">
                <Bell size={20} strokeWidth={3} /> <h2>Notifications</h2>
              </div>
              <div className="flex items-center justify-between p-5 bg-white/5 rounded-2xl border border-white/5">
                <div className="flex items-center gap-3">
                  <Zap size={18} className="text-white/40" />
                  <span className="text-sm font-bold">Real-time Alerts</span>
                </div>
                <button
                  onClick={() => setNotifications(!notifications)}
                  className={`w-14 h-7 rounded-full relative transition-colors duration-300 ${
                    notifications ? "bg-indigo-600" : "bg-white/10"
                  }`}
                >
                  <div
                    className={`absolute top-1 w-5 h-5 bg-white rounded-full transition-all duration-300 ${
                      notifications ? "left-8" : "left-1"
                    }`}
                  />
                </button>
              </div>
            </section>
          </div>

          <div className="flex justify-end pt-6">
            <button className="group flex items-center gap-3 px-12 py-5 bg-white text-black rounded-[24px] font-black uppercase text-xs tracking-[0.2em] hover:bg-indigo-500 hover:text-white transition-all active:scale-95 shadow-2xl">
              <Save size={18} strokeWidth={3} /> Save Configuration
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
