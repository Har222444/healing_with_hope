"use client";
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { signInWithEmailAndPassword, signInWithPopup } from "firebase/auth";
import { collection, query, where, getDocs } from "firebase/firestore";
import { auth, googleProvider, db } from "../../services/firebase";
import { FcGoogle } from "react-icons/fc";
import { FaFacebook, FaLinkedin } from "react-icons/fa";
import {
  Lock,
  ArrowRight,
  ArrowLeft,
  ShieldCheck,
  AlertCircle,
  User,
} from "lucide-react";

const Login: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [identifier, setIdentifier] = useState(""); // username or email
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Detect if input is an email
  const isEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

  // Resolve username → email via Firestore
  const resolveEmail = async (
    usernameOrEmail: string,
  ): Promise<string | null> => {
    if (isEmail(usernameOrEmail)) return usernameOrEmail.trim().toLowerCase();

    const q = query(
      collection(db, "users"),
      where("username", "==", usernameOrEmail.trim().toLowerCase()),
    );
    const snapshot = await getDocs(q);
    if (snapshot.empty) return null;
    return snapshot.docs[0].data().email as string;
  };

  // Google Login
  const handleGoogleLogin = async (e: React.MouseEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setLoading(true);
      await signInWithPopup(auth, googleProvider);
      navigate("/avatar-selection");
    } catch (err: any) {
      if (err.code === "auth/cancelled-popup-request") return;
      setError("Google sign-in failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // Username/Email + Password Login
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!identifier.trim()) {
      setError("Please enter your username or email.");
      return;
    }
    if (!password) {
      setError("Please enter your password.");
      return;
    }

    setLoading(true);
    try {
      // Resolve to email
      const email = await resolveEmail(identifier);

      if (!email) {
        setError("Username not found. Please check and try again.");
        return;
      }

      await signInWithEmailAndPassword(auth, email, password);
      navigate("/avatar-selection");
    } catch (err: any) {
      console.error("Login error:", err.code);
      switch (err.code) {
        case "auth/invalid-credential":
        case "auth/wrong-password":
        case "auth/user-not-found":
          setError("Incorrect password. Please try again.");
          break;
        case "auth/invalid-email":
          setError("Please enter a valid email address.");
          break;
        case "auth/too-many-requests":
          setError("Too many attempts. Please try again later.");
          break;
        case "auth/user-disabled":
          setError("This account has been disabled.");
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
      {/* BACKGROUND — same as Signup */}
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: "url('/background_Image.png')" }}
      >
        <div className="absolute inset-0 bg-white/10 backdrop-blur-[2px]" />
      </div>

      {/* TOP NAV */}
      <nav className="absolute top-0 w-full p-10 flex justify-between items-center z-50">
        <button
          onClick={() => navigate("/signup")}
          className="flex items-center gap-3 text-purple-900/40 hover:text-purple-900 transition-all group"
        >
          <div className="w-10 h-10 rounded-full border border-purple-900/10 flex items-center justify-center group-hover:border-purple-900/40 transition-all bg-white/20 backdrop-blur-md">
            <ArrowLeft size={18} />
          </div>
          <span className="text-[10px] font-black uppercase tracking-[0.4em] hidden md:block">
            Back to Signup
          </span>
        </button>
        <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/40 border border-white/60 backdrop-blur-md">
          <ShieldCheck size={14} className="text-purple-600" />
          <span className="text-[9px] font-black text-purple-900 uppercase tracking-widest">
            Secure Entry
          </span>
        </div>
      </nav>

      {/* LOGIN CARD */}
      <div className="relative z-10 w-full max-w-[440px] p-12 bg-white/80 backdrop-blur-3xl rounded-[4rem] border border-white shadow-[0_30px_60px_-15px_rgba(0,0,0,0.1)] animate-in fade-in zoom-in duration-700">
        <div className="text-center mb-8">
          <h2 className="text-4xl font-black text-purple-900 tracking-tighter mb-2 leading-none">
            Welcome <span className="text-purple-600 italic">Back</span>
          </h2>
          <p className="text-purple-800/40 text-[10px] font-black uppercase tracking-[0.3em]">
            Return to your sanctuary
          </p>
        </div>

        {/* ERROR BANNER */}
        {error && (
          <div className="flex items-start gap-3 bg-red-50 border border-red-100 text-red-600 rounded-2xl px-4 py-3 mb-6 animate-in fade-in duration-300">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <p className="text-[11px] font-bold leading-snug">{error}</p>
          </div>
        )}

        {/* SOCIAL GRID */}
        <div className="grid grid-cols-3 gap-4 mb-7">
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={loading}
            className="flex items-center justify-center py-4 bg-white rounded-3xl border border-purple-50 shadow-sm hover:shadow-md hover:scale-105 transition-all active:scale-95 group disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <FcGoogle size={24} className="group-hover:opacity-80" />
          </button>
          <button
            type="button"
            disabled
            title="Coming soon"
            className="flex items-center justify-center py-4 bg-white rounded-3xl border border-purple-50 shadow-sm text-[#1877F2] opacity-40 cursor-not-allowed"
          >
            <FaFacebook size={24} />
          </button>
          <button
            type="button"
            disabled
            title="Coming soon"
            className="flex items-center justify-center py-4 bg-white rounded-3xl border border-purple-50 shadow-sm text-[#0A66C2] opacity-40 cursor-not-allowed"
          >
            <FaLinkedin size={24} />
          </button>
        </div>

        <div className="flex items-center gap-4 mb-7">
          <div className="h-[1px] flex-1 bg-purple-900/5" />
          <span className="text-[8px] font-black text-purple-900/20 uppercase tracking-[0.4em]">
            Or Username
          </span>
          <div className="h-[1px] flex-1 bg-purple-900/5" />
        </div>

        <form onSubmit={handleLogin} className="space-y-3">
          {/* USERNAME OR EMAIL */}
          <div className="relative">
            <User
              className="absolute left-5 top-1/2 -translate-y-1/2 text-purple-300"
              size={18}
            />
            <input
              type="text"
              placeholder="Username or Email"
              value={identifier}
              onChange={(e) => {
                setIdentifier(e.target.value);
                setError(null);
              }}
              className="w-full bg-white border border-purple-50 rounded-2xl py-4 pl-14 pr-4 text-purple-900 placeholder:text-purple-200 focus:outline-none focus:border-purple-400 transition-all text-sm font-bold shadow-sm"
              required
              autoComplete="username"
            />
          </div>

          {/* PASSWORD */}
          <div className="relative">
            <Lock
              className="absolute left-5 top-1/2 -translate-y-1/2 text-purple-300"
              size={18}
            />
            <input
              type="password"
              placeholder="Your Password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError(null);
              }}
              className="w-full bg-white border border-purple-50 rounded-2xl py-4 pl-14 pr-4 text-purple-900 placeholder:text-purple-200 focus:outline-none focus:border-purple-400 transition-all text-sm font-bold shadow-sm"
              required
              autoComplete="current-password"
            />
          </div>

          {/* PREV / NEXT BUTTONS */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => navigate("/signup")}
              disabled={loading}
              className="flex-1 border border-purple-200 text-purple-600 font-black text-[11px] uppercase tracking-[0.2em] py-5 rounded-2xl flex items-center justify-center gap-2 hover:bg-purple-50 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ArrowLeft size={14} /> Previous
            </button>

            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-purple-600 text-white font-black text-[11px] uppercase tracking-[0.2em] py-5 rounded-2xl flex items-center justify-center gap-2 hover:bg-purple-700 transition-all active:scale-95 shadow-[0_15px_30px_-5px_rgba(124,58,237,0.3)] disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Signing in...
                </>
              ) : (
                <>
                  Enter <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>
        </form>

        <p className="text-center mt-8 text-[9px] font-bold text-purple-900/30 uppercase tracking-widest">
          New here?{" "}
          <span
            className="text-purple-600 cursor-pointer hover:underline"
            onClick={() => navigate("/signup")}
          >
            Create Sanctuary
          </span>
        </p>
      </div>

      <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_top_right,_rgba(167,139,250,0.08),_transparent_60%)]" />
    </div>
  );
};

export default Login;
