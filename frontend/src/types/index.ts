/**
 * Definições de tipos e interfaces TypeScript para o ecossistema ThothCVs AI Frontend.
 *
 * Mapeia contratos estritos com o backend FastAPI e suporta acessibilidade WCAG 2.1 AA.
 */

export type ApplicationStatus =
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn";

export type WorkModel = "remote" | "hybrid" | "on-site";

export interface ApplicationStage {
  id: string;
  application_id: string;
  stage_name: string;
  status: "pending" | "scheduled" | "completed" | "skipped";
  scheduled_at?: string | null;
  completed_at?: string | null;
  feedback_notes?: string | null;
  order_index: number;
  created_at: string;
}

export interface ApplicationContact {
  id: string;
  application_id: string;
  name: string;
  full_name: string;
  role: string;
  role_type: string;
  email?: string | null;
  phone?: string | null;
  linkedin_url?: string | null;
  context_notes?: string | null;
  created_at: string;
}

export interface ApplicationNote {
  id: string;
  application_id: string;
  content: string;
  note_type: string;
  created_at: string;
}

export interface ApplicationItem {
  id: string;
  company_name: string;
  job_title: string;
  status: ApplicationStatus;
  work_model: WorkModel;
  applied_at: string;
  last_activity_at: string;
  needs_follow_up: boolean;
  location?: string | null;
  salary_range?: string | null;
}

export interface ApplicationDetail extends ApplicationItem {
  job_description: string;
  job_url?: string | null;
  next_follow_up_date?: string | null;
  reminder_active: boolean;
  stages: ApplicationStage[];
  contacts: ApplicationContact[];
  notes: ApplicationNote[];
}

export interface ApplicationAnalyticsMetrics {
  total_applications: number;
  status_distribution: Record<string, number>;
  stale_applications_count: number;
  interview_conversion_rate: number;
  offer_conversion_rate: number;
  average_match_score: number;
}

export interface MatchAnalysisItem {
  requirement: string;
  status: "matched" | "partial" | "missing";
  evidence: string;
  similarity_score: number;
}

export interface MatchPreviewResponse {
  match_percentage: number;
  mandatory_matches: MatchAnalysisItem[];
  desirable_matches: MatchAnalysisItem[];
  missing_mandatory: string[];
  missing_desirable: string[];
  suggested_keywords: string[];
}

export interface ResumeGenerateResponse {
  resume_id: string;
  application_id: string;
  version_number: number;
  match_percentage: number;
  match_analysis: Record<string, unknown>;
  structured_content: {
    header: {
      full_name: string;
      target_title?: string;
      email?: string;
      phone?: string;
      location?: string;
      links?: Record<string, string>;
    };
    professional_summary?: string;
    selected_experiences?: Array<{
      company_name: string;
      position_title: string;
      start_date: string;
      end_date?: string | null;
      is_current?: boolean;
      bullet_points?: string[];
      tech_stack?: string[];
    }>;
    skills_highlighted?: string[];
    education?: Array<{
      degree: string;
      institution: string;
      start_date?: string;
      end_date?: string;
    }>;
    certifications?: Array<{
      name: string;
      issuer?: string;
      issue_date?: string;
    }>;
    languages?: Array<{
      language: string;
      proficiency?: string;
    }>;
  };
}

export interface NotificationItem {
  id: string;
  application_id?: string | null;
  notification_type: string;
  title: string;
  message: string;
  is_read: boolean;
  scheduled_for: string;
  sent_at?: string | null;
  created_at: string;
}
