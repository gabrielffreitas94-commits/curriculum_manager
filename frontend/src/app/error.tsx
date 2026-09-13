"use client";

/**
 * Error Boundary de Rota (Next.js 15 App Router).
 *
 * Captura exceções em tempo de execução na aplicação, exibindo uma interface
 * acessível (WCAG 2.1 AA), amigável ao usuário e com rastreabilidade SRE
 * através da exibição do Correlation ID / ID de Suporte.
 */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Copy, Check, RotateCcw, Home } from "lucide-react";
import { frontendLogger, getCorrelationId } from "@/lib/telemetry";

export interface ErrorProps {
  error: Error & { digest?: string; correlationId?: string | null };
  reset: () => void;
}

export default function GlobalRouteError({ error, reset }: ErrorProps) {
  const [copied, setCopied] = useState(false);

  // Extrai o ID de suporte prioritariamente do erro capturado ou do contexto ativo
  const supportId =
    error.correlationId || error.digest || getCorrelationId();

  useEffect(() => {
    frontendLogger.error("client_route_error_boundary_triggered", {
      error_message: error.message,
      error_name: error.name,
      digest: error.digest,
      correlation_id: supportId,
      stack: error.stack,
    });
  }, [error, supportId]);

  const handleCopyId = async () => {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(supportId);
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      }
    } catch {
      // Fallback silencioso se clipboard API não estiver disponível
    }
  };

  return (
    <main
      role="alert"
      aria-labelledby="error-heading"
      className="min-h-[70vh] flex items-center justify-center p-4 sm:p-6 lg:p-8"
    >
      <div className="max-w-xl w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl p-6 sm:p-8 text-center">
        {/* Ícone Semântico */}
        <div className="w-14 h-14 mx-auto mb-5 rounded-full bg-amber-100 dark:bg-amber-950/50 flex items-center justify-center text-amber-600 dark:text-amber-400">
          <AlertTriangle className="w-8 h-8" aria-hidden="true" />
        </div>

        {/* Título e Mensagem Acessível */}
        <h1
          id="error-heading"
          className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 mb-3"
        >
          Ops! Algo inesperado aconteceu
        </h1>
        <p className="text-sm sm:text-base text-slate-600 dark:text-slate-400 mb-6">
          Identificamos uma instabilidade temporária ao carregar esta página.
          Nossa equipe de engenharia já recebeu os logs de telemetria desta ocorrência.
        </p>

        {/* Painel de ID de Suporte & Rastreabilidade SRE */}
        <div className="mb-8 p-4 bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 rounded-xl text-left">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              ID de Suporte / Rastreamento
            </span>
            <button
              type="button"
              onClick={handleCopyId}
              aria-label="Copiar ID de suporte para a área de transferência"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded px-1.5 py-0.5"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                  <span className="text-emerald-600 dark:text-emerald-400 font-semibold">Copiado!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Copiar ID</span>
                </>
              )}
            </button>
          </div>
          <code
            data-testid="support-correlation-id"
            className="block text-xs sm:text-sm font-mono text-slate-800 dark:text-slate-200 break-all select-all"
          >
            {supportId}
          </code>
          <div aria-live="polite" className="sr-only">
            {copied ? "ID de suporte copiado com sucesso para a área de transferência." : ""}
          </div>
        </div>

        {/* Ações Rápidas */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => reset()}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-medium text-sm transition shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
          >
            <RotateCcw className="w-4 h-4" aria-hidden="true" />
            Tentar novamente
          </button>
          <Link
            href="/"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 active:bg-slate-300 text-slate-700 dark:text-slate-200 font-medium text-sm transition focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <Home className="w-4 h-4" aria-hidden="true" />
            Voltar ao Início
          </Link>
        </div>
      </div>
    </main>
  );
}
