import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  generateCorrelationId,
  getCorrelationId,
  setCorrelationId,
  resetCorrelationId,
  sanitizeLogData,
  frontendLogger,
} from "@/lib/telemetry";

describe("Frontend Telemetry & Correlation ID", () => {
  beforeEach(() => {
    resetCorrelationId();
    vi.restoreAllMocks();
  });

  describe("generateCorrelationId", () => {
    it("should generate a valid UUIDv4 string using crypto.randomUUID if available", () => {
      const id = generateCorrelationId();
      expect(id).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
      );
    });

    it("should generate valid UUIDv4 when crypto.randomUUID is undefined (fallback mode)", () => {
      vi.stubGlobal("crypto", {});
      try {
        const id = generateCorrelationId();
        expect(id).toMatch(
          /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
        );
      } finally {
        vi.unstubAllGlobals();
      }
    });

    it("should generate valid UUIDv4 when crypto is completely undefined", () => {
      vi.stubGlobal("crypto", undefined);
      try {
        const id = generateCorrelationId();
        expect(id).toMatch(
          /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
        );
      } finally {
        vi.unstubAllGlobals();
      }
    });
  });

  describe("getCorrelationId & setCorrelationId & resetCorrelationId", () => {
    it("should return the same correlation ID across multiple calls in the same context", () => {
      const id1 = getCorrelationId();
      const id2 = getCorrelationId();
      expect(id1).toBe(id2);
    });

    it("should allow explicitly setting the correlation ID", () => {
      setCorrelationId("custom-cid-98765");
      expect(getCorrelationId()).toBe("custom-cid-98765");
    });

    it("should reset the correlation ID when requested", () => {
      const id1 = getCorrelationId();
      const id2 = resetCorrelationId();
      expect(id1).not.toBe(id2);
      expect(getCorrelationId()).toBe(id2);
    });
  });

  describe("sanitizeLogData (PII & Secret Scrubbing)", () => {
    it("should return primitives as-is", () => {
      expect(sanitizeLogData(null)).toBeNull();
      expect(sanitizeLogData(undefined)).toBeUndefined();
      expect(sanitizeLogData(123)).toBe(123);
      expect(sanitizeLogData("regular text")).toBe("regular text");
    });

    it("should scrub Bearer tokens in raw string logs", () => {
      const raw = "Request failed with header: Bearer eyJhbGciOi... secret token";
      const sanitized = sanitizeLogData(raw);
      expect(sanitized).toBe("Request failed with header: Bearer [REDACTED] secret token");
    });

    it("should redact sensitive fields in objects and nested structures", () => {
      const dirty = {
        user_id: "user-123",
        token: "jwt.secret.token",
        authorization: "Bearer 12345",
        password: "SuperSecretPassword123!",
        nested: {
          api_key: "AIzaSyD-123456",
          normal_field: "safe_value",
        },
        items: [
          { secret: "hidden", id: 1 },
          { name: "John Doe" },
        ],
      };

      const clean = sanitizeLogData(dirty) as Record<string, unknown>;
      expect(clean.user_id).toBe("user-123");
      expect(clean.token).toBe("[REDACTED]");
      expect(clean.authorization).toBe("[REDACTED]");
      expect(clean.password).toBe("[REDACTED]");
      expect((clean.nested as Record<string, unknown>).api_key).toBe("[REDACTED]");
      expect((clean.nested as Record<string, unknown>).normal_field).toBe("safe_value");
      expect((clean.items as Array<Record<string, unknown>>)[0].secret).toBe("[REDACTED]");
      expect((clean.items as Array<Record<string, unknown>>)[0].id).toBe(1);
    });
  });

  describe("FrontendLogger", () => {
    it("should log info messages with structured payload and correlation_id", () => {
      setCorrelationId("test-session-uuid");
      const consoleSpy = vi.spyOn(console, "info").mockImplementation(() => {});

      const payload = frontendLogger.info("app_mounted", { version: "1.0.0" });

      expect(consoleSpy).toHaveBeenCalledWith("[INFO] app_mounted", expect.any(Object));
      expect(payload.level).toBe("INFO");
      expect(payload.event).toBe("app_mounted");
      expect(payload.correlation_id).toBe("test-session-uuid");
      expect(payload.version).toBe("1.0.0");
      expect(payload.timestamp).toBeDefined();
    });

    it("should log warn messages with scrubbing", () => {
      const consoleSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

      const payload = frontendLogger.warn("auth_warning", { token: "secret" });

      expect(consoleSpy).toHaveBeenCalledWith("[WARN] auth_warning", expect.any(Object));
      expect(payload.level).toBe("WARN");
      expect(payload.token).toBe("[REDACTED]");
    });

    it("should log error messages", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      const payload = frontendLogger.error("fatal_crash", { error: "Network timeout" });

      expect(consoleSpy).toHaveBeenCalledWith("[ERROR] fatal_crash", expect.any(Object));
      expect(payload.level).toBe("ERROR");
      expect(payload.error).toBe("Network timeout");
    });

    it("should log debug messages", () => {
      const consoleSpy = vi.spyOn(console, "debug").mockImplementation(() => {});

      const payload = frontendLogger.debug("dom_rendered", { render_ms: 12.4 });

      expect(consoleSpy).toHaveBeenCalledWith("[DEBUG] dom_rendered", expect.any(Object));
      expect(payload.level).toBe("DEBUG");
      expect(payload.render_ms).toBe(12.4);
    });
  });
});
