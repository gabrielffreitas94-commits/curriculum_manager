"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Header } from "@/components/Header";
import { KanbanBoard } from "@/components/KanbanBoard";
import { MatchPreviewCard } from "@/components/MatchPreviewCard";
import { JobAnalyzerModal } from "@/components/JobAnalyzerModal";
import { ResumeViewer } from "@/components/ResumeViewer";
import { AnalyticsDashboard } from "@/components/AnalyticsDashboard";
import { NotificationDrawer } from "@/components/NotificationDrawer";
import {
  ApplicationItem,
  ApplicationStatus,
  ApplicationAnalyticsMetrics,
  MatchPreviewResponse,
  ResumeGenerateResponse,
  NotificationItem,
} from "@/types";
import { ApiClient } from "@/lib/api";
import {
  Plus,
  RefreshCw,
  CheckCircle2,
  FileCheck,
  Sparkles,
} from "lucide-react";

// Mock inicial para visualização e testes
const INITIAL_APPLICATIONS: ApplicationItem[] = [
  {
    id: "app-1",
    company_name: "Nubank",
    job_title: "Tech Lead Python / FastAPI",
    status: "interview",
    work_model: "remote",
    applied_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    last_activity_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    needs_follow_up: false,
    location: "São Paulo, SP",
  },
  {
    id: "app-2",
    company_name: "Google Cloud",
    job_title: "Solutions Architect GenAI",
    status: "screening",
    work_model: "hybrid",
    applied_at: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
    last_activity_at: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
    needs_follow_up: true,
    location: "São Paulo, SP",
  },
  {
    id: "app-3",
    company_name: "Stripe",
    job_title: "Senior Backend Engineer",
    status: "applied",
    work_model: "remote",
    applied_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    last_activity_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    needs_follow_up: false,
  },
];

const INITIAL_METRICS: ApplicationAnalyticsMetrics = {
  total_applications: 3,
  status_distribution: {
    applied: 1,
    screening: 1,
    interview: 1,
    offer: 0,
    rejected: 0,
  },
  stale_applications_count: 1,
  interview_conversion_rate: 33.3,
  offer_conversion_rate: 0.0,
  average_match_score: 87.5,
};

const DEFAULT_MATCH: MatchPreviewResponse = {
  match_percentage: 88,
  mandatory_matches: [
    {
      requirement: "5+ anos de experiência com Python e desenvolvimento de APIs modernas",
      status: "matched",
      evidence: "8 anos de desenvolvimento comprovados com FastAPI e Django em microsserviços.",
      similarity_score: 0.94,
    },
    {
      requirement: "Domínio de bancos relacionais PostgreSQL e modelagem de dados",
      status: "matched",
      evidence: "Experiência sólida com PostgreSQL e SQLAlchemy assíncrono.",
      similarity_score: 0.91,
    },
    {
      requirement: "Prática com TDD e cobertura de testes automatizados",
      status: "partial",
      evidence: "Testes unitários mencionados, mas sem detalhamento de pirâmide de testes no dossiê.",
      similarity_score: 0.68,
    },
  ],
  desirable_matches: [
    {
      requirement: "Experiência com LLMs e Google Gemini API",
      status: "matched",
      evidence: "Implementação de Structured Outputs e integração GenAI no histórico recente.",
      similarity_score: 0.95,
    },
    {
      requirement: "Vivência com arquitetura hexagonal e Clean Code",
      status: "matched",
      evidence: "Design de portas e adaptadores em microsserviços críticos.",
      similarity_score: 0.89,
    },
  ],
  missing_mandatory: [],
  missing_desirable: [],
  suggested_keywords: [
    "FastAPI",
    "Python 3.13",
    "Hexagonal Architecture",
    "PostgreSQL",
    "TDD",
    "Google GenAI",
    "Docker",
  ],
};

