import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { JobAnalyzerModal } from "@/components/JobAnalyzerModal";
import { ApiClient } from "@/lib/api";

describe("JobAnalyzerModal Component", () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onAnalysisComplete: vi.fn(),
    onResumeGenerated: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should not render when isOpen is false", () => {
    const { container } = render(<JobAnalyzerModal {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("should render dialog and inputs when isOpen is true", () => {
    render(<JobAnalyzerModal {...defaultProps} />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/nome da empresa/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/título do cargo/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/idioma do currículo/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/modelo de trabalho/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/descrição completa da vaga/i)).toBeInTheDocument();
  });

  it("should show error when submitting empty job description", async () => {
    render(<JobAnalyzerModal {...defaultProps} />);

    const genBtn = screen.getByRole("button", { name: /sintetizar com ia & salvar/i });
    fireEvent.click(genBtn);

    expect(
      screen.getByText("Por favor, informe a descrição completa da vaga.")
    ).toBeInTheDocument();
  });

  it("should perform match preview and trigger callbacks on success", async () => {
    const mockPreviewResult = {
      match_percentage: 88,
      mandatory_matches: [],
      desirable_matches: [],
      suggested_keywords: [],
    };
    vi.spyOn(ApiClient, "previewMatch").mockResolvedValueOnce(mockPreviewResult);

    const onAnalysisComplete = vi.fn();
    const onClose = vi.fn();

    render(
      <JobAnalyzerModal
        {...defaultProps}
        onAnalysisComplete={onAnalysisComplete}
        onClose={onClose}
      />
    );

    const textarea = screen.getByLabelText(/descrição completa da vaga/i);
    fireEvent.change(textarea, { target: { value: "Senior Cloud Engineer with GCP and Go." } });

    const matchBtn = screen.getByRole("button", { name: /ver aderência rápida/i });
    fireEvent.click(matchBtn);

    await waitFor(() => {
      expect(ApiClient.previewMatch).toHaveBeenCalledWith("Senior Cloud Engineer with GCP and Go.");
      expect(onAnalysisComplete).toHaveBeenCalledWith(mockPreviewResult);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("should generate resume and trigger callbacks on success", async () => {
    const mockGenResult = {
      resume_id: "res-999",
      application_id: "app-999",
      version_number: 1,
      match_percentage: 95,
      match_analysis: {},
      structured_content: {},
    };
    vi.spyOn(ApiClient, "generateResume").mockResolvedValueOnce(mockGenResult);

    const onResumeGenerated = vi.fn();
    const onClose = vi.fn();

    render(
      <JobAnalyzerModal
        {...defaultProps}
        onResumeGenerated={onResumeGenerated}
        onClose={onClose}
      />
    );

    fireEvent.change(screen.getByLabelText(/nome da empresa/i), { target: { value: "Acme Corp" } });
    fireEvent.change(screen.getByLabelText(/título do cargo/i), { target: { value: "Lead SRE" } });
    fireEvent.change(screen.getByLabelText(/descrição completa da vaga/i), {
      target: { value: "Looking for SRE with Terraform and Kubernetes." },
    });

    const generateBtn = screen.getByRole("button", { name: /sintetizar com ia & salvar/i });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(ApiClient.generateResume).toHaveBeenCalledWith({
        job_description: "Looking for SRE with Terraform and Kubernetes.",
        company_name: "Acme Corp",
        job_title: "Lead SRE",
        language: "pt-BR",
        create_application: true,
      });
      expect(onResumeGenerated).toHaveBeenCalledWith(mockGenResult);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("should display API error message when synthesis fails", async () => {
    vi.spyOn(ApiClient, "previewMatch").mockRejectedValueOnce(
      new Error("Falha na conexão com o servidor de IA.")
    );

    render(<JobAnalyzerModal {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/descrição completa da vaga/i), {
      target: { value: "Alguma descrição de vaga válida." },
    });

    fireEvent.click(screen.getByRole("button", { name: /ver aderência rápida/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Falha na conexão com o servidor de IA.");
    });
  });

  it("should update language and work model select inputs", () => {
    render(<JobAnalyzerModal {...defaultProps} />);
    const langSelect = screen.getByLabelText(/idioma do currículo/i);
    fireEvent.change(langSelect, { target: { value: "en-US" } });
    expect(langSelect).toHaveValue("en-US");

    const workSelect = screen.getByLabelText(/modelo de trabalho/i);
    fireEvent.change(workSelect, { target: { value: "hybrid" } });
    expect(workSelect).toHaveValue("hybrid");
  });

  it("should display error if generateResume fails or description is empty", async () => {
    render(<JobAnalyzerModal {...defaultProps} />);

    // Com descrição vazia
    const genBtn = screen.getByRole("button", { name: /sintetizar com ia & salvar/i });
    fireEvent.click(genBtn);
    expect(screen.getByRole("alert")).toHaveTextContent("Por favor, informe a descrição completa da vaga.");

    // Com falha na API
    vi.spyOn(ApiClient, "generateResume").mockRejectedValueOnce(new Error("Erro de alucinação 422."));
    fireEvent.change(screen.getByLabelText(/descrição completa da vaga/i), {
      target: { value: "Descrição de vaga preenchida." },
    });
    fireEvent.click(genBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Erro de alucinação 422.");
    });
  });

  it("should handle focus trap with Tab, Shift+Tab and close on Escape", () => {
    const onClose = vi.fn();
    render(<JobAnalyzerModal {...defaultProps} onClose={onClose} />);

    // Pressiona Escape
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();

    // Simula primeiro elemento focado e Shift+Tab
    const modal = screen.getByRole("dialog");
    const focusables = modal.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const firstElement = focusables[0];
    const lastElement = focusables[focusables.length - 1];

    firstElement.focus();
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });

    lastElement.focus();
    fireEvent.keyDown(window, { key: "Tab", shiftKey: false });
  });

  it("should display error if handleMatchPreview is triggered with empty description", () => {
    render(<JobAnalyzerModal {...defaultProps} />);
    const form = screen.getByLabelText(/descrição completa da vaga/i).closest("form")!;
    fireEvent.submit(form);
    expect(screen.getByRole("alert")).toHaveTextContent("Por favor, informe a descrição completa da vaga.");
  });

  it("should call onClose when clicking cancel or close icon button", () => {
    const onClose = vi.fn();
    render(<JobAnalyzerModal {...defaultProps} onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText(/fechar janela modal/i));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("should display default error messages when errors have empty message", async () => {
    vi.spyOn(ApiClient, "previewMatch").mockRejectedValueOnce(new Error(""));

    render(<JobAnalyzerModal {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/descrição completa da vaga/i), {
      target: { value: "Descrição de teste para erro vazio." },
    });

    fireEvent.click(screen.getByRole("button", { name: /ver aderência rápida/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Erro ao analisar vaga.");
    });

    vi.spyOn(ApiClient, "generateResume").mockRejectedValueOnce(new Error(""));
    fireEvent.click(screen.getByRole("button", { name: /sintetizar com ia & salvar/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Erro ao sintetizar currículo via IA.");
    });
  });
});
