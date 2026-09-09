"use client";

import React from "react";
import { MatchPreviewResponse, MatchAnalysisItem } from "@/types";
import {
  CheckCircle2,
  AlertCircle,
  XCircle,
  Sparkles,
  Tag,
  Target,
  ArrowRight,
} from "lucide-react";

/**
 * Propriedades do componente MatchPreviewCard.
 *
 * @interface MatchPreviewCardProps
 * @property {MatchPreviewResponse} analysis - Dados de análise semântica e aderência retornados pela IA.
 * @property {() => void} [onGenerateResume] - Callback para acionar a síntese completa do currículo personalizado.
 * @property {boolean} [isGenerating] - Indica se a síntese do currículo está em processamento.
 *
 * @a11y
 * - Atende ao critério WCAG 2.1 AA de Independência de Cor:
 *   - "matched": Ícone `CheckCircle2` + texto explícito "Atendido" + cor verde.
 *   - "partial": Ícone `AlertCircle` + texto explícito "Parcialmente Atendido" + cor âmbar.
 *   - "missing": Ícone `XCircle` + texto explícito "Não Identificado" + cor carmesim.
 * - Elementos interativos possuem estados de foco visíveis (`ring-indigo-500`).
 * - Fornece `aria-valuenow`, `aria-valuemin`, `aria-valuemax` na barra de progresso de aderência.
 */
export interface MatchPreviewCardProps {
  analysis: MatchPreviewResponse;
  onGenerateResume?: () => void;
  isGenerating?: boolean;
}

