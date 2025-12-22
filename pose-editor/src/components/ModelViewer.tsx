import { useEffect, useRef, forwardRef, useImperativeHandle, useMemo, useState, useCallback } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js'
import type { AnimationState, PeePhase, TailWagPhase } from '../App'
import { detectBodyParts, type DetectedParts } from '../utils/boneDetector'
import { applyPeeBoneRotations, isPeePhaseComplete, getNextPeePhase, clearStoredRotations, PEE_PHASE_DURATIONS } from '../utils/peeAnimation'
import { applyTailWagAnimation, isTailWagPhaseComplete, getNextTailWagPhase, clearTailRotations, TAIL_WAG_PHASE_DURATIONS } from '../utils/tailWagAnimation'
import { exportGLBWithAnimation, createAnimationClip } from '../utils/exporter'

interface ModelViewerProps {
  url: string
  animationState: AnimationState
  showSkeleton: boolean
  onPeePhaseChange?: (phase: PeePhase, startTime: number) => void
  onTailWagPhaseChange?: (phase: TailWagPhase, startTime: number) => void
}

export interface ModelViewerHandle {
  exportAnimation: () => Promise<void>
}

// Thick line component using a cylinder between two points
function BoneLine({ start, end, color }: { start: THREE.Vector3; end: THREE.Vector3; color: string }) {
  const { position, quaternion, length } = useMemo(() => {
    const direction = new THREE.Vector3().subVectors(end, start)
    const len = direction.length()
    const midpoint = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5)

    const up = new THREE.Vector3(0, 1, 0)
    const quat = new THREE.Quaternion()
    if (len > 0.0001) {
      const axis = direction.clone().normalize()
      quat.setFromUnitVectors(up, axis)
    }

    return { position: midpoint, quaternion: quat, length: len }
  }, [start.x, start.y, start.z, end.x, end.y, end.z])

  if (length < 0.0001) return null

  return (
    <mesh position={position} quaternion={quaternion}>
      <cylinderGeometry args={[0.015, 0.015, length, 6]} />
      <meshBasicMaterial color={color} />
    </mesh>
  )
}

function getBoneColor(name: string): string {
  const lowerName = name.toLowerCase()
  if (lowerName.includes('leg') || lowerName.includes('front') || lowerName.includes('back')) {
    return '#00ffff'
  } else if (lowerName.includes('tail')) {
    return '#ff8800'
  } else if (lowerName.includes('head') || lowerName.includes('ear')) {
    return '#ffff00'
  }
  return '#ff00ff'
}

function SkeletonVisualizer({ skeleton, modelGroup }: { skeleton: THREE.Skeleton; modelGroup: THREE.Group | null }) {
  const [boneData, setBoneData] = useState<Array<{
    pos: THREE.Vector3
    parentPos: THREE.Vector3 | null
    name: string
    color: string
  }>>([])

  useFrame(() => {
    if (modelGroup) {
      modelGroup.updateMatrixWorld(true)
    }

    const data: typeof boneData = []
    for (const bone of skeleton.bones) {
      bone.updateWorldMatrix(true, false)
      const pos = new THREE.Vector3()
      bone.getWorldPosition(pos)

      let parentPos: THREE.Vector3 | null = null
      if (bone.parent && bone.parent instanceof THREE.Bone) {
        bone.parent.updateWorldMatrix(true, false)
        parentPos = new THREE.Vector3()
        bone.parent.getWorldPosition(parentPos)
      }

      data.push({
        pos,
        parentPos,
        name: bone.name,
        color: getBoneColor(bone.name)
      })
    }
    setBoneData(data)
  })

  return (
    <group>
      {boneData.map((bd, i) => (
        <group key={i}>
          <mesh position={bd.pos}>
            <sphereGeometry args={[0.04, 8, 8]} />
            <meshBasicMaterial color={bd.color} />
          </mesh>
          {bd.parentPos && (
            <BoneLine start={bd.parentPos} end={bd.pos} color={bd.color} />
          )}
        </group>
      ))}
    </group>
  )
}

