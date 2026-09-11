import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { KanbanBoard } from "@/components/KanbanBoard";
import { ApplicationItem } from "@/types";

describe("KanbanBoard Component", () => {
  const mockApplications: ApplicationItem[] = [
    {
      id: "app-1",
      company_name: "Google Cloud",
      job_title: "Senior Python Architect",
      status: "applied",
      work_model: "remote",
      location: "São Paulo, Brasil",
      needs_follow_up: true,
      last_activity_date: "2026-09-01T00:00:00Z",
      created_at: "2026-09-01T00:00:00Z",
    },
    {
      id: "app-2",
      company_name: "Amazon AWS",
      job_title: "DevOps Engineer",
      status: "screening",
      work_model: "hybrid",
      needs_follow_up: false,
      last_activity_date: "2026-09-08T00:00:00Z",
      created_at: "2026-09-08T00:00:00Z",
    },
  ];

  const defaultProps = {
    applications: mockApplications,
    onStatusChange: vi.fn().mockResolvedValue(undefined),
    onSelectApplication: vi.fn(),
  };

  it("should render all 5 ATS Kanban columns with their titles and count badges", () => {
    render(<KanbanBoard {...defaultProps} />);

    expect(screen.getByRole("region", { name: /quadro kanban de candidaturas ats/i })).toBeInTheDocument();
    expect(screen.getByText("Candidatura Enviada")).toBeInTheDocument();
    expect(screen.getByText("Triagem / RH")).toBeInTheDocument();
    expect(screen.getByText("Em Entrevistas")).toBeInTheDocument();
    expect(screen.getByText("Proposta Recebida")).toBeInTheDocument();
    expect(screen.getByText("Não Selecionado")).toBeInTheDocument();
  });

  it("should render application card details including company, title, work model, and location", () => {
    render(<KanbanBoard {...defaultProps} />);

    expect(screen.getByText("Senior Python Architect")).toBeInTheDocument();
    expect(screen.getByText("Google Cloud")).toBeInTheDocument();
    expect(screen.getByText("remote")).toBeInTheDocument();
    expect(screen.getByText("São Paulo, Brasil")).toBeInTheDocument();
  });

  it("should show follow-up alert banner when needs_follow_up is true", () => {
    render(<KanbanBoard {...defaultProps} />);

    expect(screen.getByText(/ação necessária: sem contato há 7\+ dias/i)).toBeInTheDocument();
  });

  it("should trigger onSelectApplication when card is clicked", () => {
    const onSelect = vi.fn();
    render(<KanbanBoard {...defaultProps} onSelectApplication={onSelect} />);

    fireEvent.click(screen.getByText("Senior Python Architect"));
    expect(onSelect).toHaveBeenCalledWith(mockApplications[0]);
  });

  it("should move application forward to next status when clicking next button", () => {
    const onStatusChange = vi.fn().mockResolvedValue(undefined);
    render(<KanbanBoard {...defaultProps} onStatusChange={onStatusChange} />);

    // On "applied" status, next is "screening"
    const nextBtn = screen.getByLabelText(/avançar Senior Python Architect.*para próxima etapa/i);
    fireEvent.click(nextBtn);

    expect(onStatusChange).toHaveBeenCalledWith("app-1", "screening");
  });

  it("should display empty state placeholder for columns with 0 applications", () => {
    render(<KanbanBoard {...defaultProps} />);

    const emptyPlaceholders = screen.getAllByText("Nenhuma vaga nesta etapa");
    expect(emptyPlaceholders.length).toBe(3); // interview, offer, rejected
  });
});
