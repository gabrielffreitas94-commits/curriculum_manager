/**
 * Cliente HTTP unificado para comunicação com a API FastAPI do ThothCVs AI.
 *
 * Fornece métodos tipados para consumo de candidaturas, análise semântica,
 * geração e exportação de currículos, além do centro de notificações.
 * Integra propagação automática de X-Correlation-ID e captura estruturada de erros.
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
import { frontendLogger, getCorrelationId } from "@/lib/telemetry";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

/**
 * Erro customizado de integração com a API, contendo metadados de observabilidade
 * como status HTTP e Correlation ID retornado pelo backend.
 */
export class ApiError extends Error {
  public status: number;
  public correlationId: string | null;
  public detail?: string;
  public url?: string;
  public method?: string;

  constructor(
    message: string,
    options?: {
      status?: number;
      correlationId?: string | null;
      detail?: string;
      url?: string;
      method?: string;
    }
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options?.status ?? 500;
    this.correlationId = options?.correlationId ?? null;
    this.detail = options?.detail;
    this.url = options?.url;
    this.method = options?.method;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export class ApiClient {
  private static token: string = "mock_auth_token_for_dev";

  public static setToken(newToken: string): void {
    ApiClient.token = newToken;
  }

  private static getHeaders(customCorrelationId?: string): HeadersInit {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${ApiClient.token}`,
      "X-Correlation-ID": customCorrelationId || getCorrelationId(),
    };
  }

  private static extractCorrelationId(res: Response): string | null {
    if (!res || !res.headers || typeof res.headers.get !== "function") {
      return null;
    }
    return res.headers.get("x-correlation-id") || res.headers.get("X-Correlation-ID");
  }

  private static handleError(
    res: Response,
    defaultMessage: string,
    url: string,
    method: string,
    detail?: string
  ): never {
    const correlationId = ApiClient.extractCorrelationId(res);
    frontendLogger.error("api_request_failed", {
      url,
      method,
      status: res.status,
      correlation_id: correlationId || undefined,
      error_detail: detail || defaultMessage,
    });
    throw new ApiError(detail || defaultMessage, {
      status: res.status,
      correlationId,
      detail,
      url,
      method,
    });
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
    if (!res.ok) {
      ApiClient.handleError(res, "Erro ao buscar candidaturas.", url, "GET");
    }
    return res.json();
  }

  public static async getApplicationDetail(
    id: string
  ): Promise<ApplicationDetail> {
    const url = `${API_BASE_URL}/applications/${id}`;
    const res = await fetch(url, {
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) {
      ApiClient.handleError(res, "Erro ao buscar detalhes da vaga.", url, "GET");
    }
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
    const url = `${API_BASE_URL}/applications`;
    const res = await fetch(url, {
      method: "POST",
      headers: ApiClient.getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      ApiClient.handleError(res, "Erro ao cadastrar candidatura.", url, "POST");
    }
    return res.json();
  }

  public static async updateApplicationStatus(
    id: string,
    newStatus: ApplicationStatus
  ): Promise<ApplicationItem> {
    const url = `${API_BASE_URL}/applications/${id}`;
    const res = await fetch(url, {
      method: "PATCH",
      headers: ApiClient.getHeaders(),
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) {
      ApiClient.handleError(res, "Erro ao atualizar status da candidatura.", url, "PATCH");
    }
    return res.json();
  }

  public static async getAnalyticsMetrics(): Promise<ApplicationAnalyticsMetrics> {
    const url = `${API_BASE_URL}/applications/analytics/metrics`;
    const res = await fetch(url, {
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) {
      ApiClient.handleError(res, "Erro ao buscar métricas analíticas.", url, "GET");
    }
    return res.json();
  }

  // --- IA & Currículos ---
  public static async previewMatch(
    jobDescription: string
  ): Promise<MatchPreviewResponse> {
    const url = `${API_BASE_URL}/resumes/match-preview`;
    const res = await fetch(url, {
      method: "POST",
      headers: ApiClient.getHeaders(),
      body: JSON.stringify({ job_description: jobDescription }),
    });
    if (!res.ok) {
      ApiClient.handleError(res, "Erro ao calcular aderência semântica.", url, "POST");
    }
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
    const url = `${API_BASE_URL}/resumes/generate`;
    const res = await fetch(url, {
      method: "POST",
      headers: ApiClient.getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      ApiClient.handleError(
        res,
        "Falha na síntese do currículo com IA.",
        url,
        "POST",
        err.detail
      );
    }
    return res.json();
  }

  public static getExportUrl(
    resumeId: string,
    format: "pdf" | "docx"
  ): string {
    return `${API_BASE_URL}/resumes/${resumeId}/export/${format}`;
  }

  /**
   * Exporta o currículo como Blob binário autenticado com Bearer token.
   * Evita a exposição de credenciais em query strings e impede falhas de autorização (401)
   * decorrentes de downloads diretos desprovidos de headers HTTP.
   *
   * @param resumeId Identificador do currículo gerado.
   * @param format Formato desejado: "pdf" ou "docx".
   * @returns Objeto contendo o Blob do arquivo e o nome do arquivo extraído ou padrão.
   */
  public static async exportResumeBlob(
    resumeId: string,
    format: "pdf" | "docx"
  ): Promise<{ blob: Blob; filename: string }> {
    const url = ApiClient.getExportUrl(resumeId, format);
    const res = await fetch(url, {
      headers: ApiClient.getHeaders(),
    });

    if (!res.ok) {
      ApiClient.handleError(
        res,
        `Falha ao exportar currículo em formato ${format.toUpperCase()}.`,
        url,
        "GET"
      );
    }

    let filename = `curriculo_${resumeId}.${format}`;
    const disposition = res.headers?.get ? res.headers.get("Content-Disposition") : null;
    if (disposition) {
      const match = disposition.match(/filename=["']?([^"';]+)["']?/i);
      if (match && match[1]) {
        filename = match[1].trim();
      }
    }

    const blob = await res.blob();
    return { blob, filename };
  }

  /**
   * Realiza o download seguro do currículo disparando a requisição autenticada com Bearer token,
   * convertendo a resposta em Blob e acionando o download no navegador via Object URL.
   *
   * @param resumeId Identificador do currículo gerado.
   * @param format Formato de exportação ("pdf" | "docx").
   * @param defaultFilename Nome alternativo para o arquivo baixado.
   */
  public static async downloadExport(
    resumeId: string,
    format: "pdf" | "docx",
    defaultFilename?: string
  ): Promise<void> {
    const { blob, filename } = await ApiClient.exportResumeBlob(resumeId, format);
    const downloadName = defaultFilename || filename;
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = downloadName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(blobUrl);
  }

  // --- Notificações ---
  public static async getNotifications(
    unreadOnly: boolean = false
  ): Promise<NotificationItem[]> {
    const url = `${API_BASE_URL}/notifications?unread_only=${unreadOnly}`;
    const res = await fetch(url, { headers: ApiClient.getHeaders() });
    if (!res.ok) {
      ApiClient.handleError(res, "Erro ao carregar notificações.", url, "GET");
    }
    return res.json();
  }

  public static async getUnreadCount(): Promise<number> {
    const url = `${API_BASE_URL}/notifications/unread-count`;
    const res = await fetch(url, {
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) {
      frontendLogger.warn("api_request_failed_fallback", {
        url,
        method: "GET",
        status: res.status,
      });
      return 0;
    }
    const data = await res.json();
    return data.unread_count || 0;
  }

  public static async markAsRead(id: string): Promise<void> {
    const url = `${API_BASE_URL}/notifications/${id}/read`;
    await fetch(url, {
      method: "PATCH",
      headers: ApiClient.getHeaders(),
    });
  }

  public static async markAllAsRead(): Promise<number> {
    const url = `${API_BASE_URL}/notifications/mark-all-read`;
    const res = await fetch(url, {
      method: "POST",
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) {
      frontendLogger.warn("api_request_failed_fallback", {
        url,
        method: "POST",
        status: res.status,
      });
      return 0;
    }
    const data = await res.json();
    return data.updated_count || 0;
  }

  public static async triggerFollowUpScan(): Promise<number> {
    const url = `${API_BASE_URL}/notifications/scan-follow-ups`;
    const res = await fetch(url, {
      method: "POST",
      headers: ApiClient.getHeaders(),
    });
    if (!res.ok) {
      frontendLogger.warn("api_request_failed_fallback", {
        url,
        method: "POST",
        status: res.status,
      });
      return 0;
    }
    const data = await res.json();
    return data.created_count || 0;
  }
}
