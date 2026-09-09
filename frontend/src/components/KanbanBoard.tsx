"use client";

import React from "react";
import {
  ApplicationItem,
  ApplicationStatus,
} from "@/types";
import {
  AlertTriangle,
  Building2,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Briefcase,
  MapPin,
} from "lucide-react";

/**
 * Propriedades do componente KanbanBoard.
 *
 * @interface KanbanBoardProps
 * @property {ApplicationItem[]} applications - Lista de candidaturas a serem exibidas nas colunas.
 * @property {(id: string, newStatus: ApplicationStatus) => Promise<void>} onStatusChange - Callback invocado ao alterar o status de uma vaga.
 * @property {(app: ApplicationItem) => void} [onSelectApplication] - Callback opcional ao clicar/ativar uma vaga para visualização detalhada.
 * @property {boolean} [isLoading] - Indica se o quadro está em estado de carregamento assíncrono.
 *
 * @a11y
 * - Usa estrutura semântica de seções e listas (`<section>`, `<ol>`, `<li>`).
 * - Fornece botões de movimentação entre etapas com `aria-label` descritivos para leitores de tela.
 * - Sinaliza candidaturas estagnadas através de ícone semântico (`AlertTriangle`) e texto explícito, sem depender exclusivamente de cor.
 * - Suporta navegação completa via teclado (`Tab`, `Enter`, `Space`).
 */
export interface KanbanBoardProps {
  applications: ApplicationItem[];
  onStatusChange: (id: string, newStatus: ApplicationStatus) => Promise<void>;
  onSelectApplication?: (app: ApplicationItem) => void;
  isLoading?: boolean;
}

interface ColumnConfig {
  id: ApplicationStatus;
  title: string;
  badgeColor: string;
  borderColor: string;
}

const COLUMNS: ColumnConfig[] = [
  {
    id: "applied",
    title: "Candidatura Enviada",
    badgeColor: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
    borderColor: "border-t-blue-500",
  },
  {
    id: "screening",
    title: "Triagem / RH",
    badgeColor: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300",
    borderColor: "border-t-purple-500",
  },
  {
    id: "interview",
    title: "Em Entrevistas",
    badgeColor: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
    borderColor: "border-t-amber-500",
  },
  {
    id: "offer",
    title: "Proposta Recebida",
    badgeColor: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
    borderColor: "border-t-emerald-500",
  },
  {
    id: "rejected",
    title: "Não Selecionado",
    badgeColor: "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300",
    borderColor: "border-t-rose-500",
  },
];

