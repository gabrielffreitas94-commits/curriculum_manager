import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { AnalyticsDashboard } from "@/components/AnalyticsDashboard";
import { ApplicationAnalyticsMetrics } from "@/types";

describe("AnalyticsDashboard Component", () => {
  const mockMetrics: ApplicationAnalyticsMetrics = {
    total_applications: 20,
    interview_conversion_rate: 35.5,
    offer_conversion_rate: 10.0,
    response_rate: 60.0,
    stale_applications_count: 4,
    average_match_score: 84.2,
    status_distribution: {
      applied: 10,
      screening: 3,
      interview: 4,
      offer: 2,
      rejected: 1,
    },
  };

  const defaultProps = {
    metrics: mockMetrics,
    onRefresh: vi.fn(),
    isLoading: false,
  };

  it("should render all main metric indicators (total, interviews, offers, follow-ups)", () => {
    render(<AnalyticsDashboard {...defaultProps} />);

    expect(screen.getByText("Total de Vagas")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();

    expect(screen.getByText("Convite p/ Entrevista")).toBeInTheDocument();
    expect(screen.getByText("35.5%")).toBeInTheDocument();

    expect(screen.getByText("Taxa de Ofertas")).toBeInTheDocument();
    expect(screen.getByText("10%")).toBeInTheDocument();

    expect(screen.getByText("Ação de Follow-up")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  it("should render pipeline status distribution with progressbars", () => {
    render(<AnalyticsDashboard {...defaultProps} />);

    expect(screen.getByText("Candidatura Enviada")).toBeInTheDocument();
    expect(screen.getByText("10 (50%)")).toBeInTheDocument();

    expect(screen.getByText("Média de Aderência Geral:")).toBeInTheDocument();
    expect(screen.getByText("84.2%")).toBeInTheDocument();

    const progressbars = screen.getAllByRole("progressbar");
    expect(progressbars.length).toBe(5);
  });

  it("should trigger onRefresh when refresh button is clicked", () => {
    const onRefresh = vi.fn();
    render(<AnalyticsDashboard {...defaultProps} onRefresh={onRefresh} />);

    const refreshBtn = screen.getByRole("button", { name: /atualizar dados analíticos/i });
    fireEvent.click(refreshBtn);

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("should display loading state when isLoading is true", () => {
    render(<AnalyticsDashboard {...defaultProps} isLoading={true} />);

    expect(screen.getByText("Atualizando...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /atualizar dados analíticos/i })).toBeDisabled();
  });
});
