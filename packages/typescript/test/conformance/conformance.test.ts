import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { decodeBase64, encodeBase64 } from "../../src/binary.js";
import { OdooClient } from "../../src/client.js";
import { Cmd } from "../../src/commands.js";
import {
  formatOdooDate,
  formatOdooDateTime,
  parseOdooDate,
  parseOdooDateTime,
} from "../../src/dates.js";
import { TransportError, transportErrorFromData } from "../../src/errors.js";
import { HelpdeskNamespace } from "../../src/namespaces/helpdesk.js";
import { RecordingClient } from "../../src/testing.js";
import {
  buildJSON2Body,
  JSON2Transport,
  LegacyTransport,
  isRetryableMethod,
  parseJSON2Response,
  parseNameSearch,
  retryDelayMs,
} from "../../src/transport.js";
import type { Domain, FetchLike, JsonObject } from "../../src/types.js";

interface Json2BodyScenario {
  readonly id: string;
  readonly method: string;
  readonly args: readonly unknown[];
  readonly kwargs?: Readonly<Record<string, unknown>>;
  readonly expect?: Readonly<Record<string, unknown>>;
  readonly expectError?: "TypeError";
}

interface ResponseScenario {
  readonly id: string;
  readonly wire: string;
  readonly expect: unknown;
}

interface ErrorScenario {
  readonly id: string;
  readonly message: string;
  readonly code: number;
  readonly data: JsonObject;
  readonly class: string;
  readonly rendered: string;
}

interface DateScenario {
  readonly id: string;
  readonly kind: "date" | "datetime";
  readonly wire: string;
  readonly iso?: string;
  readonly expectError?: "TypeError";
}

interface BinaryScenario {
  readonly id: string;
  readonly bytes: readonly number[];
  readonly base64: string;
}

interface ExpectedRequest {
  readonly method: string;
  readonly path: string;
  readonly headers: Readonly<Record<string, string>>;
  readonly json: unknown;
}

interface CommandScenario {
  readonly id: string;
  readonly operation:
    "create" | "update" | "delete" | "unlink" | "link" | "clear" | "set";
  readonly args: readonly unknown[];
  readonly expect: unknown;
}

interface RetryScenario {
  readonly id: string;
  readonly method: string;
  readonly attempt: number;
  readonly retryable: boolean;
  readonly delayMs: number;
}

interface NormalizationScenario {
  readonly id: string;
  readonly input: Readonly<Record<string, unknown>>;
  readonly expect: Readonly<Record<string, unknown>>;
}

interface OperationScenario {
  readonly id: string;
  readonly operation: "helpdesk.create";
  readonly input: {
    readonly name: string;
    readonly description: string;
    readonly partnerId: number;
    readonly tagIds: readonly number[];
    readonly teamId: number;
    readonly extraFields: Readonly<Record<string, unknown>>;
  };
  readonly expectedModel: string;
  readonly expectedValues: Readonly<Record<string, unknown>>;
  readonly expectedResult: number;
}

interface CreateResultScenario {
  readonly id: string;
  readonly wire: unknown;
  readonly expect?: number;
  readonly expectError?: boolean;
}

interface TransportScenario {
  readonly id: string;
  readonly dialect: "json2" | "jsonrpc";
  readonly config: {
    readonly url: string;
    readonly database: string;
    readonly username: string;
    readonly password: string;
  };
  readonly invoke: {
    readonly operation: "searchRead" | "search";
    readonly model: string;
    readonly domain: Domain;
    readonly fields?: readonly string[];
    readonly limit: number;
    readonly offset: number;
    readonly order: string;
  };
  readonly responses: readonly {
    readonly status: number;
    readonly body: unknown;
  }[];
  readonly expect: {
    readonly requests: readonly ExpectedRequest[];
    readonly value: unknown;
  };
}

interface Fixture {
  readonly schema: number;
  readonly json2Bodies: readonly Json2BodyScenario[];
  readonly json2Responses: readonly ResponseScenario[];
  readonly nameSearch: { readonly input: unknown; readonly expect: unknown };
  readonly errors: readonly ErrorScenario[];
  readonly dates: readonly DateScenario[];
  readonly binary: readonly BinaryScenario[];
  readonly commands: readonly CommandScenario[];
  readonly retry: readonly RetryScenario[];
  readonly normalization: readonly NormalizationScenario[];
  readonly operations: readonly OperationScenario[];
  readonly createResults: readonly CreateResultScenario[];
  readonly transports: readonly TransportScenario[];
}

