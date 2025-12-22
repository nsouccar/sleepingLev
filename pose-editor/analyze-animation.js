// Simple GLB parser to extract animation data
import fs from 'fs'

const filePath = '../model_Animation_Walking_withSkin.glb'

// Read GLB file
const buffer = fs.readFileSync(filePath)

// GLB format: 12-byte header + chunks
// Header: magic (4) + version (4) + length (4)
const magic = buffer.toString('ascii', 0, 4)
const version = buffer.readUInt32LE(4)
const length = buffer.readUInt32LE(8)

console.log('=== GLB Header ===')
console.log(`Magic: ${magic}`)
console.log(`Version: ${version}`)
console.log(`Total length: ${length} bytes`)

// First chunk should be JSON
const chunk0Length = buffer.readUInt32LE(12)
const chunk0Type = buffer.readUInt32LE(16)

console.log(`\nJSON chunk length: ${chunk0Length}`)

// Extract JSON
const jsonStr = buffer.toString('utf8', 20, 20 + chunk0Length)
const gltf = JSON.parse(jsonStr)

console.log('\n=== Skeleton/Nodes ===')
if (gltf.nodes) {
  gltf.nodes.forEach((node, i) => {
    if (node.name) {
      const info = []
      if (node.children) info.push(`children: [${node.children.join(',')}]`)
      if (node.rotation) info.push(`rot: [${node.rotation.map(v => v.toFixed(2)).join(',')}]`)
      if (node.translation) info.push(`pos: [${node.translation.map(v => v.toFixed(2)).join(',')}]`)
      console.log(`  ${i}: ${node.name} ${info.length ? '- ' + info.join(', ') : ''}`)
    }
  })
}

console.log('\n=== Animations ===')
if (gltf.animations) {
  gltf.animations.forEach((anim, animIdx) => {
    console.log(`\nAnimation ${animIdx}: "${anim.name || 'unnamed'}"`)
    console.log(`  Channels: ${anim.channels.length}`)
    console.log(`  Samplers: ${anim.samplers.length}`)

    // Get accessor info for timing
    const samplerDetails = anim.samplers.map((sampler, i) => {
      const inputAcc = gltf.accessors[sampler.input]
      const outputAcc = gltf.accessors[sampler.output]
      return {
        index: i,
        interpolation: sampler.interpolation || 'LINEAR',
        inputCount: inputAcc.count,
        inputMin: inputAcc.min?.[0],
        inputMax: inputAcc.max?.[0],
        outputType: outputAcc.type
      }
    })

    // Group channels by target node
    const channelsByNode = {}
    anim.channels.forEach((channel, i) => {
      const nodeIdx = channel.target.node
      const nodeName = gltf.nodes[nodeIdx]?.name || `node_${nodeIdx}`
      const path = channel.target.path
      const sampler = samplerDetails[channel.sampler]

      if (!channelsByNode[nodeName]) {
        channelsByNode[nodeName] = []
      }
      channelsByNode[nodeName].push({
        path,
        keyframes: sampler.inputCount,
        duration: sampler.inputMax - sampler.inputMin,
        interpolation: sampler.interpolation
      })
    })

    console.log('\n  Animated nodes:')
    Object.entries(channelsByNode).forEach(([name, channels]) => {
      console.log(`    ${name}:`)
      channels.forEach(ch => {
        console.log(`      - ${ch.path}: ${ch.keyframes} keyframes over ${ch.duration?.toFixed(3)}s (${ch.interpolation})`)
      })
    })

    // Extract and analyze actual keyframe data for leg bones
    console.log('\n  === Detailed leg animation data ===')
    anim.channels.forEach((channel) => {
      const nodeIdx = channel.target.node
      const nodeName = gltf.nodes[nodeIdx]?.name || ''
      const path = channel.target.path

      if (nodeName.toLowerCase().includes('leg') ||
          nodeName.toLowerCase().includes('front') ||
          nodeName.toLowerCase().includes('back')) {

        const sampler = anim.samplers[channel.sampler]
        const inputAcc = gltf.accessors[sampler.input]
        const outputAcc = gltf.accessors[sampler.output]

        // Get buffer view for input (times)
        const inputBV = gltf.bufferViews[inputAcc.bufferView]
        const inputOffset = 20 + chunk0Length + 8 + (inputBV.byteOffset || 0) + (inputAcc.byteOffset || 0)

        // Get buffer view for output (values)
        const outputBV = gltf.bufferViews[outputAcc.bufferView]
        const outputOffset = 20 + chunk0Length + 8 + (outputBV.byteOffset || 0) + (outputAcc.byteOffset || 0)

        console.log(`\n  ${nodeName}.${path}:`)

        // Read times
        const times = []
        for (let i = 0; i < Math.min(inputAcc.count, 15); i++) {
          times.push(buffer.readFloatLE(inputOffset + i * 4))
        }
        console.log(`    Times: [${times.map(t => t.toFixed(3)).join(', ')}]`)

        // Read values based on type
        if (path === 'rotation') {
          console.log('    Rotations (quaternion -> euler deg):')
          for (let i = 0; i < Math.min(inputAcc.count, 10); i++) {
            const qx = buffer.readFloatLE(outputOffset + i * 16)
            const qy = buffer.readFloatLE(outputOffset + i * 16 + 4)
            const qz = buffer.readFloatLE(outputOffset + i * 16 + 8)
            const qw = buffer.readFloatLE(outputOffset + i * 16 + 12)

            // Convert quaternion to euler (simplified)
            const sinr_cosp = 2 * (qw * qx + qy * qz)
            const cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
            const roll = Math.atan2(sinr_cosp, cosr_cosp) * 180 / Math.PI

            const sinp = 2 * (qw * qy - qz * qx)
            const pitch = Math.asin(Math.max(-1, Math.min(1, sinp))) * 180 / Math.PI

            const siny_cosp = 2 * (qw * qz + qx * qy)
            const cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
            const yaw = Math.atan2(siny_cosp, cosy_cosp) * 180 / Math.PI

            console.log(`      t=${times[i]?.toFixed(3)}: X=${roll.toFixed(1)}° Y=${pitch.toFixed(1)}° Z=${yaw.toFixed(1)}°`)
          }
        } else if (path === 'translation') {
          console.log('    Positions:')
          for (let i = 0; i < Math.min(inputAcc.count, 10); i++) {
            const x = buffer.readFloatLE(outputOffset + i * 12)
            const y = buffer.readFloatLE(outputOffset + i * 12 + 4)
            const z = buffer.readFloatLE(outputOffset + i * 12 + 8)
            console.log(`      t=${times[i]?.toFixed(3)}: x=${x.toFixed(4)} y=${y.toFixed(4)} z=${z.toFixed(4)}`)
          }
        }
      }
    })
  })
} else {
  console.log('No animations found in this file')
}
