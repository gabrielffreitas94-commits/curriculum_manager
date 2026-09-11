import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { Header } from "@/components/Header";

describe("Header Component", () => {
  const defaultProps = {
    activeTab: "kanban" as const,
    onTabChange: vi.fn(),
    unreadCount: 0,
    onOpenNotifications: vi.fn(),
  };

  it("should render brand name and skip to content link", () => {
    render(<Header {...defaultProps} />);

    expect(screen.getByText("ThothCVs")).toBeInTheDocument();
    expect(screen.getByText("AI")).toBeInTheDocument();
    expect(screen.getByText("Personal ATS")).toBeInTheDocument();

    const skipLink = screen.getByRole("link", { name: /pular para o conteúdo principal/i });
    expect(skipLink).toBeInTheDocument();
    expect(skipLink).toHaveAttribute("href", "#main-content");
  });

  it("should render all main navigation tabs with correct active states", () => {
    const { rerender } = render(<Header {...defaultProps} activeTab="kanban" />);

    const kanbanBtn = screen.getByRole("button", { name: /kanban ats/i });
    const matchBtn = screen.getByRole("button", { name: /análise & match/i });
    const analyticsBtn = screen.getByRole("button", { name: /métricas/i });
    const resumeBtn = screen.getByRole("button", { name: /currículo/i });

    expect(analyticsBtn).toBeInTheDocument();
    expect(resumeBtn).toBeInTheDocument();
    expect(kanbanBtn).toHaveAttribute("aria-current", "page");
    expect(matchBtn).not.toHaveAttribute("aria-current");

    rerender(<Header {...defaultProps} activeTab="match" />);
    expect(matchBtn).toHaveAttribute("aria-current", "page");
    expect(kanbanBtn).not.toHaveAttribute("aria-current");
  });

  it("should trigger onTabChange when navigation tab is clicked", () => {
    const onTabChange = vi.fn();
    render(<Header {...defaultProps} onTabChange={onTabChange} />);

    const matchBtn = screen.getByRole("button", { name: /análise & match/i });
    fireEvent.click(matchBtn);

    expect(onTabChange).toHaveBeenCalledWith("match");
  });

  it("should render unread notifications count and badge", () => {
    const { rerender } = render(<Header {...defaultProps} unreadCount={0} />);

    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Notificações: 0 não lidas")).toBeInTheDocument();

    rerender(<Header {...defaultProps} unreadCount={4} />);
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByLabelText("Notificações: 4 não lidas")).toBeInTheDocument();

    rerender(<Header {...defaultProps} unreadCount={15} />);
    expect(screen.getByText("9+")).toBeInTheDocument();
    expect(screen.getByLabelText("Notificações: 15 não lidas")).toBeInTheDocument();
  });

  it("should trigger onOpenNotifications when notification bell is clicked", () => {
    const onOpenNotifications = vi.fn();
    render(<Header {...defaultProps} onOpenNotifications={onOpenNotifications} />);

    const bellBtn = screen.getByLabelText(/notificações:/i);
    fireEvent.click(bellBtn);

    expect(onOpenNotifications).toHaveBeenCalledTimes(1);
  });
});
