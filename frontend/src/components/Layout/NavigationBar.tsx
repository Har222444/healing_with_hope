"use client";
import * as React from "react";
import { Link, useLocation } from "react-router-dom";
import {
  MessageCircle,
  BarChart3,
  Share2,
  Settings as SettingsIcon,
} from "lucide-react";

export default function NavigationBar() {
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path;

  return (
    <nav className="relative z-[100] flex items-center justify-between px-12 h-16 bg-white/90 backdrop-blur-md border-b border-purple-100/50 shadow-sm">
      {/* Brand Logo */}
      <Link to="/" className="flex items-center gap-3">
        <div className="w-10 h-10 bg-gradient-to-br from-[#7c3aed] to-[#a78bfa] rounded-xl flex items-center justify-center font-black text-white shadow-md">
          H
        </div>
        <span className="text-[11px] font-black tracking-[0.4em] uppercase text-[#4c1d95]">
          Healing Hope
        </span>
      </Link>

      {/* Main Links - Settings is now INSIDE this group */}
      <div className="flex items-center gap-1 bg-[#f5f3ff] p-1.5 rounded-2xl border border-purple-100/30">
        <Link
          to="/"
          className={`px-6 py-2 rounded-xl text-[9px] font-black tracking-widest flex items-center gap-2 transition-all ${
            isActive("/")
              ? "bg-white text-[#7c3aed] shadow-sm"
              : "text-[#7c3aed]/40 hover:text-[#7c3aed]"
          }`}
        >
          <MessageCircle size={14} /> CHAT
        </Link>

        <Link
          to="/healing-matrix"
          className={`px-6 py-2 rounded-xl text-[9px] font-black tracking-widest flex items-center gap-2 transition-all ${
            isActive("/healing-matrix")
              ? "bg-white text-[#7c3aed] shadow-sm"
              : "text-[#7c3aed]/40 hover:text-[#7c3aed]"
          }`}
        >
          <Share2 size={14} /> PATHWAYS
        </Link>

        <Link
          to="/progress"
          className={`px-6 py-2 rounded-xl text-[9px] font-black tracking-widest flex items-center gap-2 transition-all ${
            isActive("/progress")
              ? "bg-white text-[#7c3aed] shadow-sm"
              : "text-[#7c3aed]/40 hover:text-[#7c3aed]"
          }`}
        >
          <BarChart3 size={14} /> PROGRESS
        </Link>

        {/* SETTINGS moved inside the group */}
        <Link
          to="/settings"
          className={`px-6 py-2 rounded-xl text-[9px] font-black tracking-widest flex items-center transition-all ${
            isActive("/settings")
              ? "bg-white text-[#7c3aed] shadow-sm"
              : "text-[#7c3aed]/40 hover:text-[#7c3aed]"
          }`}
        >
          SETTINGS
        </Link>
      </div>

      {/* Right side is now empty to keep the center group balanced */}
      <div className="w-40 flex justify-end">
        {/* You can leave this empty or add a small profile name later */}
      </div>
    </nav>
  );
}
