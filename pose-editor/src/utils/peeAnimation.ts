import * as THREE from 'three'
import type { LegChain } from './boneDetector'
import type { PeePhase } from '../App'

export const PEE_PHASE_DURATIONS: Record<Exclude<PeePhase, 'idle'>, number> = {
  lifting: 0.4,
  holding: 1.5,
  lowering: 0.4,
}

export interface PeeBoneRotations {
  hip: THREE.Quaternion
  upperLeg: THREE.Quaternion
  lowerLeg: THREE.Quaternion
  paw?: THREE.Quaternion
}

// Store the original bone rotations when animation starts
let storedRotations: PeeBoneRotations | null = null
// Store the TARGET rotations (fully lifted pose) - computed once
let targetRotations: PeeBoneRotations | null = null

// "Pawing" animation angles
const PAW_LIFT = -1.5         // Raise elbow up
const PAW_AMPLITUDE = 0.3     // How much to move back and forth when pawing
const PAW_SPEED = 8           // Speed of pawing motion

function easeOutQuad(t: number): number {
  return t * (2 - t)
}

function easeInQuad(t: number): number {
  return t * t
}

/**
 * Store the current bone rotations AND compute target rotations
 * Call this when transitioning from idle to lifting
 */
export function storeLegRotations(frontRightChain: LegChain): void {
  if (!frontRightChain.upper) return

  // Store original rotations for all bones
  storedRotations = {
    hip: frontRightChain.hip?.quaternion.clone() ?? new THREE.Quaternion(),
    upperLeg: frontRightChain.upper.quaternion.clone(),
    lowerLeg: frontRightChain.lower?.quaternion.clone() ?? new THREE.Quaternion(),
    paw: frontRightChain.paw?.quaternion.clone()
  }

  // Compute target rotation for upper leg (elbow) - bend it up
  // Apply rotation in local bone space (multiply on the right)
  const elbowLiftRotation = new THREE.Quaternion()
  elbowLiftRotation.setFromAxisAngle(new THREE.Vector3(1, 0, 0), PAW_LIFT)

  const upperTarget = new THREE.Quaternion()
  upperTarget.multiplyQuaternions(storedRotations.upperLeg, elbowLiftRotation)

  // Keep hip and lower in their original positions
  targetRotations = {
    hip: storedRotations.hip.clone(),
    upperLeg: upperTarget,
    lowerLeg: storedRotations.lowerLeg.clone(),
    paw: storedRotations.paw?.clone()
  }

  console.log('Paw raise animation stored rotations:', {
    hip: frontRightChain.hip?.name,
    upper: frontRightChain.upper?.name,
    lower: frontRightChain.lower?.name,
    originalHip: storedRotations.hip.toArray(),
    targetHip: targetRotations.hip.toArray()
  })
}

/**
 * Clear stored rotations (call when pee animation ends)
 */
export function clearStoredRotations(): void {
  storedRotations = null
  targetRotations = null
}

/**
 * Apply pee animation using SLERP between stored and target rotations
 * This ensures smooth, stable interpolation without spinning
 */
export function applyPeeBoneRotations(
  frontRightChain: LegChain,
  phase: PeePhase,
  startTime: number,
  currentTime: number
): { bodyTilt: number; isComplete: boolean } {
  if (phase === 'idle' || !frontRightChain.upper) {
    return { bodyTilt: 0, isComplete: false }
  }

  // If we don't have stored rotations, store them now (only once per pee cycle)
  if (!storedRotations || !targetRotations) {
    storeLegRotations(frontRightChain)
  }

  // Safety check
  if (!storedRotations || !targetRotations) {
    return { bodyTilt: 0, isComplete: false }
  }

  const elapsed = currentTime - startTime
  const duration = PEE_PHASE_DURATIONS[phase]
  const progress = Math.min(elapsed / duration, 1)
  const isComplete = progress >= 1

  // Calculate lift factor based on phase with easing
  let liftFactor: number
  switch (phase) {
    case 'lifting':
      liftFactor = easeOutQuad(progress)
      break
    case 'holding':
      liftFactor = 1
      break
    case 'lowering':
      liftFactor = 1 - easeInQuad(progress)
      break
    default:
      liftFactor = 0
  }

  // Animate the upper leg (elbow)
  if (phase === 'holding') {
    // During holding, add a pawing motion (back and forth)
    const pawOffset = Math.sin(currentTime * PAW_SPEED) * PAW_AMPLITUDE

    // Create pawing rotation on top of the lifted position
    const pawingRotation = new THREE.Quaternion()
    pawingRotation.setFromAxisAngle(new THREE.Vector3(1, 0, 0), pawOffset)

    // Apply: lifted position + pawing motion
    const pawingTarget = new THREE.Quaternion()
    pawingTarget.multiplyQuaternions(targetRotations.upperLeg, pawingRotation)

    frontRightChain.upper.quaternion.copy(pawingTarget)
  } else {
    // Lifting or lowering - just interpolate
    frontRightChain.upper.quaternion.slerpQuaternions(
      storedRotations.upperLeg,
      targetRotations.upperLeg,
      liftFactor
    )
  }

  return { bodyTilt: 0, isComplete }
}

/**
 * Get the next phase in the pee animation sequence
 */
export function getNextPeePhase(currentPhase: PeePhase): PeePhase {
  switch (currentPhase) {
    case 'lifting':
      return 'holding'
    case 'holding':
      return 'lowering'
    case 'lowering':
      return 'idle'
    default:
      return 'idle'
  }
}

/**
 * Check if current phase has completed based on elapsed time
 */
export function isPeePhaseComplete(phase: PeePhase, startTime: number, currentTime: number): boolean {
  if (phase === 'idle') return false
  const elapsed = currentTime - startTime
  return elapsed >= PEE_PHASE_DURATIONS[phase]
}
