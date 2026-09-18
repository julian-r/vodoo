import type { FetchLike } from "../src/types.js";

export interface CapturedRequest {
  url: string;
  init: RequestInit;
  body: unknown;
}

export type FetchResult =
  | Response
  | Error
  | ((request: CapturedRequest) => Response | Promise<Response>);

export function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function makeFetch(results: FetchResult[]): {
  fetch: FetchLike;
  requests: CapturedRequest[];
} {
  const requests: CapturedRequest[] = [];
  const fetch: FetchLike = async (input, init = {}) => {
    const rawBody = typeof init.body === "string" ? init.body : undefined;
    const request: CapturedRequest = {
      url: String(input),
      init,
      body: rawBody === undefined ? undefined : JSON.parse(rawBody),
    };
    requests.push(request);
    const result = results.shift();
    if (result === undefined)
      throw new Error(`No fetch result queued for ${request.url}`);
    if (result instanceof Error) throw result;
    return typeof result === "function" ? result(request) : result;
  };
  return { fetch, requests };
}

export function headersOf(request: CapturedRequest): Headers {
  return new Headers(request.init.headers);
}
