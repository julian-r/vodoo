export { OdooClient, type OdooClientOptions } from "./client.js";
export type {
  OdooClientApi,
  SearchOptions,
  SearchReadOptions,
} from "./client-api.js";
export { decodeBase64, encodeBase64, type BinaryInput } from "./binary.js";
export {
  Cmd,
  type ClearCommand,
  type CreateCommand,
  type DeleteCommand,
  type LinkCommand,
  type OdooCommand,
  type SetCommand,
  type UnlinkCommand,
  type UpdateCommand,
} from "./commands.js";
export {
  HTML,
  Markdown,
  markdownToHtml,
  richTextToHtml,
  type RichText,
} from "./content.js";
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
  RecordOperationError,
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
  AccountMoveNamespace,
  buildAccountMoveDomain,
  type AccountMoveDomainOptions,
  type AccountMoveRecord,
} from "./namespaces/account-moves.js";
export {
  ActivityNamespace,
  buildActivityDomain,
  type ActivityDomainOptions,
  type ActivityRecord,
} from "./namespaces/activities.js";
export {
  CRMNamespace,
  DEFAULT_STALE_THRESHOLDS,
  buildPipelineSummary,
  computeHealthFlags,
  type CreateCRMOptions,
  type CRMRecord,
  type CRMStage,
  type HealthFlag,
  type PipelineDeal,
  type PipelineStageSummary,
  type PipelineSummary,
  type StaleThresholds,
} from "./namespaces/crm.js";
export {
  DocumentNamespace,
  orderFolderTree,
  safeDocumentFilename,
  type DocumentFolder,
  type DocumentRecord,
  type DocumentUploadOptions,
  type DownloadedDocument,
  type FolderListOptions,
} from "./namespaces/documents.js";
export {
  type AttachmentData,
  type AttachmentOptions,
  type ListOptions,
  type MessageOptions,
} from "./namespaces/domain.js";
export { GenericNamespace } from "./namespaces/generic.js";
export {
  HelpdeskNamespace,
  type CreateTicketOptions,
  type HelpdeskRecord,
} from "./namespaces/helpdesk.js";
export {
  KnowledgeNamespace,
  type CreateArticleOptions,
  type KnowledgeRecord,
} from "./namespaces/knowledge.js";
export {
  ProjectNamespace,
  type MilestoneTask,
  type ProjectMilestone,
  type ProjectRecord,
  type ProjectStage,
} from "./namespaces/projects.js";
export {
  GROUP_DEFINITIONS,
  SecurityNamespace,
  type AccessDefinition,
  type CreatedUser,
  type CreateUserOptions,
  type GroupDefinition,
  type GroupResult,
  type RuleDefinition,
} from "./namespaces/security.js";
export {
  TaskNamespace,
  type CreateTaskOptions,
  type TaskRecord,
} from "./namespaces/tasks.js";
export {
  TIMESHEET_MODEL,
  TIMER_TIMER_DOMAIN,
  TIMER_TIMER_FIELDS,
  TimerHandle,
  TimerNamespace,
  TimerSource,
  TimerState,
  Timesheet,
  buildRunningTimer,
  mergeRunningTimers,
  parseTimesheet,
  type TimerListOptions,
  type TimerSourceKind,
  type TimesheetObject,
} from "./namespaces/timer.js";
export {
  JSON2Transport,
  LegacyTransport,
  OdooTransport,
  buildJSON2Body,
  isRetryableMethod,
  parseJSON2Response,
  parseNameSearch,
  retryDelayMs,
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
