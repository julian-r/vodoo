import { describe, expect, it, vi } from "vitest";

import { OdooClient } from "../src/client.js";
import {
  AuthenticationError,
  NetworkError,
  OdooAccessError,
  OdooValidationError,
  TransportError,
} from "../src/errors.js";
import {
  JSON2Transport,
  LegacyTransport,
  buildJSON2Body,
  parseJSON2Response,
  parseNameSearch,
} from "../src/transport.js";
import { headersOf, jsonResponse, makeFetch } from "./helpers.js";

const config = {
  url: "https://odoo.example.com/",
  database: "db",
  username: "bot@example.com",
  password: "secret",
};

describe("LegacyTransport", () => {
  it("preserves opaque credential whitespace", () => {
    const transport = new LegacyTransport({
      ...config,
      password: " secret with spaces ",
      fetch: makeFetch([]).fetch,
    });
    expect(transport.password).toBe(" secret with spaces ");
  });

  it("authenticates once and sends Python-compatible execute_kw envelopes", async () => {
    const mock = makeFetch([
      jsonResponse({ result: 7 }),
      jsonResponse({ result: [3, 4] }),
    ]);
    const transport = new LegacyTransport({ ...config, fetch: mock.fetch });

    await expect(transport.search("res.partner", [], 2)).resolves.toEqual([
      3, 4,
    ]);
    await expect(transport.getUid()).resolves.toBe(7);

    expect(mock.requests).toHaveLength(2);
    expect(mock.requests[0]?.url).toBe("https://odoo.example.com/jsonrpc");
    expect(mock.requests[0]?.body).toEqual({
      jsonrpc: "2.0",
      method: "call",
      params: {
        service: "common",
        method: "authenticate",
        args: ["db", "bot@example.com", "secret", {}],
      },
      id: null,
    });
    expect(mock.requests[1]?.body).toEqual({
      jsonrpc: "2.0",
      method: "call",
      params: {
        service: "object",
        method: "execute_kw",
        args: ["db", 7, "secret", "res.partner", "search", [[]], { limit: 2 }],
      },
      id: null,
    });
  });

  it("maps structured server faults", async () => {
    const mock = makeFetch([
      jsonResponse({ result: 7 }),
      jsonResponse({
        error: {
          code: 200,
          message: "server error",
          data: { name: "odoo.exceptions.AccessError", message: "denied" },
        },
      }),
    ]);
    const transport = new LegacyTransport({ ...config, fetch: mock.fetch });
    await expect(transport.read("res.partner", [1])).rejects.toBeInstanceOf(
      OdooAccessError,
    );
  });

  it("does not retry authentication", async () => {
    const mock = makeFetch([new TypeError("fetch failed")]);
    const sleeps = vi.fn(async () => undefined);
    const transport = new LegacyTransport({
      ...config,
      fetch: mock.fetch,
      sleep: sleeps,
    });
    await expect(transport.authenticate()).rejects.toBeInstanceOf(NetworkError);
    expect(mock.requests).toHaveLength(1);
    expect(sleeps).not.toHaveBeenCalled();
  });
});

describe("JSON2 helpers", () => {
  it.each([
    [
      "search_read",
      [[["name", "=", "x"]]],
      { fields: ["id"] },
      { domain: [["name", "=", "x"]], fields: ["id"] },
    ],
    ["read", [[1, 2], ["name"]], null, { ids: [1, 2], fields: ["name"] }],
    ["create", [{ name: "x" }], null, { vals_list: [{ name: "x" }] }],
    ["write", [[1], { name: "x" }], null, { ids: [1], vals: { name: "x" } }],
    ["unlink", [[1, 2]], null, { ids: [1, 2] }],
    ["fields_get", [[]], null, { allfields: [] }],
    [
      "fields_get",
      [["type"]],
      { attributes: ["selection"] },
      { allfields: ["type"], attributes: ["selection"] },
    ],
    ["action_timer_start", [[42]], null, { ids: [42] }],
    [
      "name_search",
      [],
      { name: "x", args: [["active", "=", true]], limit: 5 },
      { name: "x", domain: [["active", "=", true]], limit: 5 },
    ],
  ] as const)("maps %s arguments", (method, args, kwargs, expected) => {
    expect(buildJSON2Body(method, args, kwargs)).toEqual(expected);
  });

  it("rejects positional arguments that JSON-2 cannot represent", () => {
    expect(() => buildJSON2Body("custom", ["lost"])).toThrow(
      /requires named keyword arguments/u,
    );
    expect(() => buildJSON2Body("custom", [[1], "lost"])).toThrow(
      /requires named keyword arguments/u,
    );
  });

  it.each([
    ["", null],
    ["null", null],
    ["false", null],
    ["true", true],
    ["42", 42],
    ["3.14", 3.14],
    ['{"id":1}', { id: 1 }],
    ["hello", "hello"],
  ])("parses scalar %j", (input, expected) => {
    expect(parseJSON2Response(input)).toEqual(expected);
  });

  it("skips malformed name_search entries", () => {
    expect(parseNameSearch([[1, "Alice"], "bad", [3], ["x", "wrong"]])).toEqual(
      [[1, "Alice"]],
    );
  });
});

