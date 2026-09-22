import { describe, expect, it } from "vitest";

import {
  ConfigurationError,
  OdooClient,
  type OdooProtocol,
  type OdooWorkerBindings,
} from "../src/index.js";
import { headersOf, jsonResponse, makeFetch } from "./helpers.js";

const bindings: OdooWorkerBindings = {
  ODOO_URL: "https://odoo.example.com/",
  ODOO_DATABASE: "worker-db",
  ODOO_USERNAME: "worker@example.com",
  ODOO_PASSWORD: "worker-secret",
};

describe("OdooClient.fromBindings", () => {
  it("maps Worker bindings and forces JSON-2 without a detection request", async () => {
    const mock = makeFetch([jsonResponse([{ id: 11, name: "Partner" }])]);
    const client = OdooClient.fromBindings(bindings, {
      protocol: "json2",
      defaultUserId: 23,
      headers: { "CF-Access-Client-Id": "access-id" },
      fetch: mock.fetch,
    });

    expect(client.isJson2).toBe(true);
    expect(client.projects.url(7)).toBe(
      "https://odoo.example.com/odoo/project.project/7",
    );
    expect(mock.requests).toHaveLength(0);

    await expect(
      client.searchRead("res.partner", { fields: ["id", "name"] }),
    ).resolves.toEqual([{ id: 11, name: "Partner" }]);

    expect(client.url).toBe("https://odoo.example.com");
    expect(client.database).toBe("worker-db");
    expect(client.username).toBe("worker@example.com");
    expect(client.defaultUserId).toBe(23);
    expect(client.isJson2).toBe(true);
    expect(mock.requests).toHaveLength(1);
    expect(mock.requests[0]?.url).toBe(
      "https://odoo.example.com/json/2/res.partner/search_read",
    );
    expect(mock.requests[0]?.body).toEqual({
      domain: [],
      fields: ["id", "name"],
    });
    const headers = headersOf(mock.requests[0]!);
    expect(headers.get("authorization")).toBe("bearer worker-secret");
    expect(headers.get("x-odoo-database")).toBe("worker-db");
    expect(headers.get("cf-access-client-id")).toBe("access-id");
  });

  it.each([undefined, "auto"] satisfies ReadonlyArray<
    OdooProtocol | undefined
  >)("uses auto detection when protocol is %s", async (protocol) => {
    const mock = makeFetch([
      jsonResponse([{ id: 7 }]),
      jsonResponse([{ id: 11 }]),
    ]);
    const client = OdooClient.fromBindings(bindings, {
      ...(protocol === undefined ? {} : { protocol }),
      fetch: mock.fetch,
    });

    expect(client.projects.url(7)).toBe(
      "https://odoo.example.com/web#id=7&model=project.project&view_type=form",
    );
    expect(mock.requests).toHaveLength(0);

    await expect(client.searchRead("res.partner")).resolves.toEqual([
      { id: 11 },
    ]);
    expect(client.projects.url(7)).toBe(
      "https://odoo.example.com/odoo/project.project/7",
    );
    expect(mock.requests.map((request) => request.url)).toEqual([
      "https://odoo.example.com/json/2/res.users/search_read",
      "https://odoo.example.com/json/2/res.partner/search_read",
    ]);
  });

  it("forces legacy JSON-RPC and sends custom headers on every request", async () => {
    const mock = makeFetch([
      jsonResponse({ result: 7 }),
      jsonResponse({ result: [{ id: 11 }] }),
    ]);
    const client = OdooClient.fromBindings(bindings, {
      protocol: "jsonrpc",
      headers: {
        "CF-Access-Client-Id": "access-id",
        "CF-Access-Client-Secret": "access-secret",
      },
      fetch: mock.fetch,
    });

    await expect(client.searchRead("res.partner")).resolves.toEqual([
      { id: 11 },
    ]);
    expect(client.isJson2).toBe(false);
    expect(client.projects.url(7)).toBe(
      "https://odoo.example.com/web#id=7&model=project.project&view_type=form",
    );
    expect(mock.requests).toHaveLength(2);
    expect(
      mock.requests.every(
        (request) => request.url === "https://odoo.example.com/jsonrpc",
      ),
    ).toBe(true);
    for (const request of mock.requests) {
      const headers = headersOf(request);
      expect(headers.get("cf-access-client-id")).toBe("access-id");
      expect(headers.get("cf-access-client-secret")).toBe("access-secret");
    }
  });

  it.each([
    "ODOO_URL",
    "ODOO_DATABASE",
    "ODOO_USERNAME",
    "ODOO_PASSWORD",
  ] as const)("rejects a missing %s binding", (name) => {
    const incomplete = { ...bindings } as Record<string, string | undefined>;
    delete incomplete[name];

    expect(() =>
      OdooClient.fromBindings(incomplete as unknown as OdooWorkerBindings),
    ).toThrow(
      new ConfigurationError(`Missing required Odoo Worker binding: ${name}`),
    );
  });
});
