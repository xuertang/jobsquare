export type MatchState = 'new' | 'approved' | 'dismissed' | 'snoozed';
export type AppState = 'waiting' | 'filling' | 'paused' | 'submitted' | 'needs_manual';

export interface Match {
  id: number;
  posting_id: number;
  score: number | null;
  rationale: string | null;
  score_error: string | null;
  state: MatchState;
  snoozed_until: string | null;
  title: string;
  company: string;
  location: string;
  remote: boolean;
  salary_range: string;
  url: string;
  ats_type: string;
  posted_at: string | null;
  first_seen: string;
  closed: boolean;
  contacts: number;
  application_id: number | null;
  application_state: AppState | null;
}

export interface Answer {
  id: number;
  field_key: string;
  question: string;
  answer: string;
  source: 'profile' | 'bank' | 'llm' | 'manual';
  edited: boolean;
  flagged: boolean;
  confidence: number | null;
  field_type: string;
  category: string;
  status: 'filled' | 'unfilled' | 'failed';
  note: string;
}

export interface Application {
  id: number;
  posting_id: number;
  state: AppState;
  status: string;
  resume_id: number | null;
  resume_variant: string;
  submitted_at: string | null;
  screenshot_path: string | null;
  notes: string;
  manual_reason: string;
  fill_report: { captcha?: boolean; unfilled?: number; fields?: number; multi_step?: boolean };
  title: string;
  company: string;
  location: string;
  url: string;
  apply_url: string;
  ats_type: string;
  score: number | null;
  closed: boolean;
  answers?: Answer[];
  answer_count?: number;
  flagged_count?: number;
  unfilled_count?: number;
  fill_task?: { id: number; state: string } | null;
}

export interface Message {
  id: number;
  contact_id: number;
  posting_id: number | null;
  direction: 'out' | 'in';
  kind: 'initial' | 'followup' | 'reply';
  body: string;
  source: string;
  outcome: string | null;
  drafted_at: string;
  sent_at: string | null;
  contact_name: string;
  contact_company: string;
  profile_url: string;
  posting_title: string | null;
  posting_company: string | null;
  char_cap: number;
  problems: string[];
}

export interface Contact {
  id: number;
  name: string;
  company: string;
  title: string;
  profile_url: string;
  relationship_type: string;
  source: string;
  connected_on: string | null;
  shared_context: string;
  notes: string;
  strength?: number;
  reasons?: string[];
  hint?: string;
  status?: string;
  messages?: Message[];
}

export interface Posting {
  id: number;
  company_id: number;
  company: string;
  title: string;
  location: string;
  remote: boolean;
  department: string;
  salary_range: string;
  description: string | null;
  url: string;
  apply_url: string;
  ats_type: string;
  posted_at: string | null;
  first_seen: string;
  closed: boolean;
}

export interface PostingDetail {
  posting: Posting;
  match: Match | null;
  application: Application | null;
  contacts: Contact[];
  search_links: { label: string; url: string }[];
  duplicate: { id: number; posting_id: number; title: string; state: string } | null;
}

export interface Task {
  id: number;
  kind: string;
  state: string;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
}

export interface Status {
  llm: { available: boolean; model: string };
  scheduler: { enabled: boolean; next_run: string | null };
  worker: { running: boolean };
  counts: {
    matches: Record<string, number>;
    queue: number;
    paused: number;
    submitted: number;
    followups: number;
    contacts: number;
    companies: number;
    companies_attention: number;
  };
  last_daily: Task | null;
  running: Task[];
}

export interface Company {
  id: number;
  name: string;
  ats_type: string;
  board_token: string;
  board_config: Record<string, unknown>;
  aliases: string;
  active: boolean;
  last_fetch_at: string | null;
  last_status: string | null;
  last_error: string | null;
  last_count: number | null;
  open_postings: number;
}

export interface Resume {
  id: number;
  label: string;
  filename: string;
  keywords: string;
  text: string;
  is_default: boolean;
  has_file: boolean;
}

export interface BankEntry {
  id: number;
  question: string;
  answer: string;
  uses: number;
  last_used: string | null;
}

export interface Followup extends Contact {
  posting_id: number | null;
  posting_title: string | null;
  posting_company: string | null;
  last_sent_at: string;
  days_waiting: number;
  draft: Message | null;
}

export interface OutreachBoard {
  companies: {
    company_id: number;
    company: string;
    best_score: number;
    postings: { id: number; title: string; score: number | null; state: string; location: string }[];
    contacts: Contact[];
  }[];
  followups: Followup[];
  log: Message[];
  contact_total: number;
}

export type Profile = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
export type Criteria = { search: Record<string, any>; app: Record<string, any>; levels: string[] }; // eslint-disable-line @typescript-eslint/no-explicit-any
