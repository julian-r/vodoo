import type { JsonObject } from "./types.js";

export class VodooError extends Error {
  override readonly name: string = "VodooError";
}

export class ConfigurationError extends VodooError {
  override readonly name = "ConfigurationError";
}

export class AuthenticationError extends VodooError {
  override readonly name = "AuthenticationError";
}

export class RecordNotFoundError extends VodooError {
  override readonly name = "RecordNotFoundError";

  constructor(
    readonly model: string,
    readonly recordId: number,
  ) {
    super(`Record ${recordId} not found in ${model}`);
  }
}

export class TransportError extends VodooError {
  override readonly name: string = "TransportError";

  constructor(
    message: string,
    readonly code = -1,
    readonly data: JsonObject = {},
  ) {
    super(`[${code}] ${message}`);
  }
}

export class OdooUserError extends TransportError {
  override readonly name: string = "OdooUserError";
}

export class OdooAccessDeniedError extends OdooUserError {
  override readonly name = "OdooAccessDeniedError";
}

export class OdooAccessError extends OdooUserError {
  override readonly name = "OdooAccessError";
}

export class OdooMissingError extends OdooUserError {
  override readonly name = "OdooMissingError";
}

export class OdooValidationError extends OdooUserError {
  override readonly name = "OdooValidationError";
}

/** Raw fetch/stream/timeout failure. It intentionally is not a VodooError. */
export class NetworkError extends Error {
  override readonly name = "NetworkError";

  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
  }
}

/** HTTP status failure used by legacy JSON-RPC, matching httpx.raise_for_status(). */
export class HttpStatusError extends Error {
  override readonly name = "HttpStatusError";

  constructor(
    readonly status: number,
    readonly statusText: string,
  ) {
    super(`HTTP ${status}${statusText ? ` ${statusText}` : ""}`);
  }
}

const exceptionClasses: Readonly<Record<string, typeof TransportError>> = {
  "odoo.exceptions.UserError": OdooUserError,
  "odoo.exceptions.AccessDenied": OdooAccessDeniedError,
  "odoo.exceptions.AccessError": OdooAccessError,
  "odoo.exceptions.MissingError": OdooMissingError,
  "odoo.exceptions.ValidationError": OdooValidationError,
};

export function transportErrorFromData(
  message: string,
  code = -1,
  data: JsonObject | null = null,
): TransportError {
  const exceptionName = typeof data?.name === "string" ? data.name : "";
  const ErrorClass = exceptionClasses[exceptionName] ?? TransportError;
  return new ErrorClass(message, code, data ?? {});
}
