// 本文件由 tech/scripts/export_contracts.py 自动生成，请勿手改。
// 重新生成：python tech/scripts/export_contracts.py
export const SCHEMA_VERSION = "1.0";
export const RULES_VERSION = "1.0";

export type ApiError = {
  code: ErrorCode;
  message: string;
  issues: Issue[];
  request_id: string;
};

export type AssumptionImpact = "low" | "critical";

export type CanvasNote = {
  id: string;
  text: string;
  x: number;
  y: number;
  color?: string | null;
};

export type Coverage = {
  covered_ids: string[];
  uncovered_ids: string[];
};

export type CreatePlanningRunRequest = {
  spec_revision_id: string;
  mode: PlanningMode;
  config: PlanningConfig;
  fixture_id?: string | null;
};

export type CreateProjectRequest = {
  name: string;
};

export type Deliverable = {
  id: string;
  text: string;
};

export type DesignSpecContent = {
  schema_version: "1.0";
  product_name: string;
  background: string;
  goals: string[];
  target_users: string[];
  requirements: Requirement[];
  technical_constraints: string[];
  development_constraints: string[];
  delivery_requirements: string[];
  acceptance_criteria: string[];
  supplemental_text: string;
  confirmed_assumptions: string[];
};

export type ErrorCode = "VALIDATION_FAILED" | "NOT_FOUND" | "REVISION_CONFLICT" | "IDEMPOTENCY_CONFLICT" | "PAYLOAD_TOO_LARGE" | "QUEUE_FULL" | "STORAGE_BUSY" | "RESULT_NOT_READY" | "ORIGIN_FORBIDDEN";

export type ErrorEnvelope = {
  error: ApiError;
};

export type EstimatedEffort = {
  min_hours: number;
  max_hours: number;
  basis: string;
  is_estimate: true;
};

export type ExecutionStage = {
  stage_id: string;
  task_ids: string[];
};

export type ExportBundle = {
  schema_version: "1.0";
  spec_snapshot: DesignSpecContent;
  policy_snapshot: PlanningPolicy | null;
  plan_revision: PlanRevision;
  layout: Layout | null;
};

export type Granularity = "coarse" | "standard" | "fine";

export type Issue = {
  code: IssueCode;
  severity: IssueSeverity;
  path: string;
  message: string;
  task_ids: string[];
  edges: TaskEdge[];
  suggestion: string;
};

export type IssueCode = "SPEC_REQUIRED" | "DUPLICATE_ID" | "MISSING_DEPENDENCY" | "SELF_DEPENDENCY" | "DUPLICATE_DEPENDENCY" | "CYCLE" | "INVALID_STAGE" | "INVALID_ROLE" | "INVALID_CATEGORY" | "STAGE_EDGE_FORBIDDEN" | "MISSING_INPUT" | "INPUT_NOT_DEPENDENCY" | "UNKNOWN_REQUIREMENT" | "REQUIRED_UNCOVERED" | "REQUIRED_CATEGORY" | "UNCONFIRMED_ASSUMPTION" | "CRITICAL_ASSUMPTION" | "POSSIBLE_DUPLICATE" | "ORPHAN" | "POLICY_UNSATISFIABLE" | "SOURCE_MISMATCH";

export type IssueSeverity = "error" | "warning";

export type Layout = {
  plan_revision_id: string;
  revision: number;
  positions: Record<string, Position>;
  notes: CanvasNote[];
  viewport: Viewport;
};

export type LayoutWriteRequest = {
  expected_revision: number;
  positions: Record<string, Position>;
  notes: CanvasNote[];
  viewport: Viewport;
};

export type OrchestrationRequest = {
  spec_revision_id: string;
  policy?: PlanningPolicy | null;
  tasks: Task[];
};

export type OriginMode = "REAL" | "TEST" | "NONE";

export type PlanDerivation = {
  input_hash: string;
  edges: TaskEdge[];
  execution_stages: ExecutionStage[];
  parallel_batches: string[][];
  ordered_task_ids: string[];
  validation_report: ValidationReport;
};

export type PlanRevision = {
  id: string;
  plan_id: string;
  revision: number;
  spec_revision_id: string;
  planning_run_id: string | null;
  parent_revision_id: string | null;
  policy_snapshot: PlanningPolicy | null;
  source: PlanSource;
  origin_mode: OriginMode;
  confirmed_assumption_ids: string[];
  tasks: Task[];
  edges: TaskEdge[];
  execution_stages: ExecutionStage[];
  parallel_batches: string[][];
  ordered_task_ids: string[];
  validation_report: ValidationReport;
  hash: string;
  created_at: string;
};

export type PlanRevisionSummary = {
  id: string;
  plan_id: string;
  revision: number;
  spec_revision_id: string;
  source: PlanSource;
  origin_mode: OriginMode;
  hash: string;
  created_at: string;
};

