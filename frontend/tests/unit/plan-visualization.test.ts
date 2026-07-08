import { describe, expect, it } from 'vitest'
import type { DirectionIntensity, PhaseStageTiming, StageMovement } from '@/api/types'
import {
  directionIntensityRows,
  flowKeysFromStage,
  flowKeysFromStageMovements,
  isRightTurnIntensityItem,
} from '@/viz/planVisualization'

describe('plan visualization helpers', () => {
  it('parses Chinese phase stage names into reference canvas flow keys', () => {
    const stage = {
      phase_stage_id: 'S1',
      phase_stage_name: '西直、东左',
      green_time_s: 36,
      yellow_time_s: 3,
      all_red_time_s: 2,
    } as PhaseStageTiming

    expect(flowKeysFromStage(stage)).toEqual(['6_1', '2_2'])
  })

  it('normalizes movement evidence from dir8No and turnDirNo', () => {
    const movements: StageMovement[] = [
      { label: '西直', dir8No: 6, turnDirNo: 2 },
      { label: '东左', dir8No: 2, turnDirNo: 1 },
      { label: '南右', dir8No: 4, turnDirNo: 3 },
      { label: '北行人', dir8No: 0, turnDirNo: 5 },
    ]

    expect(flowKeysFromStageMovements(movements)).toEqual(['6_1', '2_2', '4_3', '0_5'])
  })

  it('prefers structured movement evidence over repeated stage names', () => {
    const stage = {
      phase_stage_id: 'S4',
      phase_stage_name: '北直、南直',
      green_time_s: 19,
      yellow_time_s: 3,
      all_red_time_s: 2,
      movements: [{ label: '北直', dir8No: 0, turnDirNo: 2 }],
    } as PhaseStageTiming

    expect(flowKeysFromStage(stage)).toEqual(['0_1'])
  })

  it('parses optimizer movement keys with engine turnDirNo semantics', () => {
    const movements: StageMovement[] = [
      { movement_key: 'd0_t2', label: '北进口直行' },
      { movement_key: 'd4_t3', label: '南进口右转' },
      { movement_key: 'd2_t0', label: '东进口掉头' },
    ]

    expect(flowKeysFromStageMovements(movements)).toEqual(['0_1', '4_3', '2_4'])
  })

  it('parses pedestrian crosswalk labels from stage names', () => {
    const stage = {
      phase_stage_id: 'P1',
      phase_stage_name: '北人行道、东人行横道',
      green_time_s: 20,
      yellow_time_s: 3,
      all_red_time_s: 2,
    } as PhaseStageTiming

    expect(flowKeysFromStage(stage)).toEqual(['0_5', '2_5'])
  })

  it('filters right-turn intensity rows and sorts remaining rows by pressure', () => {
    const items: DirectionIntensity[] = [
      { label: '西右转', movementKey: 'd6_t2', dir8No: 6, turnDirNo: 2, intensity: 0.99 },
      { label: '东左', movementKey: 'd2_t1', dir8No: 2, turnDirNo: 1, intensity: 0.72 },
      { label: '南直', movementKey: 'd4_t0', dir8No: 4, turnDirNo: 0, intensity: 0.81 },
    ]

    expect(isRightTurnIntensityItem(items[0])).toBe(true)
    expect(directionIntensityRows(items).map((row) => row.label)).toEqual(['南直', '东左'])
  })
})
