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

  it("should call onClose when clicking cancel or close icon button", () => {
    const onClose = vi.fn();
    render(<JobAnalyzerModal {...defaultProps} onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText(/fechar janela modal/i));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
