import type { OdooClientApi, SearchReadOptions } from "../client-api.js";
import type { OdooRecord } from "../types.js";

/** Convenience namespace for arbitrary installed Odoo models. */
export class GenericNamespace {
  constructor(private readonly client: OdooClientApi) {}

  create(
    model: string,
    values: Readonly<Record<string, unknown>>,
  ): Promise<number> {
    return this.client.create(model, values);
  }

  update(
    model: string,
    recordId: number,
    values: Readonly<Record<string, unknown>>,
  ): Promise<boolean> {
    return this.client.write(model, [recordId], values);
  }

  delete(model: string, recordId: number): Promise<boolean> {
    return this.client.unlink(model, [recordId]);
  }

  search(
    model: string,
    options: SearchReadOptions = {},
  ): Promise<OdooRecord[]> {
    return this.client.searchRead(model, options);
  }

  call(
    model: string,
    method: string,
    args: readonly unknown[] = [],
    kwargs?: Readonly<Record<string, unknown>>,
  ): Promise<unknown> {
    return this.client.execute(model, method, args, kwargs);
  }
}
