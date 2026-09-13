import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import GlobalRootError from "@/app/global-error";
import { setCorrelationId } from "@/lib/telemetry";

describe("GlobalRootError Component (app/global-error.tsx)", () => {
  const mockReset = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation(() => {});
    setCorrelationId("global-root-cid-999");
  });

  it("should render critical error heading and alert landmark", () => {
    const error = new Error("Catastrophic root layout crash");

    render(<GlobalRootError error={error} reset={mockReset} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Erro Crítico no Sistema/i })
    ).toBeInTheDocument();
  });

  it("should display support ID from correlationId or fallback", () => {
    const error = Object.assign(new Error("Fatal"), {
      correlationId: "root-fail-111",
    });

    render(<GlobalRootError error={error} reset={mockReset} />);

    const codeEl = screen.getByTestId("global-correlation-id");
    expect(codeEl).toHaveTextContent("root-fail-111");
  });

  it("should copy correlation ID on button click", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const error = Object.assign(new Error("Fatal"), {
      digest: "root-digest-222",
    });

    render(<GlobalRootError error={error} reset={mockReset} />);

    const copyBtn = screen.getByRole("button", {
      name: /Copiar ID de correlação/i,
    });
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith("root-digest-222");
    await waitFor(() => {
      expect(screen.getByText("Copiado!")).toBeInTheDocument();
    });
  });

  it("should trigger reset when clicking Recarregar Aplicação", () => {
    const error = new Error("Fatal");

    render(<GlobalRootError error={error} reset={mockReset} />);

    const reloadBtn = screen.getByRole("button", {
      name: /Recarregar Aplicação/i,
    });
    fireEvent.click(reloadBtn);

    expect(mockReset).toHaveBeenCalledTimes(1);
  });

  it("should handle clipboard writeText rejection gracefully", async () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockRejectedValue(new Error("Clipboard permission denied")),
      },
    });

    const error = new Error("Fatal");
    render(<GlobalRootError error={error} reset={mockReset} />);

    const copyBtn = screen.getByRole("button", {
      name: /Copiar ID de correlação/i,
    });
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(screen.queryByText("Copiado!")).not.toBeInTheDocument();
    });
  });
});
