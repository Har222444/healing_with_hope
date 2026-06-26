"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Settings,
  MessageSquare,
  Layout,
  Activity,
  Trash2,
  Mic,
  Heart,
} from "lucide-react";
import {
  collection,
  addDoc,
  onSnapshot,
  query,
  orderBy,
  serverTimestamp,
  deleteDoc,
  getDocs,
  where,
} from "firebase/firestore";

import { db } from "../../services/firebase";
import { api } from "../../services/api";
import type { ChatResponse } from "../../services/api";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  text: string;
  sender: "user" | "assistant";
  timestamp: any;
  emotion?: string;
  show_menu?: boolean;
  menu_options?: string[];
  option_ids?: string[];
  userId?: string;
}

// ── Emotion badge ─────────────────────────────────────────────────────────────

const EmotionBadge = ({ emotion }: { emotion?: string }) => {
  if (!emotion || emotion === "calm" || emotion === "neutral") return null;
  const map: Record<string, { color: string; label: string }> = {
    panic: { color: "bg-red-100 text-red-600", label: "😰 Panic" },
    sad: { color: "bg-blue-100 text-blue-600", label: "💙 Sad" },
    stuck: { color: "bg-yellow-100 text-yellow-700", label: "🤔 Stuck" },
    hopeless: { color: "bg-gray-100 text-gray-600", label: "🌫 Hopeless" },
    suicidal: { color: "bg-red-200 text-red-800", label: "🆘 Crisis" },
    anxious: { color: "bg-orange-100 text-orange-600", label: "😟 Anxious" },
  };
  const style = map[emotion.toLowerCase()] ?? {
    color: "bg-purple-100 text-purple-600",
    label: emotion,
  };
  return (
    <span
      className={`inline-block text-[8px] font-black px-2 py-0.5 rounded-full mt-1 ${style.color}`}
    >
      {style.label}
    </span>
  );
};

// ── Component ─────────────────────────────────────────────────────────────────

