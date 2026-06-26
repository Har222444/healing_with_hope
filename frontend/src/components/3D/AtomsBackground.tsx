"use client";
import React, { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, Sphere, Stars } from "@react-three/drei";
import * as THREE from "three";

const Atoms = () => {
  const groupRef = useRef<THREE.Group>(null);

  // Create a randomized set of points for the "Neural Network"
  const particles = useMemo(() => {
    const temp = [];
    for (let i = 0; i < 50; i++) {
      const x = (Math.random() - 0.5) * 10;
      const y = (Math.random() - 0.5) * 10;
      const z = (Math.random() - 0.5) * 10;
      temp.push({ position: [x, y, z] });
    }
    return temp;
  }, []);

  // Animation loop: subtle rotation
  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += 0.002;
      groupRef.current.rotation.x += 0.001;
    }
  });

  return (
    <group ref={groupRef}>
      {particles.map((particle, i) => (
        <Float key={i} speed={2} rotationIntensity={1} floatIntensity={2}>
          <Sphere args={[0.05, 16, 16]} position={particle.position as any}>
            <meshStandardMaterial
              color="#7c3aed"
              emissive="#7c3aed"
              emissiveIntensity={2}
              transparent
              opacity={0.6}
            />
          </Sphere>
        </Float>
      ))}
    </group>
  );
};

const AtomsBackground = () => {
  return (
    <div className="absolute inset-0 z-0 bg-slate-50">
      <Canvas camera={{ position: [0, 0, 8], fov: 45 }}>
        <ambientLight intensity={0.5} />
        <pointLight position={[10, 10, 10]} intensity={1} color="#7c3aed" />
        <spotLight position={[-10, -10, -10]} intensity={0.5} color="#6d28d9" />

        <Atoms />

        {/* Subtle star field for depth */}
        <Stars
          radius={100}
          depth={50}
          count={5000}
          factor={4}
          saturation={0}
          fade
          speed={1}
        />

        {/* Adds a slight fog to the 3D world for professional depth */}
        <fog attach="fog" args={["#f8fafc", 5, 15]} />
      </Canvas>
    </div>
  );
};

export default AtomsBackground;
