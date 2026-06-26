"use client";

import type React from "react";
import { createContext, useContext, useState, useEffect } from "react";
import type { User } from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { db } from "../../services/firebase";

interface UserProfile {
  uid: string;
  displayName: string;
  avatarType: "male" | "female";
  healingScore: number;
  createdAt: Date;
}

interface HealingContextType {
  user: User | null;
  profile: UserProfile | null;
  loading: boolean;
  updateProfile: (data: Partial<UserProfile>) => Promise<void>;
  healingScore: number;
  setHealingScore: (score: number) => void;
}

const HealingContext = createContext<HealingContextType | undefined>(undefined);

export const HealingProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [healingScore, setHealingScore] = useState(0);

  useEffect(() => {
    const fetchProfile = async (uid: string) => {
      try {
        const userDoc = await getDoc(doc(db, "users", uid));
        if (userDoc.exists()) {
          const data = userDoc.data();
          setProfile({
            ...data,
            uid,
            createdAt: data.createdAt?.toDate() || new Date(),
          } as UserProfile);
        }
      } catch (error) {
        console.error("Error fetching profile:", error);
      }
    };

    // This will be connected to Firebase Auth listener
    setLoading(false);
  }, []);

  const updateProfile = async (data: Partial<UserProfile>) => {
    if (!user) return;
    try {
      // Will integrate with Firestore update
      setProfile((prev) => (prev ? { ...prev, ...data } : null));
    } catch (error) {
      console.error("Error updating profile:", error);
    }
  };

  return (
    <HealingContext.Provider
      value={{
        user,
        profile,
        loading,
        updateProfile,
        healingScore,
        setHealingScore,
      }}
    >
      {children}
    </HealingContext.Provider>
  );
};

export const useHealing = () => {
  const context = useContext(HealingContext);
  if (!context) {
    throw new Error("useHealing must be used within HealingProvider");
  }
  return context;
};
