import * as THREE from 'three'
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js'

export interface AnimationExportOptions {
  duration: number
  fps: number
  animationName: string
}

/**
 * Record bone transforms and create an AnimationClip
 */
export function createAnimationClip(
  skeleton: THREE.Skeleton,
  recordedFrames: Map<string, THREE.Quaternion[]>,
  options: AnimationExportOptions
): THREE.AnimationClip {
  const tracks: THREE.KeyframeTrack[] = []
  const frameCount = recordedFrames.get(skeleton.bones[0]?.name)?.length || 0
  const frameDuration = options.duration / frameCount

  // Create time array
  const times: number[] = []
  for (let i = 0; i < frameCount; i++) {
    times.push(i * frameDuration)
  }

  // Create quaternion tracks for each bone
  for (const bone of skeleton.bones) {
    const frames = recordedFrames.get(bone.name)
    if (!frames || frames.length === 0) continue

    const values: number[] = []
    for (const quat of frames) {
      values.push(quat.x, quat.y, quat.z, quat.w)
    }

    const track = new THREE.QuaternionKeyframeTrack(
      `${bone.name}.quaternion`,
      times,
      values
    )
    tracks.push(track)
  }

  return new THREE.AnimationClip(options.animationName, options.duration, tracks)
}

/**
 * Export scene with animation as GLB
 */
export async function exportGLBWithAnimation(
  scene: THREE.Object3D,
  clip: THREE.AnimationClip | null,
  filename?: string
): Promise<void> {
  const exporter = new GLTFExporter()

  // Clone the scene to avoid modifying the original
  const exportScene = scene.clone(true)

  const options: { binary: true; animations?: THREE.AnimationClip[] } = { binary: true }

  if (clip) {
    options.animations = [clip]
  }

  return new Promise((resolve, reject) => {
    exporter.parse(
      exportScene,
      (result) => {
        const blob = new Blob([result as ArrayBuffer], { type: 'application/octet-stream' })
        const url = URL.createObjectURL(blob)

        const link = document.createElement('a')
        link.href = url
        link.download = filename || `animated_model_${Date.now()}.glb`
        link.click()

        URL.revokeObjectURL(url)
        resolve()
      },
      (error) => {
        console.error('Export failed:', error)
        reject(error)
      },
      options
    )
  })
}

/**
 * Simple export without animation (legacy)
 */
export async function exportGLB(scene: THREE.Object3D): Promise<void> {
  return exportGLBWithAnimation(scene, null, `posed_model_${Date.now()}.glb`)
}
