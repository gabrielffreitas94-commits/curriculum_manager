"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  MatchPreviewResponse,
  ResumeGenerateResponse,
} from "@/types";
import { ApiClient } from "@/lib/api";
import {
  X,
  Sparkles,
  Search,
  Building2,
  Briefcase,
  Globe2,
  Loader2,
  AlertCircle,
} from "lucide-react";

/**
 * Propriedades do componente JobAnalyzerModal.
 *
 * @interface JobAnalyzerModalProps
 * @property {boolean} isOpen - Controla se o modal acessível está visível.
 * @property {() => void} onClose - Callback acionado para fechar o modal.
 * @property {(data: MatchPreviewResponse) => void} [onAnalysisComplete] - Callback ao concluir o cálculo semântico de aderência.
 * @property {(data: ResumeGenerateResponse) => void} [onResumeGenerated] - Callback ao gerar um novo currículo via IA.
 *
 * @a11y
 * - Implementa `role="dialog"`, `aria-modal="true"` e `aria-labelledby="job-modal-title"`.
 * - Prende o foco (`focus trap`) no interior do modal ao navegar com `Tab` ou `Shift+Tab`.
 * - Fecha com a tecla `Escape` e devolve o foco para o elemento chamador.
 * - Estados de carregamento e mensagens de erro são anunciadas via `aria-live="polite"` e `role="alert"`.
 */
export interface JobAnalyzerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAnalysisComplete?: (data: MatchPreviewResponse) => void;
  onResumeGenerated?: (data: ResumeGenerateResponse) => void;
}

