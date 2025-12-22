import { useState, useRef, useCallback, Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Environment, Html } from '@react-three/drei'
import { ModelViewer, type ModelViewerHandle } from './components/ModelViewer'
import { AnimationControls } from './components/AnimationControls'
import { FileUpload } from './components/FileUpload'
import './App.css'

export type AnimationType = 'none' | 'pee' | 'tailWag'
export type PeePhase = 'idle' | 'lifting' | 'holding' | 'lowering'
export type TailWagPhase = 'idle' | 'wagging' | 'returning'

export interface AnimationState {
  selectedAnimation: AnimationType
  speed: number
  isPlaying: boolean
  // Pee-specific state
  peePhase: PeePhase
  peeStartTime: number
  // Tail wag state
  tailWagPhase: TailWagPhase
  tailWagStartTime: number
}

const defaultAnimationState: AnimationState = {
  selectedAnimation: 'none',
  speed: 1,
  isPlaying: false,
  peePhase: 'idle',
  peeStartTime: 0,
  tailWagPhase: 'idle',
  tailWagStartTime: 0,
}

function Loader() {
  return (
    <Html center>
      <div style={{ color: 'white', fontSize: '1.5rem' }}>Loading model...</div>
    </Html>
  )
}

function App() {
  const [modelUrl, setModelUrl] = useState<string | null>(null)
  const [animationState, setAnimationState] = useState<AnimationState>(defaultAnimationState)
  const [showSkeleton, setShowSkeleton] = useState(false)
  const modelRef = useRef<ModelViewerHandle>(null)

  const handleFileUpload = useCallback((file: File) => {
    const url = URL.createObjectURL(file)
    console.log('File uploaded, URL:', url)
    setModelUrl(url)
    setAnimationState(defaultAnimationState)
  }, [])

  const handleAnimationChange = useCallback((animation: AnimationType) => {
    const now = performance.now() / 1000
    setAnimationState(prev => ({
      ...prev,
      selectedAnimation: animation,
      isPlaying: animation !== 'none',
      // Reset pee state when switching animations
      peePhase: animation === 'pee' ? 'lifting' : 'idle',
      peeStartTime: animation === 'pee' ? now : 0,
      // Reset tail wag state
      tailWagPhase: animation === 'tailWag' ? 'wagging' : 'idle',
      tailWagStartTime: animation === 'tailWag' ? now : 0,
    }))
  }, [])

  const handleSpeedChange = useCallback((speed: number) => {
    setAnimationState(prev => ({ ...prev, speed }))
  }, [])

  const handlePeePhaseChange = useCallback((phase: PeePhase, startTime: number) => {
    setAnimationState(prev => {
      // Normal pee mode
      return {
        ...prev,
        peePhase: phase,
        peeStartTime: startTime,
        isPlaying: phase !== 'idle',
        selectedAnimation: phase === 'idle' ? 'none' : prev.selectedAnimation,
      }
    })
  }, [])

  const handleTailWagPhaseChange = useCallback((phase: TailWagPhase, startTime: number) => {
    setAnimationState(prev => {
      if (phase === 'idle') {
        return {
          ...prev,
          tailWagPhase: 'idle',
          tailWagStartTime: 0,
          isPlaying: false,
          selectedAnimation: 'none',
        }
      }
      return {
        ...prev,
        tailWagPhase: phase,
        tailWagStartTime: startTime,
      }
    })
  }, [])

  const handleExport = useCallback(async () => {
    if (modelRef.current) {
      await modelRef.current.exportAnimation()
    }
  }, [])

  const handleReset = useCallback(() => {
    setAnimationState(defaultAnimationState)
  }, [])

  return (
    <div className="app">
      <header className="header">
        <h1>Animation Editor</h1>
        <div className="header-actions">
          {modelUrl && (
            <>
              <button onClick={handleReset} className="btn btn-secondary">
                Reset
              </button>
              <button onClick={handleExport} className="btn btn-primary">
                Export GLB
              </button>
            </>
          )}
        </div>
      </header>

      <div className="main-content">
        <div className="viewer-container">
          {!modelUrl ? (
            <FileUpload onFileUpload={handleFileUpload} />
          ) : (
            <Canvas
              camera={{ position: [15, 10, 15], fov: 50 }}
              shadows
            >
              <color attach="background" args={['#0a0a0f']} />
              <ambientLight intensity={0.6} />
              <directionalLight position={[10, 10, 5]} intensity={1.5} castShadow />
              <directionalLight position={[-5, 5, -5]} intensity={0.5} />
              <Suspense fallback={<Loader />}>
                <ModelViewer
                  ref={modelRef}
                  url={modelUrl}
                  animationState={animationState}
                  showSkeleton={showSkeleton}
                  onPeePhaseChange={handlePeePhaseChange}
                  onTailWagPhaseChange={handleTailWagPhaseChange}
                />
              </Suspense>
              <OrbitControls makeDefault />
              <Environment preset="studio" />
              <gridHelper args={[10, 10, '#2a2a3a', '#1a1a24']} />
            </Canvas>
          )}
        </div>

        {modelUrl && (
          <div className="controls-panel">
            <AnimationControls
              animationState={animationState}
              onAnimationChange={handleAnimationChange}
              onSpeedChange={handleSpeedChange}
              showSkeleton={showSkeleton}
              onShowSkeletonChange={setShowSkeleton}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default App