const fixtureUrl = new URL(
  "../../../../conformance/fixtures/v1.json",
  import.meta.url,
);
const fixture = JSON.parse(readFileSync(fixtureUrl, "utf8")) as Fixture;

function canonicalRequest(
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  expected: ExpectedRequest,
): ExpectedRequest {
  const headers = new Headers(init?.headers);
  const body = typeof init?.body === "string" ? init.body : "{}";
  return {
    method: init?.method ?? "GET",
    path: new URL(String(input)).pathname,
    headers: Object.fromEntries(
      Object.keys(expected.headers).map((name) => [
        name,
        headers.get(name) ?? "",
      ]),
    ),
    json: JSON.parse(body) as unknown,
  };
}

describe("shared cross-language conformance fixture", () => {
  it("uses schema version 1", () => {
    expect(fixture.schema).toBe(1);
  });

  for (const scenario of fixture.json2Bodies) {
    it(`JSON-2 body: ${scenario.id}`, () => {
      const invoke = (): Record<string, unknown> =>
        buildJSON2Body(scenario.method, scenario.args, scenario.kwargs ?? null);
      if (scenario.expectError === "TypeError") {
        expect(invoke).toThrow(TypeError);
      } else {
        expect(invoke()).toEqual(scenario.expect);
      }
    });
  }

  for (const scenario of fixture.json2Responses) {
    it(`JSON-2 response: ${scenario.id}`, () => {
      expect(parseJSON2Response(scenario.wire)).toEqual(scenario.expect);
    });
  }

  it("normalizes name_search pairs", () => {
    expect(parseNameSearch(fixture.nameSearch.input)).toEqual(
      fixture.nameSearch.expect,
    );
  });

  for (const scenario of fixture.errors) {
    it(`maps errors: ${scenario.id}`, () => {
      const error = transportErrorFromData(
        scenario.message,
        scenario.code,
        scenario.data,
      );
      expect(error.constructor.name).toBe(scenario.class);
      expect(error.message).toBe(scenario.rendered);
      expect(error.code).toBe(scenario.code);
      expect(error.data).toEqual(scenario.data);
    });
  }

  for (const scenario of fixture.dates) {
    it(`normalizes dates: ${scenario.id}`, () => {
      const invoke = (): Date =>
        scenario.kind === "date"
          ? parseOdooDate(scenario.wire)
          : parseOdooDateTime(scenario.wire);
      if (scenario.expectError === "TypeError") {
        expect(invoke).toThrow(TypeError);
        return;
      }
      const value = invoke();
      expect(value.toISOString()).toBe(scenario.iso);
      expect(
        scenario.kind === "date"
          ? formatOdooDate(value)
          : formatOdooDateTime(value),
      ).toBe(scenario.wire);
    });
  }

  for (const scenario of fixture.binary) {
    it(`round-trips binary: ${scenario.id}`, () => {
      const encoded = encodeBase64(new Uint8Array(scenario.bytes));
      expect(encoded).toBe(scenario.base64);
      expect([...decodeBase64(encoded)]).toEqual(scenario.bytes);
    });
  }

  for (const scenario of fixture.commands) {
    it(`serializes command: ${scenario.id}`, () => {
      const [first, second] = scenario.args;
      const value = {
        create: () => Cmd.create(first as Readonly<Record<string, unknown>>),
        update: () =>
          Cmd.update(
            first as number,
            second as Readonly<Record<string, unknown>>,
          ),
        delete: () => Cmd.delete(first as number),
        unlink: () => Cmd.unlink(first as number),
        link: () => Cmd.link(first as number),
        clear: () => Cmd.clear(),
        set: () => Cmd.set(first as readonly number[]),
      }[scenario.operation]();
      expect(value).toEqual(scenario.expect);
    });
  }

  for (const scenario of fixture.retry) {
    it(`applies retry policy: ${scenario.id}`, () => {
      expect(isRetryableMethod(scenario.method)).toBe(scenario.retryable);
      expect(
        retryDelayMs(
          { maxRetries: 2, backoffBaseMs: 500, backoffMaxMs: 30_000 },
          scenario.attempt,
        ),
      ).toBe(scenario.delayMs);
    });
  }

  for (const scenario of fixture.normalization) {
    it(`normalizes records: ${scenario.id}`, async () => {
      const fetch: FetchLike = async () =>
        new Response(JSON.stringify([scenario.input]), { status: 200 });
      const transport = new JSON2Transport({
        url: "https://odoo.example.test",
        database: "fixture-db",
        username: "fixture-user",
        password: "fixture-key",
        fetch,
      });
      const client = new OdooClient(
        {
          url: "https://odoo.example.test",
          database: "fixture-db",
          username: "fixture-user",
          password: "fixture-key",
        },
        { transport },
      );
      await expect(client.searchRead("res.partner")).resolves.toEqual([
        scenario.expect,
      ]);
    });
  }

  for (const scenario of fixture.operations) {
    it(`records operation: ${scenario.id}`, async () => {
      const client = new RecordingClient(undefined, [scenario.expectedResult]);
      const namespace = new HelpdeskNamespace(client);
      const result = await namespace.create(scenario.input.name, {
        description: scenario.input.description,
        partnerId: scenario.input.partnerId,
        tagIds: scenario.input.tagIds,
        teamId: scenario.input.teamId,
        extraFields: scenario.input.extraFields,
      });
      expect(result).toBe(scenario.expectedResult);
      expect(client.calls).toEqual([
        {
          method: "create",
          args: [scenario.expectedModel, scenario.expectedValues, undefined],
        },
      ]);
    });
  }

  for (const scenario of fixture.createResults) {
    it(`validates create result: ${scenario.id}`, async () => {
      const fetch: FetchLike = async () =>
        new Response(JSON.stringify(scenario.wire), { status: 200 });
      const transport = new JSON2Transport({
        url: "https://odoo.example.test",
        database: "fixture-db",
        username: "fixture-user",
        password: "fixture-key",
        fetch,
      });
      const result = transport.create("res.partner", { name: "Fixture" });
      if (scenario.expectError === true) {
        await expect(result).rejects.toBeInstanceOf(TransportError);
      } else {
        await expect(result).resolves.toBe(scenario.expect);
      }
    });
  }

  for (const scenario of fixture.transports) {
    it(`captures transport wire semantics: ${scenario.id}`, async () => {
      const responses = [...scenario.responses];
      const requests: ExpectedRequest[] = [];
      const fetch: FetchLike = async (input, init) => {
        const expected = scenario.expect.requests[requests.length];
        if (expected === undefined) throw new Error("Unexpected request");
        requests.push(canonicalRequest(input, init, expected));
        const response = responses.shift();
        if (response === undefined) throw new Error("No response queued");
        return new Response(JSON.stringify(response.body), {
          status: response.status,
          headers: { "content-type": "application/json" },
        });
      };
      const options = {
        ...scenario.config,
        fetch,
        retry: { maxRetries: 0 },
      };
      const transport =
        scenario.dialect === "json2"
          ? new JSON2Transport(options)
          : new LegacyTransport(options);
      const invoke = scenario.invoke;
      const value =
        invoke.operation === "searchRead"
          ? await transport.searchRead(
              invoke.model,
              invoke.domain,
              invoke.fields ?? null,
              invoke.limit,
              invoke.offset,
              invoke.order,
            )
          : await transport.search(
              invoke.model,
              invoke.domain,
              invoke.limit,
              invoke.offset,
              invoke.order,
            );
      expect(value).toEqual(scenario.expect.value);
      expect(requests).toEqual(scenario.expect.requests);
      expect(responses).toHaveLength(0);
    });
  }

  it("preserves opaque credential whitespace", () => {
    const transport = new JSON2Transport({
      url: "https://odoo.example.test",
      database: " db ",
      username: " user ",
      password: " key ",
      fetch: async () => new Response(),
    });
    expect(transport.database).toBe("db");
    expect(transport.username).toBe("user");
    expect(transport.password).toBe(" key ");
  });
});
