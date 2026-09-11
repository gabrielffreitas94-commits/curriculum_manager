import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { ApiClient } from "@/lib/api";

describe("ApiClient", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    ApiClient.setToken("test_token_123");
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  describe("Token & Headers Management", () => {
    it("should set custom token and send it in Authorization header", async () => {
      ApiClient.setToken("custom_bearer_jwt");
      let capturedHeaders: HeadersInit | undefined;

      global.fetch = vi.fn().mockImplementation((url, options) => {
        capturedHeaders = options?.headers;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        });
      });

      await ApiClient.getApplications();

      expect(capturedHeaders).toEqual({
        "Content-Type": "application/json",
        Authorization: "Bearer custom_bearer_jwt",
      });
    });
  });

  describe("Applications API", () => {
    it("should fetch applications without params", async () => {
      const mockApps = [{ id: "app-1", company_name: "TechCorp", job_title: "Dev" }];
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockApps),
      });

      const res = await ApiClient.getApplications();
      expect(res).toEqual(mockApps);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/applications?"),
        expect.any(Object)
      );
    });

    it("should fetch applications with filter params", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([]),
      });

      await ApiClient.getApplications("applied", true);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/applications?status=applied&needs_follow_up=true"),
        expect.any(Object)
      );
    });

    it("should throw error if getApplications fails", async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });
      await expect(ApiClient.getApplications()).rejects.toThrow("Erro ao buscar candidaturas.");
    });

    it("should fetch application detail by id", async () => {
      const mockDetail = { id: "app-123", company_name: "GCP Cloud" };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockDetail),
      });

      const res = await ApiClient.getApplicationDetail("app-123");
      expect(res).toEqual(mockDetail);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/applications/app-123"),
        expect.any(Object)
      );
    });

    it("should throw error when getApplicationDetail fails", async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });
      await expect(ApiClient.getApplicationDetail("not-found")).rejects.toThrow(
        "Erro ao buscar detalhes da vaga."
      );
    });

    it("should create application", async () => {
      const payload = {
        company_name: "Google",
        job_title: "AI Engineer",
        job_description: "Build cutting-edge AI systems.",
      };
      const mockCreated = { id: "app-created", ...payload };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockCreated),
      });

      const res = await ApiClient.createApplication(payload);
      expect(res).toEqual(mockCreated);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/applications"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify(payload),
        })
      );
    });

    it("should throw error when createApplication fails", async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false });
      await expect(
        ApiClient.createApplication({
          company_name: "Acme",
          job_title: "Dev",
          job_description: "Short",
        })
      ).rejects.toThrow("Erro ao cadastrar candidatura.");
    });

    it("should update application status via PATCH", async () => {
      const mockUpdated = { id: "app-1", status: "interview" };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockUpdated),
      });

      const res = await ApiClient.updateApplicationStatus("app-1", "interview");
      expect(res).toEqual(mockUpdated);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/applications/app-1"),
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ status: "interview" }),
        })
      );
    });

    it("should throw error when updateApplicationStatus fails", async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false });
      await expect(ApiClient.updateApplicationStatus("app-1", "rejected")).rejects.toThrow(
        "Erro ao atualizar status da candidatura."
      );
    });

    it("should get analytics metrics", async () => {
      const mockMetrics = {
        total_applications: 10,
        interview_conversion_rate: 30.0,
        response_rate: 50.0,
        status_distribution: { applied: 7, interview: 3 },
      };
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockMetrics),
      });

      const res = await ApiClient.getAnalyticsMetrics();
      expect(res).toEqual(mockMetrics);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/applications/analytics/metrics"),
        expect.any(Object)
      );
    });

    it("should throw error when getAnalyticsMetrics fails", async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false });
      await expect(ApiClient.getAnalyticsMetrics()).rejects.toThrow(
        "Erro ao buscar métricas analíticas."
      );
    });
  });

  describe("AI & Resume Generation API", () => {
    it("should preview match", async () => {
      const mockPreview = {
        match_percentage: 85,
        mandatory_matches: [],
        desirable_matches: [],
        suggested_keywords: ["Python", "FastAPI"],
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockPreview),
      });

      const res = await ApiClient.previewMatch("Job requiring Python and FastAPI");
      expect(res).toEqual(mockPreview);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/resumes/match-preview"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ job_description: "Job requiring Python and FastAPI" }),
        })
      );
    });

    it("should throw error when previewMatch fails", async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false });
      await expect(ApiClient.previewMatch("desc")).rejects.toThrow(
        "Erro ao calcular aderência semântica."
      );
    });

    it("should generate resume successfully", async () => {
      const mockGen = {
        resume_id: "res-123",
        application_id: "app-123",
        version_number: 1,
        match_percentage: 92,
        match_analysis: {},
        structured_content: {},
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockGen),
      });

      const payload = {
        job_description: "GCP Python Engineer",
        prompt_skill_slug: "tech-startup",
        language: "pt-BR",
      };

      const res = await ApiClient.generateResume(payload);
      expect(res).toEqual(mockGen);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/resumes/generate"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify(payload),
        })
      );
    });

    it("should throw custom detail error when generateResume fails with JSON detail", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ detail: "Alucinação detectada na experiência." }),
      });

      await expect(
        ApiClient.generateResume({ job_description: "Senior Architect" })
      ).rejects.toThrow("Alucinação detectada na experiência.");
    });

    it("should throw fallback error when generateResume fails with empty response", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        json: () => Promise.reject(new Error("invalid json")),
      });

      await expect(
        ApiClient.generateResume({ job_description: "Senior Architect" })
      ).rejects.toThrow("Falha na síntese do currículo com IA.");
    });

    it("should construct export URLs for PDF and DOCX", () => {
      const pdfUrl = ApiClient.getExportUrl("resume-xyz", "pdf");
      const docxUrl = ApiClient.getExportUrl("resume-xyz", "docx");

      expect(pdfUrl).toContain("/resumes/resume-xyz/export/pdf");
      expect(docxUrl).toContain("/resumes/resume-xyz/export/docx");
    });
  });

  describe("Notifications API", () => {
    it("should fetch notifications with default unreadOnly=false", async () => {
      const mockNotifs = [{ id: "notif-1", title: "Follow-up", is_read: false }];
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNotifs),
      });

      const res = await ApiClient.getNotifications();
      expect(res).toEqual(mockNotifs);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/notifications?unread_only=false"),
        expect.any(Object)
      );
    });

    it("should fetch notifications with unreadOnly=true", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([]),
      });

      await ApiClient.getNotifications(true);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/notifications?unread_only=true"),
        expect.any(Object)
      );
    });

    it("should throw error if getNotifications fails", async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false });
      await expect(ApiClient.getNotifications()).rejects.toThrow(
        "Erro ao carregar notificações."
      );
    });

    it("should get unread count and handle error by returning 0", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ unread_count: 5 }),
      });

      const count = await ApiClient.getUnreadCount();
      expect(count).toBe(5);

      // On failure, returns 0
      global.fetch = vi.fn().mockResolvedValue({ ok: false });
      const failCount = await ApiClient.getUnreadCount();
      expect(failCount).toBe(0);
    });

    it("should mark single notification as read", async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true });
      await ApiClient.markAsRead("notif-123");

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/notif-123/read"),
        expect.objectContaining({ method: "PATCH" })
      );
    });

    it("should mark all notifications as read", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ updated_count: 3 }),
      });

      const updated = await ApiClient.markAllAsRead();
      expect(updated).toBe(3);

      global.fetch = vi.fn().mockResolvedValue({ ok: false });
      const failUpdated = await ApiClient.markAllAsRead();
      expect(failUpdated).toBe(0);
    });

    it("should trigger follow-up scan", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ created_count: 2 }),
      });

      const created = await ApiClient.triggerFollowUpScan();
      expect(created).toBe(2);

      global.fetch = vi.fn().mockResolvedValue({ ok: false });
      const failCreated = await ApiClient.triggerFollowUpScan();
      expect(failCreated).toBe(0);
    });
  });
});
