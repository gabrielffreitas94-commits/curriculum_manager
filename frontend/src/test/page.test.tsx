import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Home from "@/app/page";
import { HomeDashboard } from "@/components/HomeDashboard";
import { ApiClient } from "@/lib/api";

// Mock do ApiClient
vi.mock("@/lib/api", () => ({
  ApiClient: {
    getApplications: vi.fn(),
    getAnalyticsMetrics: vi.fn(),
    getNotifications: vi.fn(),
    getUnreadCount: vi.fn(),
    updateApplicationStatus: vi.fn(),
    triggerFollowUpScan: vi.fn(),
    markAllAsRead: vi.fn(),
    markAsRead: vi.fn(),
    previewMatch: vi.fn(),
    generateResume: vi.fn(),
    getExportUrl: vi.fn((id: string, fmt: string) => `/api/v1/resumes/${id}/export/${fmt}`),
    exportResumeBlob: vi.fn(),
    downloadExport: vi.fn(),
  },
}));

describe("Home Page Component (app/page.tsx)", () => {
  const mockApplications = [
    {
      id: "app-101",
      company_name: "Fintech Alpha",
      job_title: "Tech Lead Python",
      status: "applied" as const,
      work_model: "remote",
      applied_at: new Date().toISOString(),
      last_activity_at: new Date().toISOString(),
      needs_follow_up: false,
      location: "SP",
    },
  ];

  const mockMetrics = {
    total_applications: 1,
    status_distribution: { applied: 1 },
    stale_applications_count: 0,
    interview_conversion_rate: 0.0,
    offer_conversion_rate: 0.0,
    average_match_score: 90.0,
  };

  const mockNotifications = [
    {
      id: "notif-1",
      user_id: "user-1",
      title: "Lembrete 1",
      message: "Primeiro lembrete.",
      scheduled_for: new Date().toISOString(),
      notification_type: "follow_up_reminder",
      is_read: false,
      created_at: new Date().toISOString(),
    },
    {
      id: "notif-2",
      user_id: "user-1",
      title: "Lembrete 2",
      message: "Segundo lembrete.",
      scheduled_for: new Date().toISOString(),
      notification_type: "follow_up_reminder",
      is_read: false,
      created_at: new Date().toISOString(),
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(ApiClient.getApplications).mockResolvedValue(mockApplications);
    vi.mocked(ApiClient.getAnalyticsMetrics).mockResolvedValue(mockMetrics);
    vi.mocked(ApiClient.getNotifications).mockResolvedValue(mockNotifications);
    vi.mocked(ApiClient.getUnreadCount).mockResolvedValue(2);
    vi.mocked(ApiClient.updateApplicationStatus).mockResolvedValue({} as never);
    vi.mocked(ApiClient.triggerFollowUpScan).mockResolvedValue(2);
    vi.mocked(ApiClient.markAllAsRead).mockResolvedValue(2);
    vi.mocked(ApiClient.markAsRead).mockResolvedValue({} as never);
  });

  it("should render initial dashboard with kanban board and load data", async () => {
    render(<Home />);

    expect(
      screen.getByText("Pipeline de Candidaturas (ATS Pessoal)")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(ApiClient.getApplications).toHaveBeenCalledTimes(1);
      expect(ApiClient.getAnalyticsMetrics).toHaveBeenCalledTimes(1);
      expect(ApiClient.getNotifications).toHaveBeenCalledTimes(1);
      expect(ApiClient.getUnreadCount).toHaveBeenCalledTimes(1);
    });
  });

  it("should switch between navigation tabs properly", async () => {
    render(<Home />);

    // 1. Alterna para Analise Semantica
    const matchTabBtn = screen.getByRole("button", { name: /análise & match/i });
    fireEvent.click(matchTabBtn);
    expect(
      screen.getByText("Análise Semântica & Aderência à Vaga")
    ).toBeInTheDocument();
    expect(
      screen.getByText("5+ anos de experiência com Python e desenvolvimento de APIs modernas")
    ).toBeInTheDocument();

    // 2. Alterna para Metricas Analiticas
    const analyticsTabBtn = screen.getByRole("button", { name: /métricas/i });
    fireEvent.click(analyticsTabBtn);
    expect(
      screen.getByText("Métricas Analíticas & Performance de Carreira")
    ).toBeInTheDocument();

    // 3. Alterna para Visualizador ATS (Curriculo)
    const resumeTabBtn = screen.getByRole("button", { name: /currículo/i });
    fireEvent.click(resumeTabBtn);
    expect(
      screen.getByText("Visualizador e Exportador ATS (PDF / DOCX)")
    ).toBeInTheDocument();
    expect(screen.getByText("Alexandre Silva")).toBeInTheDocument();

    // 4. Volta para o Kanban ATS
    const kanbanTabBtn = screen.getByRole("button", { name: /kanban ats/i });
    fireEvent.click(kanbanTabBtn);
    expect(
      screen.getByText("Pipeline de Candidaturas (ATS Pessoal)")
    ).toBeInTheDocument();
  });

  it("should reload data when clicking the refresh button", async () => {
    render(<Home />);

    await waitFor(() => {
      expect(ApiClient.getApplications).toHaveBeenCalledTimes(1);
    });

    const refreshBtn = screen.getByRole("button", {
      name: /recarregar dados da plataforma/i,
    });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(ApiClient.getApplications).toHaveBeenCalledTimes(2);
    });
  });

  it("should open and close JobAnalyzerModal", async () => {
    render(<Home />);

    const openModalBtn = screen.getByRole("button", {
      name: /analisar nova vaga & gerar cv/i,
    });
    fireEvent.click(openModalBtn);

    expect(
      screen.getByRole("heading", { name: /analisar nova vaga & gerar currículo/i })
    ).toBeInTheDocument();

    const closeBtn = screen.getByRole("button", {
      name: /fechar janela modal de análise de vaga/i,
    });
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(
        screen.queryByRole("heading", { name: /analisar nova vaga & gerar currículo/i })
      ).not.toBeInTheDocument();
    });
  });

  it("should open NotificationDrawer and handle mark one, mark all and trigger scan", async () => {
    render(<Home />);

    await waitFor(() => {
      expect(ApiClient.getNotifications).toHaveBeenCalledTimes(1);
    });

    const notifBtn = screen.getByLabelText(/notificações:/i);
    fireEvent.click(notifBtn);

    expect(
      screen.getByText("Notificações & Lembretes Proativos")
    ).toBeInTheDocument();

    const scanBtn = screen.getByRole("button", {
      name: /disparar varredura de candidaturas/i,
    });
    fireEvent.click(scanBtn);

    await waitFor(() => {
      expect(ApiClient.triggerFollowUpScan).toHaveBeenCalledTimes(1);
    });

    // 1. Marca todas como lidas
    const markAllBtn = screen.getByRole("button", {
      name: /marcar todas as notificações como lidas/i,
    });
    fireEvent.click(markAllBtn);

    await waitFor(() => {
      expect(ApiClient.markAllAsRead).toHaveBeenCalledTimes(1);
    });

    const closeDrawerBtn = screen.getByRole("button", {
      name: /fechar painel de notificações/i,
    });
    fireEvent.click(closeDrawerBtn);
  });

  it("should handle marking an individual notification as read", async () => {
    render(<Home />);

    await waitFor(() => {
      expect(ApiClient.getNotifications).toHaveBeenCalledTimes(1);
    });

    const notifBtn = screen.getByLabelText(/notificações:/i);
    fireEvent.click(notifBtn);

    const markOneButtons = screen.getAllByRole("button", {
      name: /marcar como lida/i,
    });
    expect(markOneButtons.length).toBeGreaterThan(0);
    fireEvent.click(markOneButtons[0]);

    await waitFor(() => {
      expect(ApiClient.markAsRead).toHaveBeenCalledWith("notif-1");
    });
  });

  it("should handle error in handleMarkOneRead gracefully", async () => {
    vi.mocked(ApiClient.markAsRead).mockRejectedValueOnce(new Error("Erro ao marcar"));
    render(<Home />);

    await waitFor(() => {
      expect(ApiClient.getNotifications).toHaveBeenCalledTimes(1);
    });

    const notifBtn = screen.getByLabelText(/notificações:/i);
    fireEvent.click(notifBtn);

    const markOneButtons = screen.getAllByRole("button", {
      name: /marcar como lida/i,
    });
    fireEvent.click(markOneButtons[0]);

    await waitFor(() => {
      expect(ApiClient.markAsRead).toHaveBeenCalledWith("notif-1");
    });
  });

  it("should handle API failure gracefully during data loading and actions", async () => {
    vi.mocked(ApiClient.getApplications).mockRejectedValueOnce(new Error("Network Error"));
    vi.mocked(ApiClient.updateApplicationStatus).mockRejectedValueOnce(new Error("Update failed"));
    vi.mocked(ApiClient.triggerFollowUpScan).mockRejectedValueOnce(new Error("Scan failed"));
    vi.mocked(ApiClient.markAllAsRead).mockRejectedValueOnce(new Error("Mark all failed"));

    render(<Home />);

    await waitFor(() => {
      expect(ApiClient.getNotifications).toHaveBeenCalled();
    });

    const notifBtn = screen.getByLabelText(/notificações:/i);
    fireEvent.click(notifBtn);

    const scanBtn = screen.getByRole("button", {
      name: /disparar varredura de candidaturas/i,
    });
    fireEvent.click(scanBtn);

    const markAllBtn = screen.getByRole("button", {
      name: /marcar todas as notificações como lidas/i,
    });
    fireEvent.click(markAllBtn);

    await waitFor(() => {
      expect(ApiClient.markAllAsRead).toHaveBeenCalled();
    });
  });

  it("should handle status change in applications", async () => {
    render(<Home />);

    expect(await screen.findByText("Fintech Alpha")).toBeInTheDocument();

    const advanceBtn = screen.getByRole("button", {
      name: /avançar tech lead python na fintech alpha para próxima etapa/i,
    });
    fireEvent.click(advanceBtn);

    await waitFor(() => {
      expect(ApiClient.updateApplicationStatus).toHaveBeenCalledWith("app-101", "screening");
    });
  });

  it("should trigger onAnalysisComplete callback from modal and update match view", async () => {
    const mockAnalysis = {
      match_percentage: 95,
      mandatory_matches: [],
      desirable_matches: [],
      missing_mandatory: [],
      missing_desirable: [],
      suggested_keywords: ["Python"],
    };
    vi.mocked(ApiClient.previewMatch).mockResolvedValue(mockAnalysis);

    render(<Home />);

    const openBtn = screen.getByRole("button", { name: /analisar nova vaga & gerar cv/i });
    fireEvent.click(openBtn);

    fireEvent.change(screen.getByLabelText(/descrição completa da vaga/i), {
      target: { value: "Descrição de vaga teste para aderência completa." },
    });
    const previewBtn = screen.getByRole("button", { name: /ver aderência rápida/i });
    fireEvent.click(previewBtn);

    await waitFor(() => {
      expect(screen.getByText("Aderência calculada com sucesso!")).toBeInTheDocument();
      expect(screen.getByText("Análise Semântica & Aderência à Vaga")).toBeInTheDocument();
    });

    const genResumeFromMatch = screen.getByRole("button", {
      name: /gerar currículo otimizado/i,
    });
    fireEvent.click(genResumeFromMatch);
    expect(
      screen.getByRole("heading", { name: /analisar nova vaga & gerar currículo/i })
    ).toBeInTheDocument();
  });

  it("should trigger onResumeGenerated callback from modal and update resume view", async () => {
    const mockResume = {
      resume_id: "res-new-1",
      application_id: "app-101",
      version_number: 2,
      match_percentage: 98,
      match_analysis: {},
      structured_content: {
        header: { full_name: "Novo Candidato" },
        professional_summary: "Resumo profissional novo.",
        selected_experiences: [],
        skills_highlighted: ["TypeScript"],
        education: [],
        certifications: [],
        languages: [],
      },
    };
    vi.mocked(ApiClient.generateResume).mockResolvedValue(mockResume);

    render(<Home />);

    const openBtn = screen.getByRole("button", { name: /analisar nova vaga & gerar cv/i });
    fireEvent.click(openBtn);

    fireEvent.change(screen.getByLabelText(/descrição completa da vaga/i), {
      target: { value: "Descrição para síntese direta de currículo com IA." },
    });
    const generateBtn = screen.getByRole("button", { name: /sintetizar com ia & salvar/i });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText("Currículo sintetizado com validação anti-alucinação!")).toBeInTheDocument();
      expect(screen.getByText("Novo Candidato")).toBeInTheDocument();
    });
  });

  it("should render empty states when activeAnalysis and activeResume are null and allow opening modal", () => {
    render(<HomeDashboard initialAnalysis={null} initialResume={null} />);

    // Na aba Match com estado vazio
    const matchTabBtn = screen.getByRole("button", { name: /análise & match/i });
    fireEvent.click(matchTabBtn);
    expect(screen.getByText("Nenhuma análise ativa")).toBeInTheDocument();
    const analyzeEmptyBtn = screen.getByRole("button", { name: /analisar vaga agora/i });
    fireEvent.click(analyzeEmptyBtn);
    expect(
      screen.getByRole("heading", { name: /analisar nova vaga & gerar currículo/i })
    ).toBeInTheDocument();

    // Fecha modal
    fireEvent.click(screen.getByRole("button", { name: /fechar janela modal de análise de vaga/i }));

    // Na aba Resume com estado vazio
    const resumeTabBtn = screen.getByRole("button", { name: /currículo/i });
    fireEvent.click(resumeTabBtn);
    expect(screen.getByText("Nenhum currículo selecionado")).toBeInTheDocument();
    const generateEmptyBtn = screen.getByRole("button", { name: /gerar currículo otimizado/i });
    fireEvent.click(generateEmptyBtn);
    expect(
      screen.getByRole("heading", { name: /analisar nova vaga & gerar currículo/i })
    ).toBeInTheDocument();
  });

  it("should handle updating application status successfully", async () => {
    vi.mocked(ApiClient.updateApplicationStatus).mockResolvedValueOnce({
      ...mockApplications[0],
      status: "screening",
    });

    render(<Home />);

    expect(await screen.findByText("Fintech Alpha")).toBeInTheDocument();

    const advanceBtn = screen.getByRole("button", {
      name: /avançar tech lead python na fintech alpha para próxima etapa/i,
    });
    fireEvent.click(advanceBtn);

    await waitFor(() => {
      expect(ApiClient.updateApplicationStatus).toHaveBeenCalledWith("app-101", "screening");
      expect(screen.getByText("Status da vaga atualizado com sucesso!")).toBeInTheDocument();
    });
  });

  it("should handle error when updating application status silently without crashing", async () => {
    vi.mocked(ApiClient.updateApplicationStatus).mockRejectedValueOnce(new Error("Network failure"));

    render(<Home />);

    expect(await screen.findByText("Fintech Alpha")).toBeInTheDocument();

    const advanceBtn = screen.getByRole("button", {
      name: /avançar tech lead python na fintech alpha para próxima etapa/i,
    });
    fireEvent.click(advanceBtn);

    await waitFor(() => {
      expect(ApiClient.updateApplicationStatus).toHaveBeenCalledWith("app-101", "screening");
    });
  });
});