const DEFAULT_RESUME: ResumeGenerateResponse = {
  resume_id: "res-sample-1",
  application_id: "app-1",
  version_number: 1,
  match_percentage: 92,
  match_analysis: {},
  structured_content: {
    header: {
      full_name: "Alexandre Silva",
      target_title: "Tech Lead & Senior Software Engineer",
      email: "alexandre.silva@exemplo.com",
      phone: "+55 (11) 98765-4321",
      location: "São Paulo, SP - Brasil",
      links: {
        linkedin: "https://linkedin.com/in/exemplo",
        github: "https://github.com/exemplo",
      },
    },
    professional_summary:
      "Engenheiro de Software com mais de 8 anos de experiência em arquitetura de microsserviços de alta escala, Python assíncrono (FastAPI) e soluções orientadas a inteligência artificial generativa.",
    selected_experiences: [
      {
        company_name: "Tech Solutions Corp",
        position_title: "Tech Lead / Senior Backend Engineer",
        start_date: "03/2021",
        end_date: null,
        is_current: true,
        bullet_points: [
          "Liderou equipe técnica de 8 desenvolvedores na arquitetura de microsserviços FastAPI reduzindo latência em 45%.",
          "Conduziu pipeline de integração com Google Gemini e modelos LLM com Structured Outputs.",
        ],
        tech_stack: ["Python", "FastAPI", "PostgreSQL", "Docker", "GCP"],
      },
      {
        company_name: "Inovação Digital Ltda",
        position_title: "Software Engineer",
        start_date: "01/2018",
        end_date: "02/2021",
        is_current: false,
        bullet_points: [
          "Desenvolveu APIs RESTful e workers assíncronos para processamento de alto volume financeiro.",
        ],
        tech_stack: ["Python", "Django", "Redis", "AWS"],
      },
    ],
    skills_highlighted: [
      "Python",
      "FastAPI",
      "SQLAlchemy",
      "Arquitetura Hexagonal",
      "Google GenAI SDK",
      "PostgreSQL",
      "Docker",
    ],
    education: [
      {
        degree: "Bacharelado em Ciência da Computação",
        institution: "Universidade de São Paulo (USP)",
        end_date: "12/2017",
      },
    ],
    certifications: [
      {
        name: "Google Cloud Certified Professional Cloud Architect",
        issuer: "Google Cloud",
      },
    ],
    languages: [
      {
        language: "Português",
        proficiency: "Nativo",
      },
      {
        language: "Inglês",
        proficiency: "Avançado / Fluente",
      },
    ],
  },
};

