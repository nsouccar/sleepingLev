import type { AnimationState, AnimationType } from '../App'

interface AnimationControlsProps {
  animationState: AnimationState
  onAnimationChange: (animation: AnimationType) => void
  onSpeedChange: (speed: number) => void
  showSkeleton: boolean
  onShowSkeletonChange: (show: boolean) => void
}

export function AnimationControls({
  animationState,
  onAnimationChange,
  onSpeedChange,
  showSkeleton,
  onShowSkeletonChange,
}: AnimationControlsProps) {
  const { selectedAnimation, speed, peePhase, tailWagPhase } = animationState

  const isAnimationRunning = (selectedAnimation === 'pee' && peePhase !== 'idle') ||
    (selectedAnimation === 'tailWag' && tailWagPhase !== 'idle')

  return (
    <div className="controls-section">
      <h3>Animation</h3>

      {/* Animation Selection */}
      <div style={{ marginBottom: '1rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem', color: '#888' }}>
          Select Animation
        </label>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button
            onClick={() => onAnimationChange('pee')}
            className={`btn ${selectedAnimation === 'pee' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ flex: 1, minWidth: '80px' }}
            disabled={selectedAnimation === 'pee' && peePhase !== 'idle'}
          >
            {selectedAnimation === 'pee' && peePhase !== 'idle'
              ? `Paw (${peePhase})`
              : 'Paw'}
          </button>
          <button
            onClick={() => onAnimationChange('tailWag')}
            className={`btn ${selectedAnimation === 'tailWag' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ flex: 1, minWidth: '80px' }}
            disabled={selectedAnimation === 'tailWag' && tailWagPhase !== 'idle'}
          >
            {selectedAnimation === 'tailWag' && tailWagPhase !== 'idle'
              ? 'Wagging...'
              : 'Tail Wag'}
          </button>
        </div>
      </div>

      {/* Speed Control */}
      {selectedAnimation !== 'none' && (
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem', color: '#888' }}>
            Speed: {speed.toFixed(1)}x
          </label>
          <input
            type="range"
            min={0.25}
            max={2}
            step={0.25}
            value={speed}
            onChange={(e) => onSpeedChange(parseFloat(e.target.value))}
            style={{ width: '100%' }}
          />
        </div>
      )}

      {/* Stop Animation */}
      {isAnimationRunning && (
        <button
          onClick={() => onAnimationChange('none')}
          className="btn btn-secondary"
          style={{ width: '100%', marginBottom: '1rem' }}
        >
          Stop Animation
        </button>
      )}

      {/* Skeleton Toggle */}
      <div style={{ borderTop: '1px solid #333', paddingTop: '1rem', marginTop: '0.5rem' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showSkeleton}
            onChange={(e) => onShowSkeletonChange(e.target.checked)}
          />
          <span style={{ fontSize: '0.85rem' }}>Show Skeleton</span>
        </label>
      </div>
    </div>
  )
}
