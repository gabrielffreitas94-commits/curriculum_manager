import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { NotificationDrawer } from "@/components/NotificationDrawer";
import { NotificationItem } from "@/types";

describe("NotificationDrawer Component", () => {
  const mockNotifications: NotificationItem[] = [
    {
      id: "notif-1",
      title: "Follow-up Necessário: Google",
      message: "Mais de 7 dias sem contato na candidatura de AI Engineer.",
      is_read: false,
      scheduled_for: "2026-09-15T10:00:00Z",
      type: "follow_up",
    },
    {
      id: "notif-2",
      title: "Candidatura Atualizada",
      message: "Status alterado para Entrevista Técnica.",
      is_read: true,
      scheduled_for: "2026-09-12T14:30:00Z",
      type: "status_update",
    },
  ];

  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    notifications: mockNotifications,
    onMarkAsRead: vi.fn().mockResolvedValue(undefined),
    onMarkAllAsRead: vi.fn().mockResolvedValue(undefined),
    onTriggerScan: vi.fn().mockResolvedValue(undefined),
    isScanning: false,
  };

  it("should not render anything when isOpen is false", () => {
    const { container } = render(<NotificationDrawer {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("should render dialog with accessibility attributes when isOpen is true", () => {
    render(<NotificationDrawer {...defaultProps} />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "notification-drawer-title");

    expect(screen.getByText("Notificações & Lembretes Proativos")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument(); // unread count
  });

  it("should close drawer on Escape key press and on close button click", () => {
    const onClose = vi.fn();
    render(<NotificationDrawer {...defaultProps} onClose={onClose} />);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    const closeBtn = screen.getByLabelText(/fechar painel de notificações/i);
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("should display empty state when notifications array is empty", () => {
    render(<NotificationDrawer {...defaultProps} notifications={[]} />);

    expect(screen.getByText("Nenhuma notificação registrada no momento.")).toBeInTheDocument();
  });

  it("should render list of notifications with read/unread statuses", () => {
    render(<NotificationDrawer {...defaultProps} />);

    expect(screen.getByText("Follow-up Necessário: Google")).toBeInTheDocument();
    expect(screen.getByText("Candidatura Atualizada")).toBeInTheDocument();

    const markAsReadBtn = screen.getByRole("button", { name: /marcar como lida/i });
    expect(markAsReadBtn).toBeInTheDocument();
  });

  it("should trigger onMarkAsRead when clicking mark as read button", async () => {
    const onMarkAsRead = vi.fn().mockResolvedValue(undefined);
    render(<NotificationDrawer {...defaultProps} onMarkAsRead={onMarkAsRead} />);

    const markBtn = screen.getByRole("button", { name: /marcar como lida/i });
    fireEvent.click(markBtn);

    expect(onMarkAsRead).toHaveBeenCalledWith("notif-1");
  });

  it("should trigger onMarkAllAsRead when clicking mark all as read button", () => {
    const onMarkAllAsRead = vi.fn().mockResolvedValue(undefined);
    render(<NotificationDrawer {...defaultProps} onMarkAllAsRead={onMarkAllAsRead} />);

    const markAllBtn = screen.getByRole("button", { name: /marcar todas.*lidas/i });
    fireEvent.click(markAllBtn);

    expect(onMarkAllAsRead).toHaveBeenCalledTimes(1);
  });

  it("should trigger onTriggerScan and show scanning state", () => {
    const onTriggerScan = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <NotificationDrawer {...defaultProps} onTriggerScan={onTriggerScan} isScanning={false} />
    );

    const scanBtn = screen.getByRole("button", { name: /disparar varredura/i });
    fireEvent.click(scanBtn);
    expect(onTriggerScan).toHaveBeenCalledTimes(1);

    rerender(
      <NotificationDrawer {...defaultProps} onTriggerScan={onTriggerScan} isScanning={true} />
    );
    expect(screen.getByText("Varrendo Vagas...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /disparar varredura/i })).toBeDisabled();
  });

  it("should close drawer on Escape key and ignore other keys", () => {
    const onClose = vi.fn();
    render(<NotificationDrawer {...defaultProps} onClose={onClose} />);

    fireEvent.keyDown(window, { key: "Enter" });
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
