/** Odoo ORM commands for x2many relationship fields. */
export type CreateCommand = readonly [0, 0, Readonly<Record<string, unknown>>];
export type UpdateCommand = readonly [
  1,
  number,
  Readonly<Record<string, unknown>>,
];
export type DeleteCommand = readonly [2, number, 0];
export type UnlinkCommand = readonly [3, number, 0];
export type LinkCommand = readonly [4, number, 0];
export type ClearCommand = readonly [5, 0, 0];
export type SetCommand = readonly [6, 0, readonly number[]];
export type OdooCommand =
  | CreateCommand
  | UpdateCommand
  | DeleteCommand
  | UnlinkCommand
  | LinkCommand
  | ClearCommand
  | SetCommand;

export const Cmd = Object.freeze({
  create(values: Readonly<Record<string, unknown>>): CreateCommand {
    return [0, 0, values];
  },
  update(
    recordId: number,
    values: Readonly<Record<string, unknown>>,
  ): UpdateCommand {
    return [1, recordId, values];
  },
  delete(recordId: number): DeleteCommand {
    return [2, recordId, 0];
  },
  unlink(recordId: number): UnlinkCommand {
    return [3, recordId, 0];
  },
  link(recordId: number): LinkCommand {
    return [4, recordId, 0];
  },
  clear(): ClearCommand {
    return [5, 0, 0];
  },
  set(recordIds: readonly number[]): SetCommand {
    return [6, 0, [...recordIds]];
  },
});
