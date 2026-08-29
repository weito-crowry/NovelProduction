export type ProjectStatus = "active" | "archived";
export type MetadataState = "ok" | "missing" | "invalid";
export type ProjectHealth = "ok" | "degraded";

export interface ProjectSummary {
  project_id: string;
  status: ProjectStatus;
  metadata_state: MetadataState;
  working_title: string | null;
  created_at: string | null;
  updated_at: string | null;
  health: ProjectHealth;
}

export interface ProjectListResponse {
  projects: ProjectSummary[];
}

export interface WorkRecord {
  id: number;
  slug: string;
  working_title: string;
  genre: string;
  premise: string;
  themes_json: string;
  description: string;
  production_status: string;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface DashboardView {
  work: WorkRecord;
  chapter_count: number;
  episode_count: number;
  scene_count: number;
}

export type ProductionStatus =
  | "planned"
  | "outlined"
  | "drafting"
  | "revising"
  | "final";
export type CanonStatus = "idea" | "draft" | "canon" | "deprecated";
export type EpisodeReferenceType =
  | "character"
  | "world_fact"
  | "timeline_event"
  | "information";

export interface ChapterRecord {
  id: number;
  work_id: number;
  position: number;
  title: string;
  summary: string;
  purpose: string;
  canon_status: string;
  production_status: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface EpisodeRecord {
  id: number;
  work_id: number;
  chapter_id: number;
  position: number;
  title: string;
  summary: string;
  purpose: string;
  foreshadowing_notes_json: string;
  canon_status: string;
  production_status: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SceneRecord {
  id: number;
  work_id: number;
  episode_id: number;
  position: number;
  title: string;
  summary: string;
  purpose: string;
  canon_status: string;
  production_status: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface EpisodeReferenceRecord {
  id: number;
  work_id: number;
  episode_id: number;
  reference_type: string;
  target_id: number;
  role: string | null;
  created_at: string;
}

export interface SafeCharacterProfile {
  id: number;
  character_key: string;
  display_name: string;
  entity_type: string;
  description: string;
  birth_date: string | null;
  physical_description: string;
  occupation: string;
  core_beliefs: string;
  goals: string;
  fears: string;
  personality: string;
  speech_style: string;
  ai_attitude: string;
  genetic_modification_attitude: string;
  canon_status: string;
}

export interface OutlineParticipant {
  profile: SafeCharacterProfile;
  role: string;
}

export interface SafeWorldFact {
  id: number;
  topic_key: string;
  category: string;
  title: string;
  statement: string;
  valid_from: string | null;
  valid_to: string | null;
  canon_status: string;
  importance: number;
}

export interface SafeTimelineEvent {
  id: number;
  event_key: string;
  time_start: string | null;
  time_end: string | null;
  date_precision: string;
  date_display: string;
  title: string;
  description: string;
  category: string;
  location_world_fact_id: number | null;
  cause_summary: string;
  consequence_summary: string;
  canon_status: string;
  importance: number;
}

export interface SafeInformationItem {
  id: number;
  statement: string;
  truth_status: string;
  canon_status: string;
  importance: number;
}

export interface RevealBoundary {
  episode_id: number;
  chapter_position: number;
  episode_position: number;
}

export interface ProtectedInformationGuard {
  information_item_id: number;
  reason: string;
  guard_text: string;
  reveal_boundary: RevealBoundary | null;
  character_id: number | null;
  knowledge_state: string | null;
}

export interface OutlineReferences {
  world_facts: SafeWorldFact[];
  timeline_events: SafeTimelineEvent[];
  information: SafeInformationItem[];
}

export interface EpisodeOutline {
  episode: EpisodeRecord;
  scenes: SceneRecord[];
  participants: OutlineParticipant[];
  references: OutlineReferences;
  protected_information_guards: ProtectedInformationGuard[];
}

export interface EffectiveCharacterState {
  state_id: number;
  source_episode_id: number;
  physical_state: string;
  emotional_state: string;
  beliefs: unknown;
  location_world_fact_id: number | null;
}

export interface EffectiveRelationship {
  relationship_id: number;
  related_character_id: number;
  relationship_type: string;
  description: string;
  canon_status: string;
}

export interface ParticipantKnownInformation {
  information_item_id: number;
  knowledge_state: string;
  source_episode_id: number;
  statement: string | null;
  truth_status: string | null;
  canon_status: string;
}

export interface ContextParticipant {
  profile: SafeCharacterProfile;
  effective_state: EffectiveCharacterState | null;
  effective_relationships: EffectiveRelationship[];
  known_information: ParticipantKnownInformation[];
}

export interface ReaderContext {
  known_before_episode: SafeInformationItem[];
  reveal_this_episode: SafeInformationItem[];
}

export interface PreviousEpisodeSummary {
  episode_id: number;
  chapter_position: number;
  episode_position: number;
  title: string;
  summary: string;
}

export interface RecentContext {
  previous_episode_summaries: PreviousEpisodeSummary[];
  previous_draft_tail: string;
}

export interface EpisodeContext {
  episode: EpisodeRecord;
  scenes: SceneRecord[];
  participants: ContextParticipant[];
  world_facts: SafeWorldFact[];
  timeline_events: SafeTimelineEvent[];
  reader_context: ReaderContext;
  protected_information_guards: ProtectedInformationGuard[];
  recent_context: RecentContext;
  foreshadowing_notes: unknown[];
  context_meta: Record<string, unknown>;
}

export interface DraftRecord {
  id: number;
  work_id: number;
  episode_id: number;
  revision: number;
  parent_draft_id: number | null;
  body: string;
  source_agent: string | null;
  change_summary: string;
  content_hash: string;
  created_at: string;
}

export interface DraftMetadata {
  id: number;
  episode_id: number;
  revision: number;
  parent_draft_id: number | null;
  source_agent: string | null;
  change_summary: string;
  content_hash: string;
  body_chars: number;
  created_at: string;
}

export interface OutlineEpisodeView {
  episode: EpisodeRecord;
  scenes: SceneRecord[];
}

export interface OutlineChapterView {
  chapter: ChapterRecord;
  episodes: OutlineEpisodeView[];
}

export interface OutlineView {
  chapters: OutlineChapterView[];
}

export interface EpisodeView {
  episode: EpisodeRecord;
  scenes: SceneRecord[];
  episode_references: EpisodeReferenceRecord[];
  outline: EpisodeOutline;
  context: EpisodeContext;
  latest_draft: DraftRecord | null;
  recent_draft_history: DraftMetadata[];
}

export interface ChapterCreate {
  title: string;
  summary?: string;
  purpose?: string;
  production_status?: ProductionStatus;
  canon_status?: CanonStatus;
}

export interface ChapterUpdate {
  expected_version: number;
  title?: string;
  summary?: string;
  purpose?: string;
  production_status?: ProductionStatus;
  canon_status?: CanonStatus;
  reason?: string;
}

export interface EpisodeCreate {
  title: string;
  summary?: string;
  purpose?: string;
  foreshadowing_notes?: unknown;
  production_status?: ProductionStatus;
  canon_status?: CanonStatus;
}

export interface EpisodeUpdate {
  expected_version: number;
  title?: string;
  summary?: string;
  purpose?: string;
  foreshadowing_notes?: unknown;
  production_status?: ProductionStatus;
  canon_status?: CanonStatus;
  reason?: string;
}

export interface SceneCreate {
  title: string;
  summary?: string;
  purpose?: string;
  production_status?: ProductionStatus;
  canon_status?: CanonStatus;
}

export interface SceneUpdate {
  expected_version: number;
  title?: string;
  summary?: string;
  purpose?: string;
  production_status?: ProductionStatus;
  canon_status?: CanonStatus;
  reason?: string;
}

export interface ReorderInput {
  target_position: number;
  expected_version: number;
}

export interface EpisodeReferenceAdd {
  reference_type: EpisodeReferenceType;
  target_id: number;
  role?: string;
}

export interface WorkUpdate {
  working_title: string;
  expected_version: number;
  genre?: string;
  premise?: string;
  themes_json?: unknown;
  description?: string;
  production_status?: string;
}
