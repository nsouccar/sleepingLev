import * as THREE from 'three'

// A leg chain contains bones in order from hip to paw
export interface LegChain {
  hip: THREE.Bone | null      // backleg / frontleg (root of leg)
  upper: THREE.Bone | null    // backleg0 / frontleg0
  lower: THREE.Bone | null    // backleg1 / frontleg1
  paw: THREE.Bone | null      // backleg2 / frontleg2
  allBones: THREE.Bone[]      // all bones in chain, ordered
}

export interface DetectedParts {
  head: THREE.Bone[]
  neck: THREE.Bone | null
  chest: THREE.Bone | null
  hips: THREE.Bone | null
  tail: THREE.Bone[]
  ears: THREE.Bone[]
  // Legacy arrays (for backwards compatibility)
  frontLegsL: THREE.Bone[]
  frontLegsR: THREE.Bone[]
  backLegsL: THREE.Bone[]
  backLegsR: THREE.Bone[]
  // New: structured leg chains for IK
  legChains: {
    frontLeft: LegChain
    frontRight: LegChain
    backLeft: LegChain
    backRight: LegChain
  }
}

// Patterns for detecting body parts from bone names
const patterns = {
  head: /^head/i,
  neck: /neck/i,
  chest: /chest|spine|torso/i,
  hips: /^hips?$/i,
  tail: /tail/i,
  ear: /ear/i,
  // Leg patterns - match "frontleg", "backleg", "R_frontleg", "R_backleg", etc.
  frontLegRoot: /^(r[_\-]?)?frontleg$/i,
  backLegRoot: /^(r[_\-]?)?backleg$/i,
  legBone: /^(r[_\-]?)?(front|back)leg(\d*)$/i,
  right: /^r[_\-]/i,
}

function isRight(name: string): boolean {
  return patterns.right.test(name)
}

function createEmptyLegChain(): LegChain {
  return { hip: null, upper: null, lower: null, paw: null, allBones: [] }
}

// Get bone chain by traversing children
function getLegChainFromRoot(rootBone: THREE.Bone): LegChain {
  const chain = createEmptyLegChain()
  chain.hip = rootBone
  chain.allBones.push(rootBone)

  // Traverse down the hierarchy to find leg bones
  let current: THREE.Bone | null = rootBone
  const boneOrder: ('upper' | 'lower' | 'paw')[] = ['upper', 'lower', 'paw']
  let orderIndex = 0

  while (current && orderIndex < boneOrder.length) {
    // Find child bone that's part of the leg
    const childBone: THREE.Bone | undefined = current.children.find(
      (child): child is THREE.Bone => child instanceof THREE.Bone
    )

    if (childBone) {
      chain[boneOrder[orderIndex]] = childBone
      chain.allBones.push(childBone)
      current = childBone
      orderIndex++
    } else {
      break
    }
  }

  return chain
}

export function detectBodyParts(bones: THREE.Bone[]): DetectedParts {
  const parts: DetectedParts = {
    head: [],
    neck: null,
    chest: null,
    hips: null,
    tail: [],
    ears: [],
    frontLegsL: [],
    frontLegsR: [],
    backLegsL: [],
    backLegsR: [],
    legChains: {
      frontLeft: createEmptyLegChain(),
      frontRight: createEmptyLegChain(),
      backLeft: createEmptyLegChain(),
      backRight: createEmptyLegChain(),
    },
  }

  // Build bone lookup
  const boneMap = new Map<string, THREE.Bone>()
  bones.forEach((bone) => boneMap.set(bone.name, bone))

  // Classify each bone
  for (const bone of bones) {
    const name = bone.name

    // Head
    if (patterns.head.test(name)) {
      parts.head.push(bone)
      continue
    }

    // Neck
    if (patterns.neck.test(name)) {
      if (!parts.neck) {
        parts.neck = bone
      }
      continue
    }

    // Ears
    if (patterns.ear.test(name)) {
      parts.ears.push(bone)
      continue
    }

    // Chest/spine
    if (patterns.chest.test(name)) {
      if (!parts.chest) {
        parts.chest = bone
      }
      continue
    }

    // Hips
    if (patterns.hips.test(name)) {
      if (!parts.hips) {
        parts.hips = bone
      }
      continue
    }

    // Tail
    if (patterns.tail.test(name)) {
      parts.tail.push(bone)
      continue
    }

    // Front leg roots - detect and build chain
    if (patterns.frontLegRoot.test(name)) {
      const chain = getLegChainFromRoot(bone)
      if (isRight(name)) {
        parts.legChains.frontRight = chain
        parts.frontLegsR = chain.allBones
      } else {
        parts.legChains.frontLeft = chain
        parts.frontLegsL = chain.allBones
      }
      continue
    }

    // Back leg roots - detect and build chain
    if (patterns.backLegRoot.test(name)) {
      const chain = getLegChainFromRoot(bone)
      if (isRight(name)) {
        parts.legChains.backRight = chain
        parts.backLegsR = chain.allBones
      } else {
        parts.legChains.backLeft = chain
        parts.backLegsL = chain.allBones
      }
      continue
    }
  }

  // Sort tail bones by hierarchy depth
  parts.tail.sort((a, b) => {
    let depthA = 0, depthB = 0
    let parent: THREE.Object3D | null = a
    while (parent) { depthA++; parent = parent.parent }
    parent = b
    while (parent) { depthB++; parent = parent.parent }
    return depthA - depthB
  })

  return parts
}