const ChatHub: React.FC = () => {
  const navigate = useNavigate();

  const [showSettings, setShowSettings] = useState(false);
  const [input, setInput] = useState("");
  const [gender, setGender] = useState("female");
  const [isLoading, setIsLoading] = useState(false);
  const [avatarState, setAvatarState] = useState<"listening" | "talking">(
    "listening",
  );
  const [chatState, setChatState] = useState("NORMAL");
  const [currentEmotion, setCurrentEmotion] = useState("calm");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [firestoreOk, setFirestoreOk] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  // Unified userId matching TinySteps and Python orchestration script
  const [userId] = useState(() => {
    const saved = localStorage.getItem("chat_user_id");
    if (saved) return saved;
    const newId = `user_${Math.random().toString(36).substring(2, 11)}`;
    localStorage.setItem("chat_user_id", newId);
    return newId;
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Load saved avatar preference
  useEffect(() => {
    const savedGender = localStorage.getItem("userAvatar");
    if (savedGender) setGender(savedGender);
  }, []);

  // Firestore real-time listener for chat messages
  useEffect(() => {
    let unsubscribe = () => {};
    try {
      const q = query(
        collection(db, "messages"),
        where("userId", "==", userId),
        orderBy("timestamp", "asc"),
      );
      unsubscribe = onSnapshot(
        q,
        (snapshot) => {
          setFirestoreOk(true);
          const msgs = snapshot.docs.map((docSnap) => ({
            id: docSnap.id,
            ...docSnap.data(),
          })) as ChatMessage[];
          setMessages(msgs);
          setTimeout(scrollToBottom, 100);
        },
        (error) => {
          console.warn("Firestore snapshot failure, fallback enabled:", error);
          setFirestoreOk(false);
        },
      );
    } catch {
      setFirestoreOk(false);
    }
    return () => unsubscribe();
  }, [userId]);

  // Avatar reacts to loading state
  useEffect(() => {
    setAvatarState(isLoading ? "talking" : "listening");
  }, [isLoading]);

  // ── Save message to Firestore (or local fallback) ─────────────────────────

  const addMessage = useCallback(
    async (msg: Omit<ChatMessage, "id">) => {
      if (firestoreOk) {
        try {
          await addDoc(collection(db, "messages"), {
            ...msg,
            userId,
            timestamp: serverTimestamp(),
          });
          return;
        } catch (err) {
          console.warn("Write transaction error, executing memory push:", err);
          setFirestoreOk(false);
        }
      }
      // Local fallback when Firestore is temporarily blocked or resolving metadata
      setMessages((prev) => [
        ...prev,
        { ...msg, id: `local_${Date.now()}`, timestamp: new Date() },
      ]);
      setTimeout(scrollToBottom, 100);
    },
    [firestoreOk, userId],
  );

  // ── Voice input ───────────────────────────────────────────────────────────

  const toggleVoice = async () => {
    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert("Voice input not supported in this browser layout.");
      return;
    }

    const rec = new SpeechRecognition();
    rec.continuous = false;
    rec.interimResults = false;
    rec.lang = "en-US";

    rec.onresult = (e: any) => {
      const resultText = e.results[0][0].transcript;
      setInput(resultText);
    };

    rec.onend = () => setIsRecording(false);
    rec.onerror = () => setIsRecording(false);

    recognitionRef.current = rec;
    setIsRecording(true);
    rec.start();
  };

  // ── CORE: send message to backend ─────────────────────────────────────────

  const handleSendMessage = async (
    overrideText?: string,
    overrideId?: string,
  ) => {
    const displayText = (
      overrideText !== undefined ? overrideText : input
    ).trim();
    if (!displayText || isLoading) return;

    const backendMessage = overrideId ?? displayText;

    setInput("");
    setIsLoading(true);
    setShowSettings(false);

    // Save user utterance to history (triggers the inference model analysis run)
    await addMessage({ text: displayText, sender: "user", timestamp: null });

    try {
      const response: ChatResponse = await api.sendMessage({
        user_id: userId,
        message: backendMessage,
        state: chatState,
      });

      if (response.state) setChatState(response.state);

      const incomingEmotion =
        response.detected_emotion?.toLowerCase() || "calm";
      setCurrentEmotion(incomingEmotion);

      const replyText: string =
        response.text || response.response || "I'm here with you. 💜";

      const rawOptions: any[] =
        (response.menu_options as any[]) || response.options || [];
      const rawIds: any[] = (response.option_ids as any[]) || [];

      const menuLabels: string[] = rawOptions.map((o) =>
        typeof o === "string" ? o : (o.label ?? String(o)),
      );

      const menuIds: string[] =
        rawIds.length === menuLabels.length
          ? rawIds.map((o) => (typeof o === "string" ? o : (o.id ?? String(o))))
          : menuLabels;

      await addMessage({
        text: replyText,
        sender: "assistant",
        timestamp: null,
        show_menu: response.show_menu || menuLabels.length > 0,
        menu_options: menuLabels,
        option_ids: menuIds,
        emotion: incomingEmotion,
      });
    } catch (err) {
      console.error("Chat routing error:", err);
      await addMessage({
        text: "I am listening closely. Let's trace through this one small step at a time. 💜",
        sender: "assistant",
        timestamp: null,
        show_menu: false,
        emotion: "calm",
      });
    } finally {
      setIsLoading(false);
    }
  };

  // ── Clear chat ────────────────────────────────────────────────────────────

  const clearChat = async () => {
    if (!window.confirm("Are you sure you want to clear your chat history?"))
      return;
    if (firestoreOk) {
      try {
        const q = query(
          collection(db, "messages"),
          where("userId", "==", userId),
        );
        const snapshot = await getDocs(q);
        await Promise.all(
          snapshot.docs.map((docSnap) => deleteDoc(docSnap.ref)),
        );
      } catch (err) {
        console.error("Error clearing backend logs:", err);
      }
    }
    setMessages([]);
    setChatState("NORMAL");
    setCurrentEmotion("calm");
    setShowSettings(false);
  };

  return (
    <div className="fixed inset-0 flex flex-col bg-[#7c3aed]">
      {/* HEADER */}
      <header className="h-16 bg-[#6d28d9] flex items-center justify-between px-8 z-50 shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-white rounded-xl flex items-center justify-center font-black text-[#7c3aed] italic">
            H
          </div>
          <h1 className="text-xs font-black tracking-[0.3em] text-white uppercase italic">
            Healing Hope
          </h1>
        </div>
        <nav className="flex items-center gap-1 bg-white/10 p-1 rounded-2xl">
          <button className="flex items-center gap-2 px-6 py-2 bg-white text-[#7c3aed] rounded-xl text-[9px] font-black">
            <MessageSquare size={14} /> CHAT
          </button>
          <button
            onClick={() => navigate("/matrix")}
            className="px-6 py-2 text-white/60 text-[9px] font-black hover:text-white transition-colors flex items-center justify-center"
          >
            <Layout size={14} />
          </button>
          <button
            onClick={() => navigate("/progress")}
            className="px-6 py-2 text-white/60 text-[9px] font-black hover:text-white transition-colors flex items-center justify-center"
          >
            <Activity size={14} />
          </button>
        </nav>
        <span
          className="text-[10px] font-black text-white/80 uppercase cursor-pointer hover:text-white transition-colors"
          onClick={() => navigate("/settings")}
        >
          Settings
        </span>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* AVATAR PANEL */}
        <div className="w-[45%] flex flex-col bg-black border-r border-white/10 relative">
          <video
            key={`${gender}-${avatarState}`}
            autoPlay
            loop
            muted
            playsInline
            className="absolute inset-0 w-full h-full object-cover"
          >
            <source
              src={`/assets/avatar/${gender}/${avatarState}.mp4`}
              type="video/mp4"
            />
          </video>
          <div className="absolute inset-0 bg-gradient-to-t from-[#2d1656]/40 to-transparent" />
          <div className="absolute bottom-0 left-0 w-full h-16 bg-[#6d28d9] border-t border-white/10 flex items-center justify-between px-6 z-20">
            <div className="flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full animate-pulse ${isLoading ? "bg-yellow-400" : "bg-green-400"}`}
              />
              <span className="text-[10px] font-black text-white/70 uppercase tracking-widest">
                {isLoading ? "Thinking..." : "System Active"}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <Heart size={10} className="text-white/50" />
              <span className="text-[9px] font-black text-white/60 uppercase tracking-wider">
                {currentEmotion}
              </span>
            </div>
          </div>
        </div>

        {/* CHAT PANEL */}
        <div className="flex-1 flex flex-col relative bg-[#1a0b2e]">
          <div
            className="absolute inset-0 bg-cover bg-center pointer-events-none z-0 opacity-40"
            style={{ backgroundImage: "url('/background_Image.png')" }}
          />

          {/* Chat sub-header */}
          <div className="h-12 flex justify-between items-center px-8 bg-[#6d28d9]/40 backdrop-blur-md relative z-30 border-b border-white/10">
            <span className="text-[9px] font-black tracking-widest text-white/90 uppercase">
              Safe Space
            </span>
            <div className="relative">
              <button
                onClick={() => setShowSettings(!showSettings)}
                className="flex items-center gap-2 px-4 py-1.5 bg-[#7c3aed] text-white rounded-xl shadow-lg border border-white/20 transition-transform active:scale-95"
              >
                <span className="text-[8px] font-black uppercase">
                  Message Settings
                </span>
                <Settings size={12} />
              </button>
              {showSettings && (
                <div className="absolute right-0 top-12 w-48 bg-white rounded-2xl shadow-2xl p-2 z-50">
                  <button
                    onClick={clearChat}
                    className="w-full flex items-center gap-3 p-3 hover:bg-red-50 rounded-xl text-[10px] font-bold text-red-500 transition-colors"
                  >
                    <Trash2 size={14} /> CLEAR CHAT
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 relative z-10 space-y-4">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center opacity-60">
                <Heart size={32} className="text-purple-300 mb-3" />
                <p className="text-white/60 text-xs font-bold">
                  This is your safe space.
                </p>
                <p className="text-white/40 text-[10px] mt-1">
                  Share how you're feeling today.
                </p>
              </div>
            )}

            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex ${m.sender === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] px-4 py-3 rounded-2xl text-xs font-bold shadow-md ${
                    m.sender === "user"
                      ? "bg-[#7c3aed] text-white rounded-tr-none"
                      : "bg-white/90 text-[#4c1d95] rounded-tl-none backdrop-blur-sm"
                  }`}
                >
                  <div className="leading-relaxed whitespace-pre-wrap">
                    {m.text}
                  </div>

                  {m.sender === "assistant" && (
                    <EmotionBadge emotion={m.emotion} />
                  )}

                  {m.sender === "assistant" &&
                    m.show_menu &&
                    Array.isArray(m.menu_options) &&
                    m.menu_options.length > 0 && (
                      <div className="mt-3 flex flex-col gap-2">
                        {m.menu_options.map((label, i) => {
                          const id = m.option_ids?.[i] ?? label;
                          return (
                            <button
                              key={i}
                              onClick={() => handleSendMessage(label, id)}
                              disabled={isLoading}
                              className="w-full text-left bg-purple-100/80 hover:bg-[#7c3aed] hover:text-white text-[#7c3aed] px-3 py-2 rounded-xl transition-all duration-200 border border-purple-200 disabled:opacity-50 text-[10px] font-bold"
                            >
                              {label}
                            </button>
                          );
                        })}
                      </div>
                    )}
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white/90 px-4 py-3 rounded-2xl rounded-tl-none shadow-md">
                  <div className="flex gap-1 items-center h-4">
                    {[0, 150, 300].map((delay) => (
                      <span
                        key={delay}
                        className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input bar */}
          <div className="p-4 flex flex-col items-center relative z-20">
            <div className="w-[94%] relative">
              <button
                onClick={toggleVoice}
                className={`absolute left-3 top-1/2 -translate-y-1/2 p-2 rounded-full z-10 transition-all ${
                  isRecording
                    ? "bg-red-500 animate-pulse scale-110 text-white"
                    : "bg-[#7c3aed] text-white hover:bg-[#6d28d9]"
                }`}
              >
                <Mic size={16} />
              </button>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" && !e.shiftKey && handleSendMessage()
                }
                placeholder={
                  isRecording ? "🎙 Listening..." : "How are you feeling today?"
                }
                disabled={isLoading}
                className="w-full bg-white/95 border-2 border-purple-200 rounded-full py-4 pl-14 pr-32 text-sm font-bold text-[#4c1d95] focus:outline-none focus:border-[#7c3aed] shadow-2xl transition-all disabled:opacity-60"
              />
              <button
                onClick={() => handleSendMessage()}
                disabled={isLoading || !input.trim()}
                className="absolute right-3 top-1/2 -translate-y-1/2 bg-[#7c3aed] text-white px-10 py-2.5 rounded-full text-[10px] font-black transition-all hover:bg-[#6d28d9] disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {isLoading ? "..." : "SEND"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatHub;
