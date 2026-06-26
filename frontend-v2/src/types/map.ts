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

export interface CognitionPayload {
  city?: { lon: number; lat: number; zoom: number }
  intersection: CognitionIntersection
  arms: CognitionArm[]
  links?: IntersectionLink[]
  direction_groups?: DirectionGroup[]
  metrics_by_arm?: ArmMetric[]
  available_directions?: string[]
}

export interface MapSceneMarker {
  id: string
  lon: number
  lat: number
  kind?: 'chip' | 'metric' | 'alert' | 'rule' | 'suggestion' | 'imbalance' | 'evidence' | 'link-info' | 'timing' | 'corridor'
  variant?: string
  title?: string
  subtitle?: string
  value?: string
  severity?: 'high' | 'medium' | 'low' | 'unknown'
  dir?: string
  link_id?: string
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
  /** map_scene fields */
  center?: [number, number]
  zoom?: number
  highlight_dirs?: string[]
  pulse_link_ids?: string[]
  dim_other_links?: boolean
  markers?: MapSceneMarker[]
  hud?: MapSceneHud | null
  focus?: { lon: number; lat: number } | null
  highlight_turn?: { dir: string; turn: string; label?: string; saturation?: number | null }
  suggestion?: Record<string, unknown>
}

export interface NarrationCard {
  id: string
  phase: string
  title: string
  text: string
  visible: boolean
}