export type PlanRevisionSummaryPage = {
  items: PlanRevisionSummary[];
  next_cursor: string | null;
};

export type PlanSource = "AI" | "TEST" | "MANUAL";

export type PlanningConfig = {
  model: string;
  granularity: Granularity;
  planning_constraints: string[];
  policy?: PlanningPolicy | null;
};

export type PlanningMode = "REAL" | "TEST";

export type PlanningPolicy = {
  schema_version: "1.0";
  rules_version: "1.0";
  allowed_stages: string[] | null;
  allowed_roles: string[] | null;
  allowed_categories: string[] | null;
  allowed_stage_edges: StageEdge[] | null;
  required_categories: string[];
};

export type PlanningRun = {
  id: string;
  spec_revision_id: string;
  mode: PlanningMode;
  status: PlanningStatus;
  config_snapshot: PlanningConfig;
  attempt_count: number;
  fixture_id?: string | null;
  usage?: TokenUsage | null;
  error?: RunError | null;
  proposal?: TaskProposal | null;
  validation_report?: ValidationReport | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type PlanningRunCreated = {
  id: string;
  status: "QUEUED";
  poll_url: string;
};

export type PlanningRunTasksResponse = {
  tasks: Task[];
};

export type PlanningStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "NEEDS_INPUT" | "FAILED";

export type Position = {
  x: number;
  y: number;
};

export type Project = {
  id: string;
  name: string;
  archived_at: string | null;
  created_at: string;
};

export type ProjectPage = {
  items: Project[];
  next_cursor: string | null;
};

export type Requirement = {
  id: string;
  kind: RequirementKind;
  text: string;
  priority: RequirementPriority;
  acceptance_criteria: string[];
};

export type RequirementKind = "functional" | "nonfunctional";

export type RequirementPriority = "must" | "should" | "could";

export type RunError = {
  code: RunFailureCode;
  message: string;
  provider_request_id?: string | null;
  retryable: boolean;
};

export type RunFailureCode = "MODEL_SCHEMA" | "MODEL_EMPTY" | "MODEL_TRUNCATED" | "MODEL_BUDGET" | "MODEL_TIMEOUT" | "MODEL_AUTH" | "MODEL_RATE_LIMITED" | "MODEL_NETWORK" | "PROCESS_INTERRUPTED" | "POLICY_UNSATISFIABLE" | "INTERNAL_ERROR";

export type SavePlanRequest = {
  spec_revision_id: string;
  planning_run_id?: string | null;
  policy?: PlanningPolicy | null;
  tasks: Task[];
  confirmed_assumption_ids: string[];
  layout?: Layout | null;
};

export type SavePlanResponse = {
  plan_id: string;
  revision: PlanRevision;
};

export type SavePlanRevisionRequest = {
  spec_revision_id: string;
  planning_run_id?: string | null;
  policy?: PlanningPolicy | null;
  tasks: Task[];
  confirmed_assumption_ids: string[];
  layout?: Layout | null;
  expected_revision: number;
  parent_revision_id?: string | null;
};

export type SpecInput = {
  kind: "spec";
  requirement_id: string;
};

export type SpecRevision = {
  id: string;
  spec_id: string;
  revision: number;
  content: DesignSpecContent;
  hash: string;
  created_at: string;
};

export type SpecRevisionPage = {
  items: SpecRevision[];
  next_cursor: string | null;
};

export type SpecRevisionWriteRequest = {
  expected_revision: number;
  content: DesignSpecContent;
};

export type SpecValidationRequest = {
  content: DesignSpecContent;
};

export type StageEdge = {
  from: string;
  to: string;
};

export type Task = {
  task_id: string;
  name: string;
  description: string;
  category: string;
  stage: string;
  priority: TaskPriority;
  assigned_role: string;
  dependencies: string[];
  inputs: (SpecInput | TaskInput)[];
  deliverables: Deliverable[];
  acceptance_criteria: string[];
  source_requirement_ids: string[];
  rationale: string;
  assumptions: TaskAssumption[];
  estimated_effort: EstimatedEffort | null;
};

export type TaskAssumption = {
  id: string;
  text: string;
  impact: AssumptionImpact;
};

export type TaskEdge = {
  source: string;
  target: string;
};

export type TaskInput = {
  kind: "task";
  task_id: string;
  deliverable_id: string;
};

export type TaskPriority = "high" | "medium" | "low";

export type TaskProposal = {
  schema_version: "1.0";
  tasks: Task[];
  blocking_questions: string[];
};

export type TokenUsage = {
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
};

export type ValidationReport = {
  valid: boolean;
  errors: Issue[];
  warnings: Issue[];
  coverage: Coverage;
  rules_version: "1.0";
  input_hash: string;
};

export type Viewport = {
  x: number;
  y: number;
  zoom: number;
};

export type WorkflowValidationRequest = {
  spec_revision_id: string;
  policy?: PlanningPolicy | null;
  tasks: Task[];
};
