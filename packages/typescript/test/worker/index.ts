import { Cmd, OdooClient, formatOdooDate } from "../../src/index.js";

export default {
  fetch(): Response {
    const client = new OdooClient({
      url: "https://odoo.example.test/",
      database: "fixture",
      username: "worker",
      password: "unused",
    });
    return Response.json({
      url: client.projects.url(7),
      command: Cmd.set([2, 3]),
      date: formatOdooDate(new Date("2026-09-20T23:30:00Z")),
    });
  },
};
