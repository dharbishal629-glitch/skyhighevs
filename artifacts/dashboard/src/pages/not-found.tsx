import React from "react";
import { Link } from "wouter";
import { GlassCard, GlassButton } from "@/components/ui/cyber-components";
import { AlertTriangle } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <GlassCard glow="red" className="p-10 text-center max-w-sm border border-red-500/20">
        <AlertTriangle className="w-12 h-12 text-red-400 mx-auto mb-4" />
        <h1 className="text-5xl font-display font-bold text-red-300 mb-2">404</h1>
        <p className="text-sm text-slate-500 mb-6">Page not found</p>
        <Link href="/"><GlassButton variant="secondary" size="sm" className="w-full">← Back to Overview</GlassButton></Link>
      </GlassCard>
    </div>
  );
}
