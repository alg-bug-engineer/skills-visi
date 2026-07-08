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
      { label: '西直', dir8No: 6, turnDirNo: 0 },
      { label: '东左', dir8No: 2, turnDirNo: 1 },
      { label: '南右', dir8No: 4, turnDirNo: 2 },
      { label: '北行人', dir8No: 0, turnDirNo: 5 },
    ]

    expect(flowKeysFromStageMovements(movements)).toEqual(['6_1', '2_2', '4_3', '0_5'])
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
