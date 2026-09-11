/**
 * Componente de Cabeçalho Global Acessível (WCAG 2.1 AA).
 *
 * Inclui link direto para o conteúdo principal (skip-to-content),
 * navegação semântica por teclado e sino de notificações reativo.
 *
 * @a11y Garante conformidade com foco visível, aria-labels explícitos e aria-live polite.
 */

"use client";

import React from "react";
import { Bell, Briefcase, FileText, BarChart3, Sparkles } from "lucide-react";

interface HeaderProps {
  activeTab: "kanban" | "match" | "analytics" | "resume";
  onTabChange: (tab: "kanban" | "match" | "analytics" | "resume") => void;
  unreadCount: number;
  onOpenNotifications: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  onTabChange,
  unreadCount,
  onOpenNotifications,
}) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-40">
      {/* Skip Link para usuários de leitores de tela e teclado */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-sky-500 focus:text-white focus:rounded-md focus:outline-none focus:ring-2 focus:ring-white"
      >
        Pular para o conteúdo principal
      </a>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Marca / Identidade */}
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-lg bg-sky-500 flex items-center justify-center text-white shadow-md">
            <Sparkles className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <span className="text-lg font-bold text-white tracking-tight">
              ThothCVs <span className="text-sky-400">AI</span>
            </span>
            <span className="hidden sm:inline-block ml-2 text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded-full">
              Personal ATS
            </span>
          </div>
        </div>

        {/* Navegação Semântica por Abas */}
        <nav aria-label="Navegação Principal" className="flex items-center space-x-1 sm:space-x-2">
          <button
            type="button"
            onClick={() => onTabChange("kanban")}
            className={`px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors focus:outline-none focus:ring-2 focus:ring-sky-400 ${
              activeTab === "kanban"
                ? "bg-sky-600 text-white shadow"
                : "text-slate-300 hover:text-white hover:bg-slate-800"
            }`}
            aria-current={activeTab === "kanban" ? "page" : undefined}
          >
            <Briefcase className="w-4 h-4" aria-hidden="true" />
            <span>Kanban ATS</span>
          </button>

          <button
            type="button"
            onClick={() => onTabChange("match")}
            className={`px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors focus:outline-none focus:ring-2 focus:ring-sky-400 ${
              activeTab === "match"
                ? "bg-sky-600 text-white shadow"
                : "text-slate-300 hover:text-white hover:bg-slate-800"
            }`}
            aria-current={activeTab === "match" ? "page" : undefined}
          >
            <Sparkles className="w-4 h-4" aria-hidden="true" />
            <span>Análise & Match</span>
          </button>

          <button
            type="button"
            onClick={() => onTabChange("analytics")}
            className={`px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors focus:outline-none focus:ring-2 focus:ring-sky-400 ${
              activeTab === "analytics"
                ? "bg-sky-600 text-white shadow"
                : "text-slate-300 hover:text-white hover:bg-slate-800"
            }`}
            aria-current={activeTab === "analytics" ? "page" : undefined}
          >
            <BarChart3 className="w-4 h-4" aria-hidden="true" />
            <span className="hidden md:inline">Métricas de Sucesso</span>
            <span className="md:hidden">Métricas</span>
          </button>

          <button
            type="button"
            onClick={() => onTabChange("resume")}
            className={`px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors focus:outline-none focus:ring-2 focus:ring-sky-400 ${
              activeTab === "resume"
                ? "bg-sky-600 text-white shadow"
                : "text-slate-300 hover:text-white hover:bg-slate-800"
            }`}
            aria-current={activeTab === "resume" ? "page" : undefined}
          >
            <FileText className="w-4 h-4" aria-hidden="true" />
            <span className="hidden md:inline">Currículo Atual</span>
            <span className="md:hidden">Currículo</span>
          </button>
        </nav>

        {/* Central de Notificações Acessível */}
        <div className="flex items-center">
          <button
            type="button"
            onClick={onOpenNotifications}
            className="relative p-2 text-slate-300 hover:text-white rounded-lg hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400 transition-colors"
            aria-label={`Notificações: ${unreadCount} não lidas`}
          >
            <Bell className="w-5 h-5" aria-hidden="true" />
            {unreadCount > 0 && (
              <span
                aria-live="polite"
                className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white shadow"
              >
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>
        </div>
      </div>
    </header>
  );
};
