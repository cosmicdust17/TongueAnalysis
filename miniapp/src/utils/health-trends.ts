import { api, query } from "./request";

export const levels = ["没有", "轻微", "明显", "很明显"] as const;
export type Level = 0 | 1 | 2 | 3;
export interface Checkin {
  date: string;
  level: Level;
  level_name: string;
}
export interface TrackingIdentity {
  id: string;
  symptom_name: string;
  active: boolean;
}
export interface Tracking extends TrackingIdentity {
  today_level: Level | null;
}
export interface Trackings {
  date: string;
  max_active: number;
  active_count: number;
  items: Tracking[];
}
export interface Trend {
  tracking_id: string;
  symptom_name: string;
  items: Checkin[];
}
export interface Suggestion {
  symptom_name: string;
}

const trackings = "/health-trends/trackings";
const analysisPath = "/health-trends/analyses/";
const trackingPath = (id: string) => trackings + "/" + encodeURIComponent(id);

export const getTrackings = () => api<Trackings>(trackings);
export const startTracking = (symptom_name: string) =>
  api<TrackingIdentity>(trackings, "POST", { symptom_name });
export const stopTracking = (id: string) =>
  api<TrackingIdentity>(trackingPath(id) + "/stop", "PUT");
export const saveCheckin = (id: string, level: Level) =>
  api<Checkin>(trackingPath(id) + "/checkins/today", "PUT", { level });
export const getTrend = (id: string, start_date: string, end_date: string) =>
  api<Trend>(trackingPath(id) + "/trend" + query({ start_date, end_date }));
export const getSuggestion = (id: string) =>
  api<{ suggestion: Suggestion | null }>(analysisPath + encodeURIComponent(id) + "/suggestion");
export const dismissSuggestion = (id: string, symptom_name: string) =>
  api(analysisPath + encodeURIComponent(id) + "/dismissal", "PUT", { symptom_name });
