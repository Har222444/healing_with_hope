"use client";
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createUserWithEmailAndPassword, signInWithPopup } from "firebase/auth";
import { auth, googleProvider } from "../../services/firebase";
import { FcGoogle } from "react-icons/fc";
import {
  Lock,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  User,
  Eye,
  EyeOff,
} from "lucide-react";

const Signup: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const toFakeEmail = (uname: string) =>
    `${uname.trim().toLowerCase()}@hope.app`;

  // Google Signup
  const handleGoogleSignup = async (e: React.MouseEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setLoading(true);
      await signInWithPopup(auth, googleProvider);
      navigate("/avatar-selection");
    } catch (err: any) {
      if (err.code === "auth/cancelled-popup-request") return;
      setError("Google sign-up failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Validations
    if (!username.trim()) {
      setError("Please enter a username.");
      return;
    }
    if (username.trim().length < 3) {
      setError("Username must be at least 3 characters.");
      return;
    }
    if (!password) {
      setError("Please enter a password.");
      return;
    }
    if (password.length < 6 && username.trim().toLowerCase() !== "admin") {
      setError("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    // ✅ Direct login bypass if username and password are "admin"
    if (username.trim().toLowerCase() === "admin" && password === "admin") {
      setSuccess("Welcome back, Admin! Logging in...");
      setTimeout(() => navigate("/avatar-selection"), 1200); // Redirects straight into app flow
      setLoading(false);
      return;
    }

    // Everyone else registers via Firebase
    try {
      const fakeEmail = toFakeEmail(username);
      await createUserWithEmailAndPassword(auth, fakeEmail, password);
      setSuccess("Account created! Redirecting...");
      setTimeout(() => navigate("/avatar-selection"), 1200);
    } catch (err: any) {
      console.error("Signup error:", err.code);
      switch (err.code) {
        case "auth/email-already-in-use":
          setError("Username already taken. Please choose another.");
          break;
        case "auth/weak-password":
          setError("Password is too weak. Use at least 6 characters.");
          break;
        case "auth/network-request-failed":
          setError("Network error. Please check your connection.");
          break;
        default:
          setError("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative h-screen w-full flex items-center justify-center overflow-hidden font-sans">
      {/* Background */}
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: "url('/background_Image.png')" }}
      >
        <div className="absolute inset-0 bg-white/10 backdrop-blur-[2px]" />
      </div>

      {/* Nav */}
      <nav className="absolute top-0 w-full p-10 flex justify-end items-center z-50">
        <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/40 border border-white/60 backdrop-blur-md">
          <ShieldCheck size={14} className="text-purple-600" />
          <span className="text-[9px] font-black text-purple-900 uppercase tracking-widest">
            Safe & Secure
          </span>
        </div>
      </nav>

      {/* Card */}
      <div className="relative z-10 w-full max-w-[440px] p-12 bg-white/80 backdrop-blur-3xl rounded-[4rem] border border-white shadow-[0_30px_60px_-15px_rgba(0,0,0,0.1)] animate-in fade-in zoom-in duration-700">
        <div className="text-center mb-8">
          <h2 className="text-4xl font-black text-purple-900 tracking-tighter mb-2 leading-none">
            Create Your{" "}
            <span className="text-purple-600 italic">Sanctuary</span>
          </h2>
          <p className="text-purple-800/40 text-[10px] font-black uppercase tracking-[0.3em]">
            Choose a username &amp; password
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-3 bg-red-50 border border-red-100 text-red-600 rounded-2xl px-4 py-3 mb-5 animate-in fade-in duration-300">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <p className="text-[11px] font-bold leading-snug">{error}</p>
          </div>
        )}

        {/* Success */}
        {success && (
          <div className="flex items-start gap-3 bg-green-50 border border-green-100 text-green-600 rounded-2xl px-4 py-3 mb-5 animate-in fade-in duration-300">
            <ShieldCheck size={16} className="mt-0.5 shrink-0" />
            <p className="text-[11px] font-bold leading-snug">{success}</p>
          </div>
        )}

        {/* Google */}
        <div className="mb-7">
          <button
            type="button"
            onClick={handleGoogleSignup}
            disabled={loading}
            className="w-full flex items-center justify-center gap-3 py-4 bg-white rounded-3xl border border-purple-50 shadow-sm hover:shadow-md hover:scale-[1.02] transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <FcGoogle size={22} />
            <span className="text-[11px] font-black text-purple-900 uppercase tracking-widest">
              Continue with Google
            </span>
          </button>
        </div>

        <div className="flex items-center gap-4 mb-7">
          <div className="h-[1px] flex-1 bg-purple-900/5" />
          <span className="text-[8px] font-black text-purple-900/20 uppercase tracking-[0.4em]">
            Or
          </span>
          <div className="h-[1px] flex-1 bg-purple-900/5" />
        </div>

        <form onSubmit={handleSignup} className="space-y-3">
          {/* Username */}
          <div className="relative">
            <User
              className="absolute left-5 top-1/2 -translate-y-1/2 text-purple-300"
              size={18}
            />
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                setError(null);
              }}
              className="w-full bg-white border border-purple-50 rounded-2xl py-4 pl-14 pr-4 text-purple-900 placeholder:text-purple-200 focus:outline-none focus:border-purple-400 transition-all text-sm font-bold shadow-sm"
              autoComplete="username"
            />
          </div>

          {/* Password */}
          <div className="relative">
            <Lock
              className="absolute left-5 top-1/2 -translate-y-1/2 text-purple-300"
              size={18}
            />
            <input
              type={showPassword ? "text" : "password"}
              placeholder="Password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError(null);
              }}
              className="w-full bg-white border border-purple-50 rounded-2xl py-4 pl-14 pr-12 text-purple-900 placeholder:text-purple-200 focus:outline-none focus:border-purple-400 transition-all text-sm font-bold shadow-sm"
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-5 top-1/2 -translate-y-1/2 text-purple-300 hover:text-purple-500 transition-colors"
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>

          {/* Confirm Password */}
          <div className="relative">
            <Lock
              className="absolute left-5 top-1/2 -translate-y-1/2 text-purple-300"
              size={18}
            />
            <input
              type={showPassword ? "text" : "password"}
              placeholder="Confirm Password"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                setError(null);
              }}
              className="w-full bg-white border border-purple-50 rounded-2xl py-4 pl-14 pr-4 text-purple-900 placeholder:text-purple-200 focus:outline-none focus:border-purple-400 transition-all text-sm font-bold shadow-sm"
              autoComplete="new-password"
            />
          </div>

          {/* Action Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-purple-600 text-white font-black text-[11px] uppercase tracking-[0.2em] py-5 rounded-2xl flex items-center justify-center gap-2 hover:bg-purple-700 transition-all active:scale-95 shadow-[0_15px_30px_-5px_rgba(124,58,237,0.3)] disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  Enter Sanctuary <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_top_right,_rgba(167,139,250,0.08),_transparent_60%)]" />
    </div>
  );
};

export default Signup;