export const ModelViewer = forwardRef<ModelViewerHandle, ModelViewerProps>(
  ({ url, animationState, showSkeleton, onPeePhaseChange, onTailWagPhaseChange }, ref) => {
    const gltf = useGLTF(url)
    const groupRef = useRef<THREE.Group>(null)
    const skeletonRef = useRef<THREE.Skeleton | null>(null)
    const [skeletonReady, setSkeletonReady] = useState(false)
    const partsRef = useRef<DetectedParts | null>(null)
    const { camera } = useThree()

    // Track phase start times using clock.elapsedTime (not performance.now)
    const phaseStartTimeRef = useRef<{ pee: number; tailWag: number }>({ pee: -1, tailWag: -1 })
    const lastPeePhaseRef = useRef<PeePhase>('idle')
    const lastTailWagPhaseRef = useRef<TailWagPhase>('idle')

    // Clone scene using SkeletonUtils (must be before exportAnimation)
    const clonedScene = useMemo(() => {
      return SkeletonUtils.clone(gltf.scene)
    }, [gltf.scene])

    // Export animation function
    const exportAnimation = useCallback(async () => {
      if (!clonedScene || !skeletonRef.current) {
        console.error('No scene or skeleton to export')
        return
      }

      const { selectedAnimation } = animationState
      let clipToExport: THREE.AnimationClip | null = null

      if (selectedAnimation === 'pee') {
        // Record the pee animation by simulating the phases
        const fps = 30
        const peeDuration = PEE_PHASE_DURATIONS.lifting + PEE_PHASE_DURATIONS.holding + PEE_PHASE_DURATIONS.lowering
        const recordedFrames = new Map<string, THREE.Quaternion[]>()

        // Initialize frame arrays for each bone
        for (const bone of skeletonRef.current.bones) {
          recordedFrames.set(bone.name, [])
        }

        // Helper to record pee frames
        const phases: Array<'lifting' | 'holding' | 'lowering'> = ['lifting', 'holding', 'lowering']
        let accumulatedTime = 0

        for (const phase of phases) {
          const phaseDuration = PEE_PHASE_DURATIONS[phase]
          const phaseFrames = Math.ceil(phaseDuration * fps)

          for (let i = 0; i < phaseFrames; i++) {
            const phaseProgress = i / phaseFrames
            const phaseTime = phaseProgress * phaseDuration
            const startTime = accumulatedTime
            const currentTime = accumulatedTime + phaseTime

            // Apply pee animation for this frame
            if (partsRef.current) {
              applyPeeBoneRotations(
                partsRef.current.legChains.frontRight,
                phase,
                startTime,
                currentTime
              )
            }

            // Record all bone quaternions
            for (const bone of skeletonRef.current!.bones) {
              recordedFrames.get(bone.name)?.push(bone.quaternion.clone())
            }
          }
          accumulatedTime += phaseDuration
        }

        clearStoredRotations()

        clipToExport = createAnimationClip(
          skeletonRef.current,
          recordedFrames,
          { duration: peeDuration, fps, animationName: 'pee' }
        )
      } else if (selectedAnimation === 'tailWag') {
        // Record the tail wag animation
        const fps = 30
        const tailWagDuration = TAIL_WAG_PHASE_DURATIONS.wagging + TAIL_WAG_PHASE_DURATIONS.returning
        const recordedFrames = new Map<string, THREE.Quaternion[]>()

        // Initialize frame arrays for each bone
        for (const bone of skeletonRef.current.bones) {
          recordedFrames.set(bone.name, [])
        }

        const phases: Array<'wagging' | 'returning'> = ['wagging', 'returning']
        let accumulatedTime = 0

        for (const phase of phases) {
          const phaseDuration = TAIL_WAG_PHASE_DURATIONS[phase]
          const phaseFrames = Math.ceil(phaseDuration * fps)

          for (let i = 0; i < phaseFrames; i++) {
            const phaseTime = (i / phaseFrames) * phaseDuration
            const startTime = accumulatedTime
            const currentTime = accumulatedTime + phaseTime

            // Apply tail wag animation for this frame
            if (partsRef.current) {
              applyTailWagAnimation(
                partsRef.current,
                phase,
                startTime,
                currentTime
              )
            }

            // Record all bone quaternions
            for (const bone of skeletonRef.current!.bones) {
              recordedFrames.get(bone.name)?.push(bone.quaternion.clone())
            }
          }
          accumulatedTime += phaseDuration
        }

        clearTailRotations()

        clipToExport = createAnimationClip(
          skeletonRef.current,
          recordedFrames,
          { duration: tailWagDuration, fps, animationName: 'tailWag' }
        )
      }

      const filename = selectedAnimation !== 'none'
        ? `${selectedAnimation}_animation_${Date.now()}.glb`
        : `model_${Date.now()}.glb`

      await exportGLBWithAnimation(clonedScene, clipToExport, filename)
    }, [animationState, clonedScene])

    useImperativeHandle(ref, () => ({
      exportAnimation
    }), [exportAnimation])

    // Center and scale model on load
    useEffect(() => {
      if (!clonedScene || !groupRef.current) return

      clonedScene.updateMatrixWorld(true)
      const box = new THREE.Box3().setFromObject(clonedScene)
      const center = box.getCenter(new THREE.Vector3())
      const size = box.getSize(new THREE.Vector3())
      const maxDim = Math.max(size.x, size.y, size.z)

      if (maxDim === 0 || !isFinite(maxDim)) return

      const targetSize = 5
      const scale = targetSize / maxDim

      groupRef.current.scale.setScalar(scale)
      groupRef.current.position.set(
        -center.x * scale,
        -center.y * scale + (size.y * scale) / 2,
        -center.z * scale
      )

      camera.position.set(8, 5, 8)
      camera.lookAt(0, (size.y * scale) / 2, 0)
    }, [clonedScene, camera])

    // Find skeleton and detect body parts
    useEffect(() => {
      if (!clonedScene) return

      const bones: THREE.Bone[] = []

      clonedScene.traverse((obj: THREE.Object3D) => {
        if (obj instanceof THREE.SkinnedMesh && obj.skeleton) {
          skeletonRef.current = obj.skeleton
          obj.skeleton.bones.forEach((bone) => {
            if (!bones.some(b => b.name === bone.name)) {
              bones.push(bone)
            }
          })
        }
      })

      if (bones.length > 0) {
        partsRef.current = detectBodyParts(bones)
        setSkeletonReady(true)
      } else {
        setSkeletonReady(false)
      }
    }, [clonedScene])

    // Animation loop
    useFrame((state) => {
      const time = state.clock.elapsedTime
      const { selectedAnimation, peePhase, tailWagPhase } = animationState

      if (!partsRef.current || !groupRef.current) return

      const parts = partsRef.current

      // Detect phase changes and record start times using clock.elapsedTime
      if (peePhase !== lastPeePhaseRef.current) {
        if (peePhase !== 'idle') {
          phaseStartTimeRef.current.pee = time
        }
        lastPeePhaseRef.current = peePhase
      }

      if (tailWagPhase !== lastTailWagPhaseRef.current) {
        if (tailWagPhase !== 'idle') {
          phaseStartTimeRef.current.tailWag = time
        }
        lastTailWagPhaseRef.current = tailWagPhase
      }

      // Pee animation
      if (selectedAnimation === 'pee' && peePhase !== 'idle') {
        const peeStartTime = phaseStartTimeRef.current.pee
        applyPeeBoneRotations(
          parts.legChains.frontRight,
          peePhase,
          peeStartTime,
          time
        )

        if (isPeePhaseComplete(peePhase, peeStartTime, time)) {
          const nextPhase = getNextPeePhase(peePhase)
          if (onPeePhaseChange) {
            onPeePhaseChange(nextPhase, time)
            if (nextPhase === 'idle') {
              clearStoredRotations()
            }
          }
        }
      }
      // Tail wag animation
      else if (selectedAnimation === 'tailWag' && tailWagPhase !== 'idle') {
        const tailWagStartTime = phaseStartTimeRef.current.tailWag
        applyTailWagAnimation(
          parts,
          tailWagPhase,
          tailWagStartTime,
          time
        )

        if (isTailWagPhaseComplete(tailWagPhase, tailWagStartTime, time)) {
          const nextPhase = getNextTailWagPhase(tailWagPhase)
          if (onTailWagPhaseChange) {
            onTailWagPhaseChange(nextPhase, time)
            if (nextPhase === 'idle') {
              clearTailRotations()
            }
          }
        }
      }
    })

    return (
      <>
        <group ref={groupRef}>
          <primitive object={clonedScene} />
        </group>

        {showSkeleton && skeletonReady && skeletonRef.current && (
          <SkeletonVisualizer skeleton={skeletonRef.current} modelGroup={groupRef.current} />
        )}
      </>
    )
  }
)

ModelViewer.displayName = 'ModelViewer'
