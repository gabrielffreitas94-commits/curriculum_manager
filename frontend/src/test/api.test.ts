import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { ApiClient, ApiError } from "@/lib/api";

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
    it("should set custom token and send it in Authorization header with X-Correlation-ID", async () => {
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
        "X-Correlation-ID": expect.any(String),
      });
    });

    it("should throw ApiError containing status and correlationId extracted from response headers", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        headers: {
          get: (headerName: string) =>
            headerName.toLowerCase() === "x-correlation-id"
              ? "backend-trace-uuid-1234"
              : null,
        },
      });

      try {
        await ApiClient.getApplications();
        expect.unreachable("Deveria ter lançado ApiError");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiError = err as ApiError;
        expect(apiError.status).toBe(403);
        expect(apiError.correlationId).toBe("backend-trace-uuid-1234");
        expect(apiError.message).toBe("Erro ao buscar candidaturas.");
      }
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

    it("should export resume as Blob with Authorization Bearer header", async () => {
      /**
       * VETOR DE AMEAÇA:
       * Download de currículo sem cabeçalho Authorization ou expondo tokens em URLs viola
       * RFC 6750 e causa vazamento de credenciais em logs ou falha 401.
       *
       * COMPORTAMENTO ESPERADO:
       * ApiClient.exportResumeBlob deve enviar cabeçalho Authorization: Bearer e extrair o blob
       * e filename do Content-Disposition da resposta.
       *
       * PREMISSA DO GUARDRAIL:
       * É obrigatório garantir que a requisição envie o Bearer token e retorne o Blob íntegro.
       *
       * ORIENTAÇÃO PARA AGENTES IA:
       * Não remova os cabeçalhos de autenticação nem a extração segura de Content-Disposition.
       */
      const mockBlob = new Blob(["fake-pdf-content"], { type: "application/pdf" });
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: {
          get: (name: string) =>
            name.toLowerCase() === "content-disposition"
              ? 'attachment; filename="curriculo_oficial_ana.pdf"'
              : null,
        },
        blob: () => Promise.resolve(mockBlob),
      });

      const { blob, filename } = await ApiClient.exportResumeBlob("res-123", "pdf");

      expect(blob).toEqual(mockBlob);
      expect(filename).toBe("curriculo_oficial_ana.pdf");
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/resumes/res-123/export/pdf"),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: expect.stringContaining("Bearer "),
          }),
        })
      );
    });

    it("should fallback to default filename when Content-Disposition is missing in exportResumeBlob", async () => {
      const mockBlob = new Blob(["fake-docx-content"]);
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: {
          get: () => null,
        },
        blob: () => Promise.resolve(mockBlob),
      });

      const { filename } = await ApiClient.exportResumeBlob("res-999", "docx");
      expect(filename).toBe("curriculo_res-999.docx");
    });

    it("should throw error when exportResumeBlob fails with !res.ok", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
      });

      await expect(ApiClient.exportResumeBlob("res-123", "pdf")).rejects.toThrow(
        "Falha ao exportar currículo em formato PDF."
      );
    });

    it("should perform secure download via Blob and Object URL in downloadExport", async () => {
      const mockBlob = new Blob(["dummy-pdf"]);
      vi.spyOn(ApiClient, "exportResumeBlob").mockResolvedValue({
        blob: mockBlob,
        filename: "curriculo_teste.pdf",
      });

      const createObjectURLSpy = vi.fn(() => "blob:mock-url");
      const revokeObjectURLSpy = vi.fn();
      global.URL.createObjectURL = createObjectURLSpy;
      global.URL.revokeObjectURL = revokeObjectURLSpy;

      const appendSpy = vi.spyOn(document.body, "appendChild");
      const removeSpy = vi.spyOn(document.body, "removeChild");
      const clickSpy = vi.fn();

      const originalCreateElement = document.createElement.bind(document);
      vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
        const el = originalCreateElement(tagName);
        if (tagName === "a") {
          el.click = clickSpy;
        }
        return el;
      });

      await ApiClient.downloadExport("res-123", "pdf");

      expect(createObjectURLSpy).toHaveBeenCalledWith(mockBlob);
      expect(clickSpy).toHaveBeenCalledTimes(1);
      expect(appendSpy).toHaveBeenCalled();
      expect(removeSpy).toHaveBeenCalled();
      expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock-url");
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

    it("should return 0 when payload numbers are undefined", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });

      expect(await ApiClient.getUnreadCount()).toBe(0);
      expect(await ApiClient.markAllAsRead()).toBe(0);
      expect(await ApiClient.triggerFollowUpScan()).toBe(0);
    });
  });
});
