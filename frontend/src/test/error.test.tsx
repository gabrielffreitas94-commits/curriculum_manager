import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import GlobalRouteError from "@/app/error";
import { setCorrelationId } from "@/lib/telemetry";

describe("GlobalRouteError Component (app/error.tsx)", () => {
  const mockReset = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation(() => {});
    setCorrelationId("default-test-cid-123");
  });

  it("should render accessible error banner with role alert and heading", () => {
    const error = new Error("Falha no componente de interface");

    render(<GlobalRouteError error={error} reset={mockReset} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Ops! Algo inesperado aconteceu/i })
    ).toBeInTheDocument();
  });

  it("should display correlationId from custom ApiError property", () => {
    const error = Object.assign(new Error("Erro na API"), {
      correlationId: "api-trace-uuid-456",
    });

    render(<GlobalRouteError error={error} reset={mockReset} />);

    const codeEl = screen.getByTestId("support-correlation-id");
    expect(codeEl).toHaveTextContent("api-trace-uuid-456");
  });

  it("should display error.digest when correlationId is absent", () => {
    const error = Object.assign(new Error("Next.js runtime crash"), {
      digest: "next-digest-789",
    });

    render(<GlobalRouteError error={error} reset={mockReset} />);

    const codeEl = screen.getByTestId("support-correlation-id");
    expect(codeEl).toHaveTextContent("next-digest-789");
  });

  it("should fallback to active telemetry correlationId when error has no digest or custom ID", () => {
    const error = new Error("Generic unhandled error");

    render(<GlobalRouteError error={error} reset={mockReset} />);

    const codeEl = screen.getByTestId("support-correlation-id");
    expect(codeEl).toHaveTextContent("default-test-cid-123");
  });

  it("should copy support ID to clipboard and provide accessible visual and screen-reader feedback", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const error = Object.assign(new Error("Crash"), {
      correlationId: "cid-copy-test",
    });

    render(<GlobalRouteError error={error} reset={mockReset} />);

    const copyBtn = screen.getByRole("button", {
      name: /Copiar ID de suporte para a área de transferência/i,
    });
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith("cid-copy-test");
    await waitFor(() => {
      expect(screen.getByText("Copiado!")).toBeInTheDocument();
    });
  });

  it("should invoke reset callback when clicking Tentar novamente", () => {
    const error = new Error("Transient error");

    render(<GlobalRouteError error={error} reset={mockReset} />);

    const retryBtn = screen.getByRole("button", { name: /Tentar novamente/i });
    fireEvent.click(retryBtn);

    expect(mockReset).toHaveBeenCalledTimes(1);
  });

  it("should contain link returning to home page", () => {
    const error = new Error("Navigation error");

    render(<GlobalRouteError error={error} reset={mockReset} />);

    const homeLink = screen.getByRole("link", { name: /Voltar ao Início/i });
    expect(homeLink).toHaveAttribute("href", "/");
  });

  it("should handle clipboard writeText rejection gracefully", async () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockRejectedValue(new Error("Clipboard permission denied")),
      },
    });

    const error = new Error("Test error");
    render(<GlobalRouteError error={error} reset={mockReset} />);

    const copyBtn = screen.getByRole("button", {
      name: /Copiar ID de suporte para a área de transferência/i,
    });
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(screen.queryByText("Copiado!")).not.toBeInTheDocument();
    });
  });
});