export const JobAnalyzerModal: React.FC<JobAnalyzerModalProps> = ({
  isOpen,
  onClose,
  onAnalysisComplete,
  onResumeGenerated,
}) => {
  const [companyName, setCompanyName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [language, setLanguage] = useState("pt-BR");
  const [workModel, setWorkModel] = useState<"remote" | "hybrid" | "on-site">("remote");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingAction, setLoadingAction] = useState<"match" | "generate" | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const modalRef = useRef<HTMLDivElement>(null);
  const firstInputRef = useRef<HTMLInputElement>(null);

  // Focus trap & Escape key listener
  useEffect(() => {
    if (!isOpen) return;

    // Foca o primeiro input acessível
    setTimeout(() => {
      firstInputRef.current?.focus();
    }, 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }

      if (e.key === "Tab" && modalRef.current) {
        const focusableElements = modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            lastElement.focus();
            e.preventDefault();
          }
        } else {
          if (document.activeElement === lastElement) {
            firstElement.focus();
            e.preventDefault();
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleMatchPreview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!jobDescription.trim()) {
      setErrorMessage("Por favor, informe a descrição completa da vaga.");
      return;
    }

    try {
      setIsLoading(true);
      setLoadingAction("match");
      setErrorMessage(null);

      const result = await ApiClient.previewMatch(jobDescription);
      onAnalysisComplete?.(result);
      onClose();
    } catch (err: unknown) {
      const error = err as Error;
      setErrorMessage(error.message || "Erro ao analisar vaga.");
    } finally {
      setIsLoading(false);
      setLoadingAction(null);
    }
  };

  const handleGenerateResume = async () => {
    if (!jobDescription.trim()) {
      setErrorMessage("Por favor, informe a descrição completa da vaga.");
      return;
    }

    try {
      setIsLoading(true);
      setLoadingAction("generate");
      setErrorMessage(null);

      const result = await ApiClient.generateResume({
        job_description: jobDescription,
        company_name: companyName.trim() || undefined,
        job_title: jobTitle.trim() || undefined,
        language,
        create_application: true,
      });

      onResumeGenerated?.(result);
      onClose();
    } catch (err: unknown) {
      const error = err as Error;
      setErrorMessage(error.message || "Erro ao sintetizar currículo via IA.");
    } finally {
      setIsLoading(false);
      setLoadingAction(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs"
      role="presentation"
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="job-modal-title"
        className="relative w-full max-w-2xl bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 p-6 flex flex-col gap-5 max-h-[90vh] overflow-y-auto"
      >
        {/* Cabeçalho do Modal */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
              <Sparkles className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <h2
                id="job-modal-title"
                className="text-lg font-bold text-slate-900 dark:text-slate-100"
              >
                Analisar Nova Vaga & Gerar Currículo
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Cole os dados da oportunidade para validação anti-alucinação e otimização ATS.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar janela modal de análise de vaga"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {/* Mensagem de Erro Acessível */}
        {errorMessage && (
          <div
            role="alert"
            className="flex items-center gap-2 p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-300 dark:border-rose-800 text-rose-800 dark:text-rose-200 text-xs"
          >
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" aria-hidden="true" />
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleMatchPreview} className="flex flex-col gap-4">
          {/* Linha 1: Empresa e Cargo */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="modal-company"
                className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1"
              >
                Nome da Empresa
              </label>
              <div className="relative">
                <Building2
                  className="absolute left-3 top-2.5 h-4 w-4 text-slate-400"
                  aria-hidden="true"
                />
                <input
                  ref={firstInputRef}
                  id="modal-company"
                  type="text"
                  placeholder="Ex: Google, Nubank..."
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="modal-job-title"
                className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1"
              >
                Título do Cargo
              </label>
              <div className="relative">
                <Briefcase
                  className="absolute left-3 top-2.5 h-4 w-4 text-slate-400"
                  aria-hidden="true"
                />
                <input
                  id="modal-job-title"
                  type="text"
                  placeholder="Ex: Desenvolvedor Senior..."
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>
          </div>

          {/* Linha 2: Idioma do Currículo e Modelo de Trabalho */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="modal-language"
                className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1"
              >
                Idioma do Currículo
              </label>
              <div className="relative">
                <Globe2
                  className="absolute left-3 top-2.5 h-4 w-4 text-slate-400"
                  aria-hidden="true"
                />
                <select
                  id="modal-language"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="pt-BR">Português (Brasil) - pt-BR</option>
                  <option value="pt-PT">Português (Portugal) - pt-PT</option>
                  <option value="en-US">English (US) - en-US</option>
                  <option value="en-GB">English (UK) - en-GB</option>
                  <option value="es-ES">Español (España) - es-ES</option>
                </select>
              </div>
            </div>

            <div>
              <label
                htmlFor="modal-work-model"
                className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1"
              >
                Modelo de Trabalho
              </label>
              <select
                id="modal-work-model"
                value={workModel}
                onChange={(e) =>
                  setWorkModel(e.target.value as "remote" | "hybrid" | "on-site")
                }
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
              >
                <option value="remote">Remoto</option>
                <option value="hybrid">Híbrido</option>
                <option value="on-site">Presencial</option>
              </select>
            </div>
          </div>

          {/* Textarea da Descrição da Vaga */}
          <div>
            <label
              htmlFor="modal-description"
              className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1"
            >
              Descrição Completa da Vaga (JD) *
            </label>
            <textarea
              id="modal-description"
              required
              rows={6}
              placeholder="Cole aqui os requisitos, responsabilidades e qualificações da vaga..."
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              className="w-full p-3 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* Rodapé com Ações */}
          <div
            className="flex flex-col-reverse sm:flex-row items-center justify-end gap-3 pt-3 border-t border-slate-100 dark:border-slate-800"
            aria-live="polite"
          >
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="w-full sm:w-auto px-4 py-2 text-sm font-medium rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            >
              Cancelar
            </button>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-300 dark:border-slate-700 hover:bg-slate-200 transition disabled:opacity-50"
            >
              {isLoading && loadingAction === "match" ? (
                <Loader2 className="h-4 w-4 animate-spin text-indigo-600" aria-hidden="true" />
              ) : (
                <Search className="h-4 w-4" aria-hidden="true" />
              )}
              <span>Ver Aderência Rápida</span>
            </button>

            <button
              type="button"
              onClick={handleGenerateResume}
              disabled={isLoading}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2 text-sm font-semibold rounded-lg bg-indigo-600 text-white shadow hover:bg-indigo-700 transition disabled:opacity-50"
            >
              {isLoading && loadingAction === "generate" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Sparkles className="h-4 w-4" aria-hidden="true" />
              )}
              <span>Sintetizar com IA & Salvar</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
