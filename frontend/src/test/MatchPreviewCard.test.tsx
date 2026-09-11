import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { MatchPreviewCard } from "@/components/MatchPreviewCard";
import { MatchPreviewResponse } from "@/types";

describe("MatchPreviewCard Component", () => {
  const mockAnalysis: MatchPreviewResponse = {
    match_percentage: 82,
    mandatory_matches: [
      {
        requirement: "Experiência com Python e FastAPI",
        status: "matched",
        evidence: "5 anos liderando desenvolvimento de APIs assíncronas.",
      },
      {
        requirement: "Kubernetes & Docker",
        status: "partial",
        evidence: "Uso de containers Docker em desenvolvimento local.",
      },
      {
        requirement: "Rust",
        status: "missing",
      },
    ],
    desirable_matches: [
      {
        requirement: "Certificação Cloud GCP",
        status: "matched",
        evidence: "GCP Professional Cloud Architect.",
      },
    ],
    suggested_keywords: ["Python", "FastAPI", "GCP", "Kubernetes"],
  };

  it("should render score, progressbar, and correct percentage color", () => {
    const { rerender } = render(<MatchPreviewCard analysis={mockAnalysis} />);

    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("82%")).toHaveClass("text-emerald-600");

    const progressbar = screen.getByRole("progressbar");
    expect(progressbar).toHaveAttribute("aria-valuenow", "82");
    expect(progressbar).toHaveAttribute("aria-valuemin", "0");
    expect(progressbar).toHaveAttribute("aria-valuemax", "100");

    // Test amber score (60-79)
    rerender(<MatchPreviewCard analysis={{ ...mockAnalysis, match_percentage: 65 }} />);
    expect(screen.getByText("65%")).toHaveClass("text-amber-600");

    // Test rose score (<60)
    rerender(<MatchPreviewCard analysis={{ ...mockAnalysis, match_percentage: 45 }} />);
    expect(screen.getByText("45%")).toHaveClass("text-rose-600");
  });

  it("should render mandatory requirements and status badges (matched, partial, missing)", () => {
    render(<MatchPreviewCard analysis={mockAnalysis} />);

    expect(screen.getByText("Requisitos Mandatórios (3)")).toBeInTheDocument();
    expect(screen.getByText("Experiência com Python e FastAPI")).toBeInTheDocument();
    expect(screen.getByText("5 anos liderando desenvolvimento de APIs assíncronas.")).toBeInTheDocument();
    expect(screen.getAllByText("Atendido").length).toBe(2);

    expect(screen.getByText("Kubernetes & Docker")).toBeInTheDocument();
    expect(screen.getByText("Parcial")).toBeInTheDocument();

    expect(screen.getByText("Rust")).toBeInTheDocument();
    expect(screen.getByText("Não Identificado")).toBeInTheDocument();
  });

  it("should render desirable requirements and suggested keywords", () => {
    render(<MatchPreviewCard analysis={mockAnalysis} />);

    expect(screen.getByText("Requisitos Desejáveis (1)")).toBeInTheDocument();
    expect(screen.getByText("Certificação Cloud GCP")).toBeInTheDocument();

    expect(screen.getByText("Palavras-chave recomendadas para ATS")).toBeInTheDocument();
    expect(screen.getByText("FastAPI")).toBeInTheDocument();
    expect(screen.getByText("GCP")).toBeInTheDocument();
  });

  it("should trigger onGenerateResume when action button is clicked", () => {
    const onGenerate = vi.fn();
    render(<MatchPreviewCard analysis={mockAnalysis} onGenerateResume={onGenerate} />);

    const generateBtn = screen.getByRole("button", { name: /gerar currículo otimizado/i });
    expect(generateBtn).not.toBeDisabled();

    fireEvent.click(generateBtn);
    expect(onGenerate).toHaveBeenCalledTimes(1);
  });

  it("should show loading state and disable button when isGenerating is true", () => {
    render(
      <MatchPreviewCard
        analysis={mockAnalysis}
        onGenerateResume={vi.fn()}
        isGenerating={true}
      />
    );

    const btn = screen.getByRole("button", { name: /gerando currículo.../i });
    expect(btn).toBeDisabled();
  });
});
