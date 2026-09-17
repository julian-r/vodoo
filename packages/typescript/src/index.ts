export { OdooClient, type OdooClientOptions } from "./client.js";
export type {
  OdooClientApi,
  SearchOptions,
  SearchReadOptions,
} from "./client-api.js";
export {
  AuthenticationError,
  ConfigurationError,
  HttpStatusError,
  NetworkError,
  OdooAccessDeniedError,
  OdooAccessError,
  OdooMissingError,
  OdooUserError,
  OdooValidationError,
  RecordNotFoundError,
  TransportError,
  VodooError,
} from "./errors.js";
export {
  formatOdooDate,
  formatOdooDateTime,
  parseOdooDate,
  parseOdooDateTime,
} from "./dates.js";
export {
  ProjectNamespace,
  type MilestoneTask,
  type ProjectMilestone,
  type ProjectRecord,
  type ProjectStage,
} from "./namespaces/projects.js";
export {
  JSON2Transport,
  LegacyTransport,
  OdooTransport,
  buildJSON2Body,
  parseJSON2Response,
  parseNameSearch,
  type OdooTransportApi,
  type TransportOptions,
} from "./transport.js";
export type {
  Domain,
  DomainTerm,
  FetchLike,
  JsonObject,
  JsonPrimitive,
  JsonValue,
  NameSearchResult,
  OdooConfig,
  OdooRecord,
  RetryConfig,
  Sleep,
} from "./types.js";
export { DEFAULT_RETRY } from "./types.js";