export default function Home() {
  const [activeTab, setActiveTab] = useState<"kanban" | "match" | "analytics" | "resume">("kanban");
  const [applications, setApplications] = useState<ApplicationItem[]>(INITIAL_APPLICATIONS);
  const [metrics, setMetrics] = useState<ApplicationAnalyticsMetrics>(INITIAL_METRICS);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // Estados de modais e drawers
  const [isAnalyzerOpen, setIsAnalyzerOpen] = useState(false);
  const [isNotificationOpen, setIsNotificationOpen] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Resultados de IA
  const [activeAnalysis, setActiveAnalysis] = useState<MatchPreviewResponse | null>(DEFAULT_MATCH);
  const [activeResume, setActiveResume] = useState<ResumeGenerateResponse | null>(DEFAULT_RESUME);

  // Feedback de ações
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  // Carregamento de dados da API
  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      const [appsData, metricsData, notifsData, unread] = await Promise.allSettled([
        ApiClient.getApplications(),
        ApiClient.getAnalyticsMetrics(),
        ApiClient.getNotifications(),
        ApiClient.getUnreadCount(),
      ]);

      if (appsData.status === "fulfilled" && appsData.value.length > 0) {
        setApplications(appsData.value);
      }
      if (metricsData.status === "fulfilled") {
        setMetrics(metricsData.value);
      }
      if (notifsData.status === "fulfilled") {
        setNotifications(notifsData.value);
      }
      if (unread.status === "fulfilled") {
        setUnreadCount(unread.value);
      }
    } catch {
      // Falha silenciosa em dev se o backend estiver offline
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Alteração de status no Kanban
  const handleStatusChange = async (id: string, newStatus: ApplicationStatus) => {
    setApplications((prev) =>
      prev.map((app) =>
        app.id === id ? { ...app, status: newStatus, needs_follow_up: false } : app
      )
    );

    try {
      await ApiClient.updateApplicationStatus(id, newStatus);
      showToast("Status da vaga atualizado com sucesso!");
      loadData();
    } catch {
      // Mantém o estado otimista em dev
    }
  };

  // Varredura de follow-ups proativos
  const handleTriggerScan = async () => {
    try {
      setIsScanning(true);
      const count = await ApiClient.triggerFollowUpScan();
      showToast(`Varredura concluída! ${count} novo(s) lembrete(s) gerado(s).`);
      await loadData();
    } catch {
      showToast("Varredura simulada com sucesso.");
    } finally {
      setIsScanning(false);
    }
  };

  // Marcar todas notificações como lidas
  const handleMarkAllRead = async () => {
    try {
      await ApiClient.markAllAsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
      showToast("Todas as notificações foram marcadas como lidas.");
    } catch {
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    }
  };

  // Marcar uma notificação como lida
  const handleMarkOneRead = async (id: string) => {
    try {
      await ApiClient.markAsRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
    }
  };

  return (
    <div className="flex flex-col min-h-screen">
      {/* Header Acessível */}
      <Header
        activeTab={activeTab}
        onTabChange={setActiveTab}
        unreadCount={unreadCount}
        onOpenNotifications={() => setIsNotificationOpen(true)}
      />

      {/* Notificação Flutuante (Toast Acessível) */}
      {toastMessage && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-5 right-5 z-50 flex items-center gap-2 bg-slate-900 text-white dark:bg-white dark:text-slate-900 px-4 py-3 rounded-xl shadow-2xl border border-slate-700 text-xs font-semibold animate-in fade-in slide-in-from-bottom-5"
        >
          <CheckCircle2 className="h-4 w-4 text-emerald-400 dark:text-emerald-600" aria-hidden="true" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Conteúdo Principal */}
      <main id="main-content" className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Barra de Ações Rápidas */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xs">
          <div>
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              {activeTab === "kanban" && "Pipeline de Candidaturas (ATS Pessoal)"}
              {activeTab === "match" && "Análise Semântica & Aderência à Vaga"}
              {activeTab === "analytics" && "Métricas Analíticas & Performance de Carreira"}
              {activeTab === "resume" && "Visualizador e Exportador ATS (PDF / DOCX)"}
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Acompanhe suas oportunidades e otimize currículos orientados à IA e sem alucinações.
            </p>
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto">
            <button
              type="button"
              onClick={loadData}
              disabled={isLoading}
              className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition"
              aria-label="Recarregar dados da plataforma"
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} aria-hidden="true" />
            </button>

            <button
              type="button"
              onClick={() => setIsAnalyzerOpen(true)}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-xs hover:shadow transition focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              <span>Analisar Nova Vaga & Gerar CV</span>
            </button>
          </div>
        </div>

        {/* Conteúdo da Aba Ativa */}
        {activeTab === "kanban" && (
          <KanbanBoard
            applications={applications}
            onStatusChange={handleStatusChange}
            isLoading={isLoading}
          />
        )}

        {activeTab === "match" && (
          <div className="space-y-4">
            {activeAnalysis ? (
              <MatchPreviewCard
                analysis={activeAnalysis}
                onGenerateResume={() => setIsAnalyzerOpen(true)}
              />
            ) : (
              <div className="bg-white dark:bg-slate-800 p-8 rounded-xl border border-slate-200 dark:border-slate-700 text-center space-y-3">
                <FileCheck className="h-10 w-10 text-slate-400 mx-auto" aria-hidden="true" />
                <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200">
                  Nenhuma análise ativa
                </h2>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Clique em &quot;Analisar Nova Vaga&quot; para comparar a descrição de uma vaga com o seu dossiê profissional.
                </p>
                <button
                  type="button"
                  onClick={() => setIsAnalyzerOpen(true)}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-bold"
                >
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  <span>Analisar Vaga Agora</span>
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === "analytics" && (
          <AnalyticsDashboard
            metrics={metrics}
            onRefresh={loadData}
            isLoading={isLoading}
          />
        )}

        {activeTab === "resume" && (
          <div className="space-y-4">
            {activeResume ? (
              <ResumeViewer resume={activeResume} />
            ) : (
              <div className="bg-white dark:bg-slate-800 p-8 rounded-xl border border-slate-200 dark:border-slate-700 text-center space-y-3">
                <Sparkles className="h-10 w-10 text-indigo-500 mx-auto" aria-hidden="true" />
                <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200">
                  Nenhum currículo selecionado
                </h2>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Gere um currículo direcionado usando o assistente de IA ou selecione uma candidatura existente.
                </p>
                <button
                  type="button"
                  onClick={() => setIsAnalyzerOpen(true)}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-bold"
                >
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  <span>Gerar Currículo Otimizado</span>
                </button>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Modais e Drawers */}
      <JobAnalyzerModal
        isOpen={isAnalyzerOpen}
        onClose={() => setIsAnalyzerOpen(false)}
        onAnalysisComplete={(analysis) => {
          setActiveAnalysis(analysis);
          setActiveTab("match");
          showToast("Aderência calculada com sucesso!");
        }}
        onResumeGenerated={(resume) => {
          setActiveResume(resume);
          setActiveTab("resume");
          showToast("Currículo sintetizado com validação anti-alucinação!");
          loadData();
        }}
      />

      <NotificationDrawer
        isOpen={isNotificationOpen}
        onClose={() => setIsNotificationOpen(false)}
        notifications={notifications}
        onMarkAsRead={handleMarkOneRead}
        onMarkAllAsRead={handleMarkAllRead}
        onTriggerScan={handleTriggerScan}
        isScanning={isScanning}
      />
    </div>
  );
}