export const KanbanBoard: React.FC<KanbanBoardProps> = ({
  applications,
  onStatusChange,
  onSelectApplication,
  isLoading = false,
}) => {
  const getAdjacentStatus = (
    currentStatus: ApplicationStatus,
    direction: "prev" | "next"
  ): ApplicationStatus | null => {
    const order: ApplicationStatus[] = [
      "applied",
      "screening",
      "interview",
      "offer",
    ];
    const currentIndex = order.indexOf(currentStatus);
    if (currentIndex === -1) return null;

    if (direction === "prev" && currentIndex > 0) {
      return order[currentIndex - 1];
    }
    if (direction === "next" && currentIndex < order.length - 1) {
      return order[currentIndex + 1];
    }
    return null;
  };

  return (
    <div
      className="w-full overflow-x-auto pb-4"
      role="region"
      aria-label="Quadro Kanban de Candidaturas ATS"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4 min-w-[1050px]">
        {COLUMNS.map((col) => {
          const colApps = applications.filter((app) => app.status === col.id);

          return (
            <section
              key={col.id}
              aria-labelledby={`col-heading-${col.id}`}
              className={`flex flex-col bg-slate-50 dark:bg-slate-900/50 rounded-xl p-3 border border-slate-200 dark:border-slate-800 border-t-4 ${col.borderColor} shadow-xs min-h-[420px]`}
            >
              {/* Header da Coluna */}
              <div className="flex items-center justify-between mb-3 px-1">
                <h3
                  id={`col-heading-${col.id}`}
                  className="font-semibold text-sm text-slate-800 dark:text-slate-200 flex items-center gap-2"
                >
                  {col.title}
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${col.badgeColor}`}
                    aria-label={`${colApps.length} candidaturas`}
                  >
                    {colApps.length}
                  </span>
                </h3>
              </div>

              {/* Lista de Cards da Coluna */}
              <ol
                className="flex flex-col gap-3 flex-1 overflow-y-auto"
                aria-label={`Vagas em ${col.title}`}
              >
                {colApps.length === 0 ? (
                  <li className="flex-1 flex items-center justify-center p-4 border border-dashed border-slate-200 dark:border-slate-800 rounded-lg text-xs text-slate-400 text-center">
                    Nenhuma vaga nesta etapa
                  </li>
                ) : (
                  colApps.map((app) => {
                    const prevStatus = getAdjacentStatus(app.status, "prev");
                    const nextStatus = getAdjacentStatus(app.status, "next");

                    return (
                      <li
                        key={app.id}
                        onClick={() => onSelectApplication?.(app)}
                        className={`group bg-white dark:bg-slate-800 rounded-lg p-3.5 border border-slate-200 dark:border-slate-700/80 shadow-xs hover:shadow-md transition-shadow flex flex-col gap-2.5 focus-within:ring-2 focus-within:ring-indigo-500 ${
                          onSelectApplication ? "cursor-pointer" : ""
                        }`}
                      >
                        {/* Alerta de Follow-up (se estagnada há > 7 dias) */}
                        {app.needs_follow_up && (
                          <div
                            role="alert"
                            className="flex items-center gap-1.5 px-2 py-1 rounded bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-700/60 text-amber-800 dark:text-amber-200 text-xs font-semibold"
                          >
                            <AlertTriangle
                              className="h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400"
                              aria-hidden="true"
                            />
                            <span>Ação necessária: sem contato há 7+ dias</span>
                          </div>
                        )}

                        {/* Informações da Vaga */}
                        <div>
                          <h4 className="font-semibold text-sm text-slate-900 dark:text-slate-100 line-clamp-1">
                            {app.job_title}
                          </h4>
                          <div className="flex items-center gap-1 text-xs text-slate-600 dark:text-slate-400 mt-0.5">
                            <Building2 className="h-3 w-3 shrink-0" aria-hidden="true" />
                            <span className="truncate">{app.company_name}</span>
                          </div>
                        </div>

                        {/* Metadados: Modelo de trabalho e Localização */}
                        <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 font-medium capitalize">
                            <Briefcase className="h-2.5 w-2.5" aria-hidden="true" />
                            {app.work_model}
                          </span>
                          {app.location && (
                            <span className="inline-flex items-center gap-1 truncate max-w-[120px]">
                              <MapPin className="h-2.5 w-2.5" aria-hidden="true" />
                              {app.location}
                            </span>
                          )}
                        </div>

                        {/* Rodapé do Card: Data e Ações de Movimentação */}
                        <div className="pt-2 border-t border-slate-100 dark:border-slate-700/50 flex items-center justify-between text-xs">
                          <span
                            className="flex items-center gap-1 text-slate-400 text-[11px]"
                            title={`Candidatura registrada em ${new Date(
                              app.applied_at
                            ).toLocaleDateString("pt-BR")}`}
                          >
                            <Calendar className="h-3 w-3" aria-hidden="true" />
                            {new Date(app.applied_at).toLocaleDateString("pt-BR", {
                              month: "short",
                              year: "numeric",
                            })}
                          </span>

                          {/* Controles acessíveis de avanço/recuo de etapa */}
                          <div className="flex items-center gap-1">
                            {prevStatus && (
                              <button
                                type="button"
                                disabled={isLoading}
                                onClick={() => onStatusChange(app.id, prevStatus)}
                                aria-label={`Mover ${app.job_title} na ${app.company_name} para etapa anterior`}
                                className="p-1 rounded text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                              >
                                <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
                              </button>
                            )}
                            {nextStatus && (
                              <button
                                type="button"
                                disabled={isLoading}
                                onClick={() => onStatusChange(app.id, nextStatus)}
                                aria-label={`Avançar ${app.job_title} na ${app.company_name} para próxima etapa`}
                                className="p-1 rounded text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                              >
                                <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                              </button>
                            )}
                          </div>
                        </div>
                      </li>
                    );
                  })
                )}
              </ol>
            </section>
          );
        })}
      </div>
    </div>
  );
};
