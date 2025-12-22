import * as THREE from 'three'
import type { DetectedParts } from './boneDetector'

// Tail wag animation parameters
const TAIL_WAG_AMPLITUDE = 0.4   // How much to wag side to side (radians)
const TAIL_WAG_SPEED = 12        // Speed of wagging
const WAG_DURATION = 2.0         // Total duration of wagging

export type TailWagPhase = 'idle' | 'wagging' | 'returning'

export const TAIL_WAG_PHASE_DURATIONS: Record<Exclude<TailWagPhase, 'idle'>, number> = {
  wagging: WAG_DURATION,
  returning: 0.3,
}

// Store original tail rotations
let storedTailRotations: THREE.Quaternion[] | null = null
// Store the last wag angle for smooth return
let lastWagAngle: number = 0

export function storeTailRotations(parts: DetectedParts): void {
  if (parts.tail.length === 0) return

  storedTailRotations = parts.tail.map(bone => bone.quaternion.clone())
}

export function clearTailRotations(): void {
  storedTailRotations = null
  lastWagAngle = 0
}

export function applyTailWagAnimation(
  parts: DetectedParts,
  phase: TailWagPhase,
  startTime: number,
  currentTime: number
): { isComplete: boolean } {
  if (phase === 'idle' || parts.tail.length === 0) {
    return { isComplete: false }
  }

  // Store rotations if not already stored
  if (!storedTailRotations) {
    storeTailRotations(parts)
  }

  if (!storedTailRotations) {
    return { isComplete: false }
  }

  const elapsed = currentTime - startTime
  const duration = TAIL_WAG_PHASE_DURATIONS[phase]
  const progress = Math.min(elapsed / duration, 1)
  const isComplete = progress >= 1

  let wagAngle: number

  if (phase === 'wagging') {
    // Calculate wag angle using sine wave
    wagAngle = Math.sin(currentTime * TAIL_WAG_SPEED) * TAIL_WAG_AMPLITUDE
    lastWagAngle = wagAngle
  } else if (phase === 'returning') {
    // Smoothly return to original position
    wagAngle = lastWagAngle * (1 - progress)
  } else {
    wagAngle = 0
  }

  // Apply wag to each tail bone with same amplitude for symmetry
  parts.tail.forEach((bone, index) => {
    if (!storedTailRotations || index >= storedTailRotations.length) return

    // Create wag rotation (side to side on Z axis for horizontal wag)
    const wagRotation = new THREE.Quaternion()
    wagRotation.setFromAxisAngle(new THREE.Vector3(0, 0, 1), wagAngle)

    // Apply: original rotation + wag
    const targetRotation = new THREE.Quaternion()
    targetRotation.multiplyQuaternions(storedTailRotations[index], wagRotation)

    bone.quaternion.copy(targetRotation)
  })

  return { isComplete }
}

export function getNextTailWagPhase(currentPhase: TailWagPhase): TailWagPhase {
  switch (currentPhase) {
    case 'wagging':
      return 'returning'
    case 'returning':
      return 'idle'
    default:
      return 'idle'
  }
}

export function isTailWagPhaseComplete(phase: TailWagPhase, startTime: number, currentTime: number): boolean {
  if (phase === 'idle') return false
  const elapsed = currentTime - startTime
  return elapsed >= TAIL_WAG_PHASE_DURATIONS[phase]
}
