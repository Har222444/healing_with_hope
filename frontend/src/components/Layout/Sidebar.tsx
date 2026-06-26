"use client"

import React from "react"
import { useNavigate } from "react-router-dom"
import { motion } from "framer-motion"

interface SidebarItem {
  icon: string
  label: string
  path: string
}

const sidebarItems: SidebarItem[] = [
  { icon: "💬", label: "Home/Chat", path: "/chat" },
  { icon: "📊", label: "Progress", path: "/progress" },
  { icon: "⚙️", label: "Settings", path: "/settings" },
]

export const Sidebar: React.FC = () => {
  const navigate = useNavigate()
  const [hoveredItem, setHoveredItem] = React.useState<string | null>(null)

  return (
    <motion.div
      className="fixed right-0 top-0 h-screen w-20 md:w-24 backdrop-blur-md bg-white/30 border-l border-white/20 flex flex-col items-center justify-center gap-8"
      initial={{ x: 100 }}
      animate={{ x: 0 }}
      transition={{ duration: 0.3 }}
    >
      {sidebarItems.map((item) => (
        <motion.button
          key={item.path}
          onClick={() => navigate(item.path)}
          onMouseEnter={() => setHoveredItem(item.path)}
          onMouseLeave={() => setHoveredItem(null)}
          className="relative flex items-center justify-center w-16 h-16 rounded-full hover:bg-purple-500/20 transition-colors"
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
        >
          <span className="text-2xl">{item.icon}</span>
          {hoveredItem === item.path && (
            <motion.span
              className="absolute right-20 text-sm font-medium text-purple-900 whitespace-nowrap"
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
            >
              {item.label}
            </motion.span>
          )}
        </motion.button>
      ))}

      <motion.button
        onClick={() => {
          // Logout logic
          navigate("/")
        }}
        className="absolute bottom-8 flex items-center justify-center w-16 h-16 rounded-full hover:bg-red-500/20 transition-colors"
        whileHover={{ scale: 1.1 }}
      >
        <span className="text-2xl">🚪</span>
      </motion.button>
    </motion.div>
  )
}
