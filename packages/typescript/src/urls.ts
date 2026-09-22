export type RecordUrlDialect = "jsonrpc" | "json2";

/** Build the canonical Odoo web-client URL for a selected transport dialect. */
export function buildRecordUrl(
  baseUrl: string,
  model: string,
  recordId: number,
  dialect: RecordUrlDialect,
): string {
  const base = baseUrl.replace(/\/+$/u, "");
  const modelPath = model.includes(".") ? model : `m-${model}`;
  return dialect === "json2"
    ? `${base}/odoo/${modelPath}/${recordId}`
    : `${base}/web#id=${recordId}&model=${model}&view_type=form`;
}
