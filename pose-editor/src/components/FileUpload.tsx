import { useCallback } from 'react'

interface FileUploadProps {
  onFileUpload: (file: File) => void
}

export function FileUpload({ onFileUpload }: FileUploadProps) {
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      const file = e.dataTransfer.files[0]
      if (file && (file.name.endsWith('.glb') || file.name.endsWith('.gltf'))) {
        onFileUpload(file)
      }
    },
    [onFileUpload]
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        onFileUpload(file)
      }
    },
    [onFileUpload]
  )

  return (
    <div
      className="file-upload"
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      <div className="file-upload-content">
        <div className="file-upload-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <h2>Drop your Meshy GLB here</h2>
        <p>or click to browse</p>
        <input
          type="file"
          accept=".glb,.gltf"
          onChange={handleChange}
          className="file-input"
        />
      </div>
    </div>
  )
}
