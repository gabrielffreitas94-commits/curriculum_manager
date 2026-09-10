/**
 * Cliente HTTP unificado para comunicação com a API FastAPI do ThothCVs AI.
 *
 * Fornece métodos tipados para consumo de candidaturas, análise semântica,
 * geração e exportação de currículos, além do centro de notificações.
 */

import {
  ApplicationAnalyticsMetrics,
  ApplicationDetail,
  ApplicationItem,
  ApplicationStatus,
  MatchPreviewResponse,
  NotificationItem,
  ResumeGenerateResponse,
} from "@/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiClient {
  private static token: string = "mock_auth_token_for_dev";

  public static setToken(newToken: string): void {
    ApiClient.token = newToken;
  }

  private static getHeaders(): HeadersInit {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${ApiClient.token}`,
    };
  }

  // --- Candidaturas (ATS) ---
  public static async getApplications(
    status?: string,
    needsFollowUp?: boolean
  ): Promise<ApplicationItem[]> {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    if (needsFollowUp !== undefined)
      params.append("needs_follow_up", String(needsFollowUp));

    const url = `${API_BASE_URL}/applications?${params.toString()}`;
    const res = await fetch(url, { headers: ApiClient.getHeaders() });
    if (!res.ok) throw new Error("Erro ao buscar candidaturas.");
    return res.json();
  }

  public static async getApplicationDetail(
    id: string
  ): Promise<ApplicationDetail> {
    const res = await fetch(`${API_BASE_URL}/applications/${id}`, {
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) throw new Error("Erro ao buscar detalhes da vaga.");
    return res.json();
  }

  public static async createApplication(payload: {
    company_name: string;
    job_title: string;
    job_description: string;
    work_model?: string;
    salary_range?: string;
    location?: string;
    status?: string;
  }): Promise<ApplicationItem> {
    const res = await fetch(`${API_BASE_URL}/applications`, {
      method: "POST",
      headers: ApiClient.getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("Erro ao cadastrar candidatura.");
    return res.json();
  }

  public static async updateApplicationStatus(
    id: string,
    newStatus: ApplicationStatus
  ): Promise<ApplicationItem> {
    const res = await fetch(`${API_BASE_URL}/applications/${id}`, {
      method: "PATCH",
      headers: ApiClient.getHeaders(),
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) throw new Error("Erro ao atualizar status da candidatura.");
    return res.json();
  }

  public static async getAnalyticsMetrics(): Promise<ApplicationAnalyticsMetrics> {
    const res = await fetch(`${API_BASE_URL}/applications/analytics/metrics`, {
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) throw new Error("Erro ao buscar métricas analíticas.");
    return res.json();
  }

  // --- IA & Currículos ---
  public static async previewMatch(
    jobDescription: string
  ): Promise<MatchPreviewResponse> {
    const res = await fetch(`${API_BASE_URL}/resumes/match-preview`, {
      method: "POST",
      headers: ApiClient.getHeaders(),
      body: JSON.stringify({ job_description: jobDescription }),
    });
    if (!res.ok) throw new Error("Erro ao calcular aderência semântica.");
    return res.json();
  }

  public static async generateResume(payload: {
    job_description: string;
    prompt_skill_slug?: string;
    language?: string;
    create_application?: boolean;
    company_name?: string;
    job_title?: string;
  }): Promise<ResumeGenerateResponse> {
    const res = await fetch(`${API_BASE_URL}/resumes/generate`, {
      method: "POST",
      headers: ApiClient.getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Falha na síntese do currículo com IA.");
    }
    return res.json();
  }

  public static getExportUrl(
    resumeId: string,
    format: "pdf" | "docx"
  ): string {
    return `${API_BASE_URL}/resumes/${resumeId}/export/${format}`;
  }

  // --- Notificações ---
  public static async getNotifications(
    unreadOnly: boolean = false
  ): Promise<NotificationItem[]> {
    const res = await fetch(
      `${API_BASE_URL}/notifications?unread_only=${unreadOnly}`,
      { headers: ApiClient.getHeaders() }
    );
    if (!res.ok) throw new Error("Erro ao carregar notificações.");
    return res.json();
  }

  public static async getUnreadCount(): Promise<number> {
    const res = await fetch(`${API_BASE_URL}/notifications/unread-count`, {
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) return 0;
    const data = await res.json();
    return data.unread_count || 0;
  }

  public static async markAsRead(id: string): Promise<void> {
    await fetch(`${API_BASE_URL}/notifications/${id}/read`, {
      method: "PATCH",
      headers: ApiClient.getHeaders(),
    });
  }

  public static async markAllAsRead(): Promise<number> {
    const res = await fetch(`${API_BASE_URL}/notifications/mark-all-read`, {
      method: "POST",
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) return 0;
    const data = await res.json();
    return data.updated_count || 0;
  }

  public static async triggerFollowUpScan(): Promise<number> {
    const res = await fetch(`${API_BASE_URL}/notifications/scan-follow-ups`, {
      method: "POST",
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) return 0;
    const data = await res.json();
    return data.created_count || 0;
  }
}
