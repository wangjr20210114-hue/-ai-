import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { PNG } from 'pngjs'

const outputDirectory = resolve('src/assets/tab')
const size = 81
const scale = size / 64

function colorBytes(value) {
  const hex = value.replace('#', '')
  return [
    Number.parseInt(hex.slice(0, 2), 16),
    Number.parseInt(hex.slice(2, 4), 16),
    Number.parseInt(hex.slice(4, 6), 16),
  ]
}

function createCanvas(color) {
  const png = new PNG({ width: size, height: size, colorType: 6 })
  const [red, green, blue] = colorBytes(color)
  const setPixel = (x, y, alpha = 255) => {
    const px = Math.round(x)
    const py = Math.round(y)
    if (px < 0 || py < 0 || px >= size || py >= size) return
    const offset = (py * size + px) * 4
    png.data[offset] = red
    png.data[offset + 1] = green
    png.data[offset + 2] = blue
    png.data[offset + 3] = Math.max(png.data[offset + 3], alpha)
  }
  const dot = (x, y, radius = 1.65 * scale) => {
    const cx = x * scale
    const cy = y * scale
    for (let py = Math.floor(cy - radius - 1); py <= Math.ceil(cy + radius + 1); py += 1) {
      for (let px = Math.floor(cx - radius - 1); px <= Math.ceil(cx + radius + 1); px += 1) {
        const distance = Math.hypot(px - cx, py - cy)
        if (distance <= radius) setPixel(px, py)
        else if (distance <= radius + 1) setPixel(px, py, Math.round(255 * (radius + 1 - distance)))
      }
    }
  }
  const line = (x1, y1, x2, y2, width = 3.2) => {
    const steps = Math.max(2, Math.ceil(Math.hypot(x2 - x1, y2 - y1) * scale * 1.8))
    for (let index = 0; index <= steps; index += 1) {
      const ratio = index / steps
      dot(x1 + (x2 - x1) * ratio, y1 + (y2 - y1) * ratio, width * scale / 2)
    }
  }
  const circle = (cx, cy, radius, width = 3.2) => {
    const steps = Math.ceil(radius * scale * 8)
    let previous = [cx + radius, cy]
    for (let index = 1; index <= steps; index += 1) {
      const angle = (Math.PI * 2 * index) / steps
      const next = [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius]
      line(previous[0], previous[1], next[0], next[1], width)
      previous = next
    }
  }
  const polyline = (points, close = false, width = 3.2) => {
    points.slice(1).forEach((point, index) => line(
      points[index][0],
      points[index][1],
      point[0],
      point[1],
      width,
    ))
    if (close) line(points.at(-1)[0], points.at(-1)[1], points[0][0], points[0][1], width)
  }
  const roundedRect = (x, y, width, height, radius) => {
    line(x + radius, y, x + width - radius, y)
    line(x + radius, y + height, x + width - radius, y + height)
    line(x, y + radius, x, y + height - radius)
    line(x + width, y + radius, x + width, y + height - radius)
    const corners = [
      [x + radius, y + radius, Math.PI, Math.PI * 1.5],
      [x + width - radius, y + radius, Math.PI * 1.5, Math.PI * 2],
      [x + width - radius, y + height - radius, 0, Math.PI * .5],
      [x + radius, y + height - radius, Math.PI * .5, Math.PI],
    ]
    corners.forEach(([cx, cy, start, end]) => {
      let previous = [cx + Math.cos(start) * radius, cy + Math.sin(start) * radius]
      for (let index = 1; index <= 12; index += 1) {
        const angle = start + (end - start) * index / 12
        const next = [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius]
        line(previous[0], previous[1], next[0], next[1])
        previous = next
      }
    })
  }
  return { png, line, circle, polyline, roundedRect }
}

const painters = {
  chat({ line, roundedRect }) {
    roundedRect(11, 9, 42, 36, 9)
    line(20, 43, 15, 52)
    line(15, 52, 29, 45)
    line(22, 21, 42, 21)
    line(22, 30, 35, 30)
  },
  calendar({ line, circle, roundedRect }) {
    roundedRect(10, 13, 44, 41, 8)
    line(10, 25, 54, 25)
    line(22, 8, 22, 18)
    line(42, 8, 42, 18)
    ;[[22, 35], [32, 35], [42, 35], [22, 44], [32, 44], [42, 44]]
      .forEach(([x, y]) => circle(x, y, 1.25, 2.5))
  },
  reading({ line, polyline }) {
    polyline([[9, 13], [18, 12], [25, 14], [32, 18], [32, 54], [25, 50], [18, 48], [9, 49]], true)
    polyline([[55, 13], [46, 12], [39, 14], [32, 18]], false)
    polyline([[55, 13], [55, 49], [46, 48], [39, 50], [32, 54]], false)
    line(17, 25, 27, 28)
    line(17, 34, 27, 37)
  },
  proactive({ polyline }) {
    polyline([[32, 7], [36, 22], [50, 26], [36, 30], [32, 45], [28, 30], [14, 26], [28, 22]], true)
    polyline([[50, 42], [52, 49], [59, 51], [52, 53], [50, 60], [48, 53], [41, 51], [48, 49]], true, 2.8)
  },
  settings({ line, circle }) {
    line(12, 18, 52, 18)
    line(12, 32, 52, 32)
    line(12, 46, 52, 46)
    circle(23, 18, 5)
    circle(42, 32, 5)
    circle(28, 46, 5)
  },
}

const themes = {
  light: { idle: '#8d7668', active: '#ed6a2c' },
  dark: { idle: '#9d91b4', active: '#b59cff' },
}

await mkdir(outputDirectory, { recursive: true })

for (const [theme, colors] of Object.entries(themes)) {
  for (const [state, color] of Object.entries(colors)) {
    for (const [name, paint] of Object.entries(painters)) {
      const canvas = createCanvas(color)
      paint(canvas)
      await writeFile(
        resolve(outputDirectory, `${name}-${theme}-${state}.png`),
        PNG.sync.write(canvas.png),
      )
    }
  }
}

process.stdout.write(`Generated Floris tab icons in ${outputDirectory}\n`)
