export type Role = "user" | "knowledge_admin" | "ops_admin";
export interface User {
  id: string;
  username: string;
  nickname: string;
  role: Role;
  active: boolean;
  has_password: boolean;
  profile: { gender?: string; age?: number | null };
  created_at: string;
}
export interface Session {
  access_token: string;
  user: User;
}
export interface Uploaded {
  id: string;
  name: string;
  url: string;
  size: number;
}
export interface Report {
  id: string;
  analysis_id: string;
  image_id: string;
  title: string;
  created_at: string;
  is_demo: boolean;
  content: {
    presentation: {
      title: string; identity: {user_id:string;age:string|number;gender:string;report_date:string};
      symptoms_text:string;duration:string;analysis:string;brief:string;
      advice_items:{category:string;text:string}[];
      evidence:{number:number;explanation:string;quote:string;reference:string}[];
      notice:string;
    };
    annotations?: AnnotationSnapshot;
  };
}
export interface DetectionBox {
  class_name: string;
  class_id: number;
  name: string;
  description: string;
  color: string;
  score: number;
  xyxy: [number, number, number, number];
}
export interface AnnotationSnapshot {
  available: boolean;
  image_width: number;
  image_height: number;
  detections: DetectionBox[];
}
export interface Analysis {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  error: string;
  report_id: string | null;
}
export interface Evidence {
  chunk_id?: string;
  location?: {
    chapter: string | null;
    pdf_page: number | null;
    printed_page: string | number | null;
    paragraph: string | number | null;
    block_on_page?: number;
  };
  entity_id: string;
  title: string;
  text: string;
  kind: string;
  source_title: string;
  citation: string;
  is_demo: boolean;
  score: number;
  path: { id: string; kind: string; citation: string; source_title: string }[];
}
export interface Source {
  id: string;
  title: string;
  citation: string;
  file_id?: string;
  file_type?: string;
  file_name?: string;
  is_demo: boolean;
  updated_at: string;
}
export type Status = "draft" | "pending" | "published";
export interface Entity {
  id: string;
  name: string;
  kind: string;
  text: string;
  source_id: string;
  source_title?: string;
  aliases: string[];
  status: Status;
  is_demo: boolean;
  updated_at: string;
}
export interface Relation {
  id: string;
  source: string;
  target: string;
  kind: string;
  source_id: string;
  status: Status;
  is_demo: boolean;
  updated_at: string;
}
export interface Graph {
  nodes: Entity[];
  relations: Relation[];
  sources: Source[];
  truncated: boolean;
}
export interface Log {
  id: string;
  action: string;
  status: string;
  category: string;
  actor_name: string;
  created_at: string;
}
export interface Alert {
  id: string;
  service: string;
  message: string;
  resolved: boolean;
  created_at: string;
}
export interface Service {
  key: string;
  name: string;
  status: string;
  message: string;
}
export interface Overview {
  status: string;
  updated_at: string;
  today_analyses: number;
  report_count: number;
  pending_alerts: number;
  services: Service[];
  recent_logs: Log[];
}
export interface KnowledgeOverview {
  entity_count: number;
  relation_count: number;
  source_count: number;
  pending_count: number;
  published_count: number;
  has_demo_data: boolean;
}
