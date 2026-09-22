import {
  Cmd,
  OdooClient,
  formatOdooDate,
  type OdooWorkerBindings,
} from "../../src/index.js";

export default {
  fetch(_request: Request, env: OdooWorkerBindings): Response {
    const client = OdooClient.fromBindings(env, { protocol: "json2" });
    return Response.json({
      url: client.projects.url(7),
      command: Cmd.set([2, 3]),
      date: formatOdooDate(new Date("2026-09-20T23:30:00Z")),
    });
  },
};
