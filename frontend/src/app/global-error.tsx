"use client";

/**
 * Root Global Error Boundary (Next.js 15 App Router).
 *
 * Captura falhas catastróficas que ocorrem dentro do RootLayout (app/layout.tsx).
 * Como substitui o layout raiz, é obrigatório definir suas próprias tags <html> e <body>.
 */

import React, { useEffect, useState } from "react";
import { AlertOctagon, Copy, Check, RotateCcw } from "lucide-react";
import { frontendLogger, getCorrelationId } from "@/lib/telemetry";

export interface GlobalErrorProps {
  error: Error & { digest?: string; correlationId?: string | null };
  reset: () => void;
}

export default function GlobalRootError({ error, reset }: GlobalErrorProps) {
  const [copied, setCopied] = useState(false);

  const supportId =
    error.correlationId || error.digest || getCorrelationId();

  useEffect(() => {
    frontendLogger.error("client_global_root_error_triggered", {
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
      // Ignora falha de clipboard
    }
  };

  return (
    <html lang="pt-BR">
      <body className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4 sm:p-6 font-sans">
        <main
          role="alert"
          aria-labelledby="global-error-title"
          className="max-w-lg w-full bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 sm:p-8 text-center"
        >
          <div className="w-14 h-14 mx-auto mb-5 rounded-full bg-rose-950/70 border border-rose-800/50 flex items-center justify-center text-rose-400">
            <AlertOctagon className="w-8 h-8" aria-hidden="true" />
          </div>

          <h1
            id="global-error-title"
            className="text-2xl font-bold tracking-tight text-white mb-2"
          >
            Erro Crítico no Sistema
          </h1>
          <p className="text-sm text-slate-400 mb-6">
            Ocorreu uma interrupção inesperada no carregamento base da plataforma.
            Por favor, utilize o ID de suporte abaixo ao contatar nosso time de SRE.
          </p>

          <div className="mb-6 p-4 bg-slate-950 border border-slate-800 rounded-xl text-left">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                ID de Correlação / Suporte
              </span>
              <button
                type="button"
                onClick={handleCopyId}
                aria-label="Copiar ID de correlação"
                className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded px-1.5 py-0.5"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
                    <span className="text-emerald-400 font-semibold">Copiado!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" aria-hidden="true" />
                    <span>Copiar</span>
                  </>
                )}
              </button>
            </div>
            <code
              data-testid="global-correlation-id"
              className="block text-xs font-mono text-slate-300 break-all select-all"
            >
              {supportId}
            </code>
            <div aria-live="polite" className="sr-only">
              {copied ? "ID de suporte copiado." : ""}
            </div>
          </div>

          <button
            type="button"
            onClick={() => reset()}
            className="w-full inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-medium text-sm transition shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <RotateCcw className="w-4 h-4" aria-hidden="true" />
            Recarregar Aplicação
          </button>
        </main>
      </body>
    </html>
  );
}
