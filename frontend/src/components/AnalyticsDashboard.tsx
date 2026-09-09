"use client";

import React from "react";
import { ApplicationAnalyticsMetrics } from "@/types";
import {
  TrendingUp,
  Award,
  AlertTriangle,
  Target,
  BarChart3,
  Briefcase,
  RefreshCw,
} from "lucide-react";

/**
 * Propriedades do componente AnalyticsDashboard.
 *
 * @interface AnalyticsDashboardProps
 * @property {ApplicationAnalyticsMetrics} metrics - Objeto agregado contendo taxas de conversão e distribuição do pipeline ATS.
 * @property {() => void} [onRefresh] - Callback para recarregar as métricas via API.
 * @property {boolean} [isLoading] - Indica se as métricas estão em atualização.
 *
 * @a11y
 * - Todos os indicadores utilizam emparelhamento estrito de cor + ícone semântico + rótulo de texto.
 * - Utiliza atributos ARIA adequados (`role="region"`, `aria-label="Dashboard de Métricas Analíticas ATS"`).
 * - O botão de atualização possui rótulo descritivo e estado de desativação com anúncio para leitores de tela.
 */
export interface AnalyticsDashboardProps {
  metrics: ApplicationAnalyticsMetrics;
  onRefresh?: () => void;
  isLoading?: boolean;
}

export const AnalyticsDashboard: React.FC<AnalyticsDashboardProps> = ({
  metrics,
  onRefresh,
  isLoading = false,
}) => {
  const statusLabels: Record<string, string> = {
    applied: "Candidatura Enviada",
    screening: "Triagem Inicial",
    interview: "Em Entrevistas",
    offer: "Proposta Recebida",
    rejected: "Não Selecionado",
    withdrawn: "Desistência",
  };

  return (
    <div
      className="space-y-6"
      role="region"
      aria-label="Dashboard de Métricas Analíticas ATS"
    >
      {/* Cabeçalho da Seção de Métricas */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-indigo-600 dark:text-indigo-400" aria-hidden="true" />
            Performance do Pipeline de Carreira
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Métricas em tempo real sobre taxas de conversão e eficácia dos currículos direcionados.
          </p>
        </div>

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition disabled:opacity-50 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
            aria-label="Atualizar dados analíticos do dashboard"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            <span>{isLoading ? "Atualizando..." : "Recarregar Dados"}</span>
          </button>
        )}
      </div>

      {/* Grid de Cards com Indicadores Chave */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total de Candidaturas */}
        <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-xs flex items-center gap-4">
          <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400">
            <Briefcase className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Total de Vagas
            </span>
            <span className="text-2xl font-bold text-slate-900 dark:text-slate-100">
              {metrics.total_applications}
            </span>
            <span className="block text-[11px] text-slate-400 mt-0.5">
              Candidaturas cadastradas
            </span>
          </div>
        </div>

        {/* Taxa de Conversão para Entrevistas */}
        <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-xs flex items-center gap-4">
          <div className="p-3 rounded-lg bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400">
            <TrendingUp className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Convite p/ Entrevista
            </span>
            <span className="text-2xl font-bold text-purple-600 dark:text-purple-400">
              {metrics.interview_conversion_rate}%
            </span>
            <span className="block text-[11px] text-slate-400 mt-0.5">
              Taxa de avanço do pipeline
            </span>
          </div>
        </div>

        {/* Taxa de Ofertas Recebidas */}
        <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-xs flex items-center gap-4">
          <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400">
            <Award className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Taxa de Ofertas
            </span>
            <span className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
              {metrics.offer_conversion_rate}%
            </span>
            <span className="block text-[11px] text-slate-400 mt-0.5">
              Propostas de contratação
            </span>
          </div>
        </div>

        {/* Vagas Estagnadas (> 7 dias) */}
        <div className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-xs flex items-center gap-4">
          <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400">
            <AlertTriangle className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Ação de Follow-up
            </span>
            <span className="text-2xl font-bold text-amber-600 dark:text-amber-400">
              {metrics.stale_applications_count}
            </span>
            <span className="block text-[11px] text-slate-400 mt-0.5">
              Estagnadas há 7+ dias
            </span>
          </div>
        </div>
      </div>

      {/* Distribuição por Etapas do Pipeline */}
      <section
        aria-labelledby="status-dist-heading"
        className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-xs"
      >
        <div className="flex items-center justify-between mb-4">
          <h3
            id="status-dist-heading"
            className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2"
          >
            <Target className="h-4 w-4 text-indigo-600" aria-hidden="true" />
            Distribuição de Candidaturas por Status
          </h3>
          <span className="text-xs text-slate-500">
            Média de Aderência Geral:{" "}
            <strong className="text-slate-800 dark:text-slate-200">
              {metrics.average_match_score}%
            </strong>
          </span>
        </div>

        <div className="space-y-3" role="list" aria-label="Distribuição quantitativa por etapa">
          {Object.entries(metrics.status_distribution).map(([statusKey, count]) => {
            const percentage =
              metrics.total_applications > 0
                ? Math.round((count / metrics.total_applications) * 100)
                : 0;
            const label = statusLabels[statusKey] || statusKey;

            return (
              <div key={statusKey} role="listitem" className="space-y-1">
                <div className="flex justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <span>{label}</span>
                  <span>
                    {count} ({percentage}%)
                  </span>
                </div>
                <div
                  role="progressbar"
                  aria-valuenow={percentage}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${label}: ${count} candidaturas, ${percentage} por cento do total`}
                  className="w-full bg-slate-100 dark:bg-slate-700 h-2 rounded-full overflow-hidden"
                >
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
};
