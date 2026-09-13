/**
 * Módulo de Telemetria e Rastreamento Distribuído do Frontend.
 *
 * Fornece geração determinística de Correlation ID (UUIDv4),
 * gerenciamento de contexto de sessão, higienização estrita de PII/segredos
 * e logging estruturado para diagnóstico no navegador e correlação com o backend GCP.
 */

const SENSITIVE_KEYS = new Set([
  "authorization",
  "token",
  "access_token",
  "refresh_token",
  "password",
  "secret",
  "api_key",
  "apikey",
  "credentials",
  "client_secret",
]);

/**
 * Gera um identificador único de correlação no formato UUIDv4.
 * Utiliza a API nativa crypto.randomUUID() com fallback resiliente.
 */
export function generateCorrelationId(): string {
  if (
    typeof crypto !== "undefined" &&
    crypto &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }

  // Fallback RFC 4122 v4
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

let activeCorrelationId: string | null = null;

/**
 * Retorna o Correlation ID ativo da sessão/requisição atual.
 * Caso ainda não exista, inicializa um novo UUIDv4.
 */
export function getCorrelationId(): string {
  if (!activeCorrelationId) {
    activeCorrelationId = generateCorrelationId();
  }
  return activeCorrelationId;
}

/**
 * Define ou sobrescreve explicitamente o Correlation ID ativo.
 */
export function setCorrelationId(id: string): void {
  activeCorrelationId = id.trim();
}

/**
 * Reseta o Correlation ID ativo, forçando a geração de um novo UUID no próximo acesso.
 */
export function resetCorrelationId(): string {
  activeCorrelationId = generateCorrelationId();
  return activeCorrelationId;
}

/**
 * Higieniza recursivamente objetos e valores, ocultando chaves sensíveis (tokens, senhas).
 */
export function sanitizeLogData(data: unknown): unknown {
  if (data === null || data === undefined) return data;

  if (typeof data === "string") {
    // Scrubbing de Bearer tokens em strings soltas
    if (/bearer\s+[a-zA-Z0-9_\-\.]+/i.test(data)) {
      return data.replace(/bearer\s+[a-zA-Z0-9_\-\.]+/gi, "Bearer [REDACTED]");
    }
    return data;
  }

  if (Array.isArray(data)) {
    return data.map((item) => sanitizeLogData(item));
  }

  if (typeof data === "object") {
    const sanitized: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
      const lowerKey = key.toLowerCase();
      if (SENSITIVE_KEYS.has(lowerKey)) {
        sanitized[key] = "[REDACTED]";
      } else {
        sanitized[key] = sanitizeLogData(value);
      }
    }
    return sanitized;
  }

  return data;
}

export type LogLevel = "DEBUG" | "INFO" | "WARN" | "ERROR";

export interface LogPayload {
  timestamp: string;
  level: LogLevel;
  event: string;
  correlation_id: string;
  [key: string]: unknown;
}

/**
 * Logger estruturado do cliente frontend.
 */
export class FrontendLogger {
  private emit(level: LogLevel, event: string, context?: Record<string, unknown>): LogPayload {
    const payload: LogPayload = {
      timestamp: new Date().toISOString(),
      level,
      event,
      correlation_id: getCorrelationId(),
      ...((sanitizeLogData(context || {}) as Record<string, unknown>) || {}),
    };

    switch (level) {
      case "DEBUG":
        console.debug(`[${payload.level}] ${payload.event}`, payload);
        break;
      case "INFO":
        console.info(`[${payload.level}] ${payload.event}`, payload);
        break;
      case "WARN":
        console.warn(`[${payload.level}] ${payload.event}`, payload);
        break;
      case "ERROR":
        console.error(`[${payload.level}] ${payload.event}`, payload);
        break;
    }

    return payload;
  }

  public debug(event: string, context?: Record<string, unknown>): LogPayload {
    return this.emit("DEBUG", event, context);
  }

  public info(event: string, context?: Record<string, unknown>): LogPayload {
    return this.emit("INFO", event, context);
  }

  public warn(event: string, context?: Record<string, unknown>): LogPayload {
    return this.emit("WARN", event, context);
  }

  public error(event: string, context?: Record<string, unknown>): LogPayload {
    return this.emit("ERROR", event, context);
  }
}

export const frontendLogger = new FrontendLogger();