export const MatchPreviewCard: React.FC<MatchPreviewCardProps> = ({
  analysis,
  onGenerateResume,
  isGenerating = false,
}) => {
  const renderStatusBadge = (status: MatchAnalysisItem["status"]) => {
    switch (status) {
      case "matched":
        return (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700/60"
            aria-label="Status: Requisito Atendido"
          >
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
            <span>Atendido</span>
          </span>
        );
      case "partial":
        return (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700/60"
            aria-label="Status: Requisito Parcialmente Atendido"
          >
            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
            <span>Parcial</span>
          </span>
        );
      case "missing":
      default:
        return (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100 dark:bg-rose-950/60 text-rose-800 dark:text-rose-300 border border-rose-300 dark:border-rose-700/60"
            aria-label="Status: Requisito Não Identificado no Dossiê"
          >
            <XCircle className="h-3.5 w-3.5 shrink-0 text-rose-600 dark:text-rose-400" aria-hidden="true" />
            <span>Não Identificado</span>
          </span>
        );
    }
  };

  const getPercentageColor = (score: number): string => {
    if (score >= 80) return "text-emerald-600 dark:text-emerald-400";
    if (score >= 60) return "text-amber-600 dark:text-amber-400";
    return "text-rose-600 dark:text-rose-400";
  };

  return (
    <div
      className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm flex flex-col gap-6"
      role="region"
      aria-label="Análise de Aderência Semântica e ATS"
    >
      {/* Cabeçalho do Card: Score e Ação */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-100 dark:border-slate-700/60">
        <div>
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-indigo-600 dark:text-indigo-400" aria-hidden="true" />
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              Aderência Semântica com a Vaga
            </h3>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Cálculo ponderado entre competências mandatórias (70%) e desejáveis (30%).
          </p>
        </div>

        <div className="flex items-center gap-4 self-stretch sm:self-auto justify-between">
          <div className="text-right">
            <span
              className={`text-3xl font-extrabold ${getPercentageColor(
                analysis.match_percentage
              )}`}
            >
              {analysis.match_percentage}%
            </span>
            <span className="block text-[11px] text-slate-500 font-medium">
              Taxa de Compatibilidade
            </span>
          </div>

          {onGenerateResume && (
            <button
              type="button"
              onClick={onGenerateResume}
              disabled={isGenerating}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold shadow-xs hover:shadow transition disabled:opacity-50 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
            >
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              <span>{isGenerating ? "Gerando Currículo..." : "Gerar Currículo Otimizado"}</span>
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {/* Barra de Progresso Acessível */}
      <div
        role="progressbar"
        aria-valuenow={analysis.match_percentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Compatibilidade com a vaga: ${analysis.match_percentage} por cento`}
        className="w-full bg-slate-100 dark:bg-slate-700 h-2.5 rounded-full overflow-hidden"
      >
        <div
          className={`h-full transition-all duration-500 rounded-full ${
            analysis.match_percentage >= 80
              ? "bg-emerald-500"
              : analysis.match_percentage >= 60
              ? "bg-amber-500"
              : "bg-rose-500"
          }`}
          style={{ width: `${analysis.match_percentage}%` }}
        />
      </div>

      {/* Seção 1: Requisitos Obrigatórios */}
      <section aria-labelledby="mandatory-heading" className="space-y-3">
        <h4
          id="mandatory-heading"
          className="text-sm font-bold text-slate-800 dark:text-slate-200 flex items-center justify-between"
        >
          <span>Requisitos Mandatórios ({analysis.mandatory_matches.length})</span>
          <span className="text-xs text-slate-500 font-normal">Peso: 70%</span>
        </h4>
        <ul className="space-y-2.5" role="list">
          {analysis.mandatory_matches.map((item, idx) => (
            <li
              key={idx}
              className="p-3 rounded-lg border border-slate-200 dark:border-slate-700/80 bg-slate-50/50 dark:bg-slate-900/30 flex flex-col gap-1.5"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                  {item.requirement}
                </span>
                {renderStatusBadge(item.status)}
              </div>
              {item.evidence && (
                <p className="text-xs text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800/80 p-2 rounded border border-slate-100 dark:border-slate-700/40">
                  <span className="font-semibold text-slate-700 dark:text-slate-300">
                    Evidência no dossiê:{" "}
                  </span>
                  {item.evidence}
                </p>
              )}
            </li>
          ))}
        </ul>
      </section>

      {/* Seção 2: Requisitos Desejáveis */}
      {analysis.desirable_matches.length > 0 && (
        <section aria-labelledby="desirable-heading" className="space-y-3">
          <h4
            id="desirable-heading"
            className="text-sm font-bold text-slate-800 dark:text-slate-200 flex items-center justify-between"
          >
            <span>Requisitos Desejáveis ({analysis.desirable_matches.length})</span>
            <span className="text-xs text-slate-500 font-normal">Peso: 30%</span>
          </h4>
          <ul className="space-y-2.5" role="list">
            {analysis.desirable_matches.map((item, idx) => (
              <li
                key={idx}
                className="p-3 rounded-lg border border-slate-200 dark:border-slate-700/80 bg-slate-50/50 dark:bg-slate-900/30 flex flex-col gap-1.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {item.requirement}
                  </span>
                  {renderStatusBadge(item.status)}
                </div>
                {item.evidence && (
                  <p className="text-xs text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800/80 p-2 rounded border border-slate-100 dark:border-slate-700/40">
                    <span className="font-semibold text-slate-700 dark:text-slate-300">
                      Evidência no dossiê:{" "}
                    </span>
                    {item.evidence}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Seção 3: Palavras-chave Recomendadas para ATS */}
      {analysis.suggested_keywords && analysis.suggested_keywords.length > 0 && (
        <section aria-labelledby="keywords-heading" className="space-y-2 pt-2 border-t border-slate-100 dark:border-slate-700/60">
          <h4
            id="keywords-heading"
            className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5"
          >
            <Tag className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Palavras-chave recomendadas para ATS</span>
          </h4>
          <div className="flex flex-wrap gap-1.5" role="list" aria-label="Lista de palavras-chave ATS recomendadas">
            {analysis.suggested_keywords.map((kw, i) => (
              <span
                key={i}
                role="listitem"
                className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800"
              >
                {kw}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};
