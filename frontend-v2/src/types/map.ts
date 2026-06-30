export interface IntersectionLink {
  link_id: string
  link_role: string
  dir4_label?: string
  dir8_label?: string
  road_name?: string
  lane_num?: number
  path: Array<[number, number]>
}

export interface CognitionIntersection {
  inter_id: string
  name: string
  lon: number
  lat: number
  zoom?: number
  arm_count?: number
  total_lanes?: number
}

export interface CognitionArm {
  link_id: string
  dir4_label: string
  dir8_label?: string
  dir_label?: string
  lane_num: number
  lane_info?: string
  turn_move?: string
  clockwise_seq?: number
  entrance_angle?: number | null
  lanes?: Array<{ lane_id: string; lane_seq: number; turn_move: string }>
}

export interface DirectionGroup {
  group: string
  saturation_avg?: number
  saturation_max?: number
  level?: string
  arm_labels?: string[]
}

export interface ArmMetric {
  link_id: string
  dir4_label: string
  saturation?: number | null
  level?: string
}

/** 转向级饱和度（与 granularity.by_turn / cognition.metrics_by_turn 对齐） */
export interface TurnMetric {
  label: string
  dir4_label: string
  turn?: string
  dir8_code?: number | null
  turn_dir_no?: number | null
  turn_saturation?: number | null
  green_utilization?: number | null
  level?: string
}

export interface CognitionPayload {
  city?: { lon: number; lat: number; zoom: number }
  intersection: CognitionIntersection
  arms: CognitionArm[]
  links?: IntersectionLink[]
  direction_groups?: DirectionGroup[]
  metrics_by_arm?: ArmMetric[]
  metrics_by_turn?: TurnMetric[]
  available_directions?: string[]
}

export interface MapSceneMarker {
  id: string
  lon: number
  lat: number
  kind?: 'chip' | 'metric' | 'alert' | 'rule' | 'suggestion' | 'imbalance' | 'evidence' | 'link-info' | 'timing' | 'corridor' | 'corridor-scan'
  variant?: string
  title?: string
  subtitle?: string
  value?: string
  severity?: 'high' | 'medium' | 'low' | 'unknown'
  dir?: string
  link_id?: string
  inter_id?: string
  inter_name?: string
  rank?: number | null
  selected?: boolean
  has_data?: boolean
  metrics?: Record<string, unknown>
}

export interface MapSceneHud {
  title: string
  icon?: string
  metrics: Array<{ label: string; value: string; severity?: string }>
}

export interface MapScenePayload {
  action: 'map_scene'
  phase: string
  center?: [number, number]
  zoom?: number
  highlight_dirs?: string[]
  pulse_link_ids?: string[]
  dim_other_links?: boolean
  markers?: MapSceneMarker[]
  hud?: MapSceneHud | null
  focus?: { lon: number; lat: number } | null
}

export interface MapActionEvent {
  action: string
  phase?: string
  locked?: boolean
  city?: { lon: number; lat: number; zoom: number }
  intersection?: CognitionIntersection
  arms?: CognitionArm[]
  links?: IntersectionLink[]
  direction_groups?: DirectionGroup[]
  metrics_by_arm?: ArmMetric[]
  metrics_by_turn?: TurnMetric[]
  title?: string
  text?: string
  index?: number
  total?: number
  message?: string
  action_type?: string
  show_metrics?: boolean
  fields?: Array<{ key: string; label: string; value: string }>
  highlight_groups?: string[]
  highlightDir?: string | null
  final?: boolean
  evaluation?: Record<string, unknown>
  traffic_flow?: Record<string, unknown>
  metrics?: Record<string, unknown>
  /** map_scene fields */
  center?: [number, number]
  zoom?: number
  highlight_dirs?: string[]
  pulse_link_ids?: string[]
  dim_other_links?: boolean
  focus_groups?: string[]
  protected_groups?: string[]
  direction_roles?: Array<{ group: string; role: string; saturation?: number | null }>
  axis_roads?: Record<string, string>
  speakable?: string | null
  step_summary?: string
  focus_step_index?: number
  markers?: MapSceneMarker[]
  hud?: MapSceneHud | null
  focus?: { lon: number; lat: number } | null
  highlight_turn?: { dir: string; turn: string; label?: string; saturation?: number | null }
  source_center?: { lon: number; lat: number } | null
  /** highlight_flow_sources：按进口道沿路展示 */
  entry_traces?: Array<{
    entry?: string
    dir8_code?: number
    upstream_inter_id?: string
    name?: string
    narrative?: string
    lon?: number
    lat?: number
    dominant_turn?: string
    vehicles_of_100?: number
    movements?: Array<{
      turn: string
      vehicles_of_100: number
      feed_direction?: string
    }>
    path?: Array<[number, number]>
    dominant?: boolean
  }>
  sources?: Array<{
    inter_id: string
    name: string
    movement: string
    coverage?: number | null
    lon: number
    lat: number
    dominant?: boolean
  }>
  suggestion?: Record<string, unknown>
  focus_inter_id?: string
  intersections?: Array<Record<string, unknown>>
  top3_inter_ids?: string[]
  time_period?: { label?: string; name?: string }
  corridor?: {
    line_id?: string
    line_name?: string
    bounds?: { sw: [number, number]; ne: [number, number] }
    polyline?: Array<[number, number]>
    line_paths?: Array<{ link_id?: string; seq_no?: number; path: Array<[number, number]> }>
    envelope_style?: string
  }
  camera?: { center: [number, number]; zoom: number }
}

export interface NarrationCard {
  id: string
  phase: string
  title: string
  text: string
  visible: boolean
}
