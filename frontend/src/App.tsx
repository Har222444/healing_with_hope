"use client";
import * as React from "react";
import { useEffect } from "react";
import { db } from "../services/firebase";
import { collection, addDoc } from "firebase/firestore";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  useLocation,
} from "react-router-dom";

// Components
import NavigationBar from "./components/Layout/NavigationBar";
import Hero from "./page-components/Hero";
import Signup from "./page-components/Signup";
import Login from "./page-components/Login";
import AvatarSelection from "./page-components/AvatarSelection";
import ChatHub from "./page-components/ChatHub";
import HealingMatrix from "./page-components/HealingMatrix";
import TinySteps from "./page-components/TinySteps";
import ProgressDashboard from "./page-components/ProgressDashboard";
import FutureBloom from "./page-components/FutureBloom";
import Settings from "./page-components/Settings";

const AppContent = () => {
  const location = useLocation();

  const testFirebase = async () => {
    try {
      const docRef = await addDoc(collection(db, "test_connection"), {
        message: "Hello from frontend!",
        timestamp: new Date(),
      });
      console.log("✅ Firebase test successful! Doc ID:", docRef.id);
    } catch (error) {
      console.error("❌ Firebase test failed:", error);
    }
  };

  useEffect(() => {
    testFirebase();
  }, []);

  // Hide nav on auth + landing pages
  const hideNavPaths = ["/", "/signup", "/login", "/avatar-selection"];
  const shouldHideNav = hideNavPaths.includes(location.pathname);

  return (
    <div className="min-h-screen bg-white">
      {!shouldHideNav && <NavigationBar />}
      <Routes>
        <Route path="/" element={<Hero />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/login" element={<Login />} />
        <Route path="/avatar-selection" element={<AvatarSelection />} />
        <Route path="/chat" element={<ChatHub />} />
        <Route path="/healing-matrix" element={<HealingMatrix />} />
        <Route path="/tiny-steps" element={<TinySteps />} />
        <Route path="/futurebloom" element={<FutureBloom />} />
        <Route path="/progress" element={<ProgressDashboard />} />
        <Route path="/settings" element={<Settings />} />
        <Route
          path="*"
          element={
            <div className="p-20 text-center text-rose-900 font-bold">
              404 - Page Not Found
            </div>
          }
        />
      </Routes>
    </div>
  );
};

export default function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}
