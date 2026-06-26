// Firebase Configuration & Service - Healing with Hope
import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider } from "firebase/auth";
import {
  getFirestore,
  collection,
  addDoc,
  getDocs,
  query,
  serverTimestamp,
  DocumentData,
} from "firebase/firestore";

// --- 1. CONFIGURATION ---
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize services
export const auth = getAuth(app);
export const db = getFirestore(app);
export const googleProvider = new GoogleAuthProvider();

// Type-safe collections helper
export const COLLECTIONS = {
  USERS: "users",
  TINY_STEPS: "tiny_steps",
  HOPE_PAGE: "hope_page",
  STRESS_HISTORY: "stress_history",
  MESSAGES: "messages",
} as const;

console.log("✅ Firebase + Firestore initialized for Healing with Hope!");

// --- 2. TYPES & INTERFACES ---
interface UserTask extends DocumentData {
  id: string;
  title?: string;
  completed?: boolean;
}

// --- 3. FIRESTORE OPERATIONS (UNIFIED FROM PYTHON) ---

/**
 * Save stress/vagal scores to history
 * Replaces: save_stress_score from Python
 */
export const saveStressScore = async (
  userId: string,
  score: number,
  source: string,
) => {
  if (!userId) return;

  try {
    // Path: users/{userId}/stress_history
    const historyRef = collection(
      db,
      COLLECTIONS.USERS,
      userId,
      COLLECTIONS.STRESS_HISTORY,
    );

    await addDoc(historyRef, {
      score: score,
      source: source,
      timestamp: serverTimestamp(), // Modern Firestore way to handle dates
    });

    console.log(`✅ Saved stress score for ${userId}`);
  } catch (error) {
    console.error("❌ Error saving stress score:", error);
    throw error;
  }
};

/**
 * Fetch "Tiny Steps" tasks for a specific user
 * Replaces: get_user_tasks from Python
 */
export const getUserTasks = async (userId: string): Promise<UserTask[]> => {
  if (!userId) return [];

  try {
    // Path: users/{userId}/tiny_steps
    const tasksRef = collection(
      db,
      COLLECTIONS.USERS,
      userId,
      COLLECTIONS.TINY_STEPS,
    );
    const querySnapshot = await getDocs(query(tasksRef));

    return querySnapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    })) as UserTask[];
  } catch (error) {
    console.error("❌ Error fetching tasks:", error);
    return [];
  }
};

export default app;