describe("JSON2Transport", () => {
  it("uses Python-compatible timeout and retry defaults", () => {
    const mock = makeFetch([]);
    const transport = new JSON2Transport({ ...config, fetch: mock.fetch });
    expect(transport.timeoutMs).toBe(30_000);
    expect(transport.retry).toEqual({
      maxRetries: 2,
      backoffBaseMs: 500,
      backoffMaxMs: 30_000,
    });
  });

  it("sets mandatory headers after extra headers and unwraps create IDs", async () => {
    const mock = makeFetch([jsonResponse([91])]);
    const transport = new JSON2Transport({
      ...config,
      fetch: mock.fetch,
      headers: {
        authorization: "wrong",
        "content-type": "wrong",
        "X-Custom": "yes",
      },
    });

    await expect(
      transport.create("project.milestone", { name: "Beta" }),
    ).resolves.toBe(91);
    expect(mock.requests[0]?.url).toBe(
      "https://odoo.example.com/json/2/project.milestone/create",
    );
    expect(mock.requests[0]?.body).toEqual({ vals_list: [{ name: "Beta" }] });
    const headers = headersOf(mock.requests[0]!);
    expect(headers.get("authorization")).toBe("bearer secret");
    expect(headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(headers.get("x-odoo-database")).toBe("db");
    expect(headers.get("x-custom")).toBe("yes");
  });

  it("authenticates by looking up the configured login and caches uid", async () => {
    const mock = makeFetch([jsonResponse([{ id: 7 }])]);
    const transport = new JSON2Transport({ ...config, fetch: mock.fetch });
    await expect(transport.getUid()).resolves.toBe(7);
    await expect(transport.getUid()).resolves.toBe(7);
    expect(mock.requests).toHaveLength(1);
    expect(mock.requests[0]?.body).toEqual({
      domain: [["login", "=", "bot@example.com"]],
      fields: ["id"],
      limit: 1,
    });
  });

  it("wraps authentication transport errors", async () => {
    const mock = makeFetch([jsonResponse({ message: "bad key" }, 401)]);
    const transport = new JSON2Transport({ ...config, fetch: mock.fetch });
    await expect(transport.authenticate()).rejects.toBeInstanceOf(
      AuthenticationError,
    );
  });

  it("maps JSON-2 structured faults", async () => {
    const mock = makeFetch([
      jsonResponse(
        {
          message: "invalid",
          data: { name: "odoo.exceptions.ValidationError", message: "invalid" },
        },
        422,
      ),
    ]);
    const transport = new JSON2Transport({ ...config, fetch: mock.fetch });
    await expect(
      transport.write("res.partner", [1], { name: "" }),
    ).rejects.toBeInstanceOf(OdooValidationError);
  });

  it("retries allowlisted network failures with Python backoff", async () => {
    const mock = makeFetch([
      new TypeError("fetch failed"),
      new TypeError("fetch failed"),
      jsonResponse([{ id: 1 }]),
    ]);
    const delays: number[] = [];
    const transport = new JSON2Transport({
      ...config,
      fetch: mock.fetch,
      sleep: async (delay) => {
        delays.push(delay);
      },
    });
    await expect(transport.searchRead("res.partner")).resolves.toEqual([
      { id: 1 },
    ]);
    expect(delays).toEqual([500, 1_000]);
    expect(mock.requests).toHaveLength(3);
  });

  it("does not retry writes or HTTP/server errors", async () => {
    const network = makeFetch([new TypeError("fetch failed")]);
    const writeTransport = new JSON2Transport({
      ...config,
      fetch: network.fetch,
    });
    await expect(
      writeTransport.write("res.partner", [1], { name: "x" }),
    ).rejects.toBeInstanceOf(NetworkError);
    expect(network.requests).toHaveLength(1);

    const http = makeFetch([jsonResponse({ message: "gateway" }, 503)]);
    const readTransport = new JSON2Transport({ ...config, fetch: http.fetch });
    await expect(readTransport.read("res.partner", [1])).rejects.toBeInstanceOf(
      TransportError,
    );
    expect(http.requests).toHaveLength(1);
  });
});

describe("OdooClient auto-detection", () => {
  it("falls back to legacy only after a VodooError", async () => {
    const mock = makeFetch([
      jsonResponse({ message: "not JSON-2" }, 404),
      jsonResponse({ result: 7 }),
    ]);
    const client = new OdooClient(config, { fetch: mock.fetch });
    await expect(client.getUid()).resolves.toBe(7);
    expect(client.isJson2).toBe(false);
    expect(mock.requests.map((request) => request.url)).toEqual([
      "https://odoo.example.com/json/2/res.users/search_read",
      "https://odoo.example.com/jsonrpc",
    ]);
  });

  it("does not fall back after a raw network failure", async () => {
    const mock = makeFetch([
      new TypeError("fetch failed"),
      new TypeError("fetch failed"),
      new TypeError("fetch failed"),
    ]);
    const client = new OdooClient(config, {
      fetch: mock.fetch,
      sleep: async () => undefined,
    });
    await expect(client.getUid()).rejects.toBeInstanceOf(NetworkError);
    expect(mock.requests).toHaveLength(3);
    expect(
      mock.requests.every((request) => request.url.includes("/json/2/")),
    ).toBe(true);
  });
});
