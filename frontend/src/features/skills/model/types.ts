export interface InstalledSkill {
  id: string;
  version?: string;
  kind?: 'system' | 'community' | 'user';
  publisher?: { id: string; name: string; verified: boolean };
  required_plan?: 'guest' | 'free' | 'plus' | 'pro';
  package_path?: string;
  order: number;
  default_enabled: boolean;
  locked: boolean;
  capabilities: string[];
  category?: string;
  requires: string[];
  recommends: string[];
  conflicts?: string[];
  external: boolean;
  configured: boolean;
  connect_url: string;
  credential?: {
    kind: 'token';
    env_key: string;
    ttl_seconds: number;
    help_url: string;
    instructions: Record<string, string>;
  };
  icon: string;
  name: Record<string, string>;
  description: Record<string, string>;
  component_actions?: string[];
  eligible?: boolean;
  installed?: boolean;
  enabled?: boolean;
  eligibility_reason?: 'login_required' | 'membership_required' | '';
}

export interface SkillDependencyGraph {
  nodes: Array<{
    id: string;
    version: string;
    kind: NonNullable<InstalledSkill['kind']>;
    locked: boolean;
    required_plan: InstalledSkill['required_plan'];
    name: Record<string, string>;
  }>;
  edges: Array<{ from: string; to: string; type: 'requires' | 'recommends' | 'conflicts' }>;
}

export interface SkillComponentApi {
  version: string;
  actions: Array<{
    id: string;
    category?: string;
    name?: Record<string, string>;
    permission: string;
    description: string;
    description_i18n?: Record<string, string>;
    input: Record<string, string>;
    required?: string[];
  }>;
  security: {
    identity_source: string;
    model_is_authorization_boundary: boolean;
    tenant_prefix_required: boolean;
    raw_chain_of_thought_allowed: boolean;
  };
}

export interface SkillConnectionState {
  configured: boolean;
  connected_at: number;
  expires_at: number;
}

export interface SkillUploadRecord {
  id: string;
  name: string;
  storage_key: string;
  status: 'stored' | 'pending_review' | 'approved' | 'rejected';
  visibility?: 'private' | 'marketplace';
  review_status?: 'not_submitted' | 'pending_review' | 'approved' | 'rejected';
  review_available: boolean;
  source_type?: 'zip' | 'declarative';
  source_skill_id?: string;
  description?: string;
  instructions?: string;
  size: number;
  installed_at?: number;
  submitted_at?: number;
  review_requested_at?: number;
}

export interface UserSkillRecord {
  id: string;
  name: string;
  description: string;
  instructions: string;
  source_type: 'file' | 'folder' | 'package' | 'paste' | 'url';
  source_url: string;
  enabled: boolean;
  installed_at: number;
  updated_at: number;
  review_status: 'not_submitted';
}

export interface SkillMarketplaceState {
  skills: InstalledSkill[];
  preferences: Record<string, boolean>;
  connections: Record<string, SkillConnectionState>;
  user_skills: UserSkillRecord[];
  entitlements: {
    plan: 'guest' | 'free' | 'plus' | 'pro';
    limits: Record<string, string | number>;
    payment_available: boolean;
  };
  dependency_graph: SkillDependencyGraph;
  component_api: SkillComponentApi;
  identity: {
    user_id: string;
    subject_id: string;
    tenant_id: string;
    display_name: string;
    avatar_url: string;
    auth_type: 'guest' | 'wechat' | 'cloudbase';
    membership: 'guest' | 'free' | 'plus' | 'pro';
    roles: string[];
  };
}
