"use client";

import React, { useEffect, useRef } from "react";
import { NotificationItem } from "@/types";
import {
  X,
  Bell,
  CheckCheck,
  Radar,
  Calendar,
  Clock,
} from "lucide-react";

/**
 * Propriedades do componente NotificationDrawer.
 *
 * @interface NotificationDrawerProps
 * @property {boolean} isOpen - Controla a visibilidade do painel de notificações.
 * @property {() => void} onClose - Callback acionado para fechar o painel.
 * @property {NotificationItem[]} notifications - Lista de notificações e lembretes proativos.
 * @property {(id: string) => Promise<void>} onMarkAsRead - Callback para marcar uma notificação individual como lida.
 * @property {() => Promise<void>} onMarkAllAsRead - Callback para marcar todas as notificações pendentes como lidas.
 * @property {() => Promise<void>} onTriggerScan - Callback para disparar a varredura proativa de estagnação.
 * @property {boolean} [isScanning] - Indica se o robô proativo está realizando varredura.
 *
 * @a11y
 * - Implementa `role="dialog"`, `aria-modal="true"` e `aria-labelledby="notification-drawer-title"`.
 * - Prende o foco dentro do drawer enquanto aberto e escuta a tecla `Escape`.
 * - Cada notificação possui indicação textual e ícone para o status lida / não-lida (independência de cor).
 */
export interface NotificationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  notifications: NotificationItem[];
  onMarkAsRead: (id: string) => Promise<void>;
  onMarkAllAsRead: () => Promise<void>;
  onTriggerScan: () => Promise<void>;
  isScanning?: boolean;
}

export const NotificationDrawer: React.FC<NotificationDrawerProps> = ({
  isOpen,
  onClose,
  notifications,
  onMarkAsRead,
  onMarkAllAsRead,
  onTriggerScan,
  isScanning = false,
}) => {
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-900/50 backdrop-blur-xs transition-opacity"
      role="presentation"
    >
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="notification-drawer-title"
        className="w-full max-w-md bg-white dark:bg-slate-900 h-full shadow-2xl border-l border-slate-200 dark:border-slate-800 flex flex-col"
      >
        {/* Cabeçalho do Drawer */}
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-indigo-600 dark:text-indigo-400" aria-hidden="true" />
            <h2
              id="notification-drawer-title"
              className="text-base font-bold text-slate-900 dark:text-slate-100"
            >
              Notificações & Lembretes Proativos
            </h2>
            {unreadCount > 0 && (
              <span
                className="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300"
                aria-label={`${unreadCount} novas notificações não lidas`}
              >
                {unreadCount}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar painel de notificações"
            className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {/* Ações Globais: Varredura Proativa & Marcar Lidas */}
        <div className="p-3 bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            onClick={onTriggerScan}
            disabled={isScanning}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition disabled:opacity-50 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
            aria-label="Disparar varredura de candidaturas estagnadas sem contato"
          >
            <Radar className={`h-3.5 w-3.5 ${isScanning ? "animate-spin" : ""}`} aria-hidden="true" />
            <span>{isScanning ? "Varrendo Vagas..." : "Varredura de Follow-up"}</span>
          </button>

          {unreadCount > 0 && (
            <button
              type="button"
              onClick={onMarkAllAsRead}
              className="inline-flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline font-semibold"
              aria-label="Marcar todas as notificações como lidas"
            >
              <CheckCheck className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Marcar todas lidas</span>
            </button>
          )}
        </div>

        {/* Lista de Notificações */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3" role="list">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-slate-400 text-center text-xs">
              <Clock className="h-8 w-8 mb-2 stroke-1" aria-hidden="true" />
              <p>Nenhuma notificação registrada no momento.</p>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Clique em &quot;Varredura de Follow-up&quot; para checar vagas paradas há mais de 7 dias.
              </p>
            </div>
          ) : (
            notifications.map((item) => (
              <div
                key={item.id}
                role="listitem"
                className={`p-3.5 rounded-xl border transition-colors flex flex-col gap-2 ${
                  item.is_read
                    ? "bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 opacity-80"
                    : "bg-indigo-50/50 dark:bg-indigo-950/20 border-indigo-200 dark:border-indigo-800/60"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    {!item.is_read && (
                      <span
                        className="h-2 w-2 rounded-full bg-amber-500 shrink-0"
                        aria-label="Status: Nova notificação não lida"
                      />
                    )}
                    <h3 className="font-bold text-xs text-slate-900 dark:text-slate-100 line-clamp-1">
                      {item.title}
                    </h3>
                  </div>

                  <span
                    className="inline-flex items-center gap-1 text-[11px] text-slate-400"
                    title={`Agendado para ${new Date(item.scheduled_for).toLocaleString("pt-BR")}`}
                  >
                    <Calendar className="h-3 w-3" aria-hidden="true" />
                    {new Date(item.scheduled_for).toLocaleDateString("pt-BR", {
                      day: "2-digit",
                      month: "short",
                    })}
                  </span>
                </div>

                <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                  {item.message}
                </p>

                {!item.is_read && (
                  <div className="pt-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() => onMarkAsRead(item.id)}
                      className="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      Marcar como lida
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
