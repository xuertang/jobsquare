// Generates the extension PNG icons with no external dependencies.
// Draws the Gongzuo mark: an indigo rounded square with white "form line" bars.
import { deflateSync } from 'node:zlib'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(__dirname, '..', 'icons')

// --- minimal PNG encoder ---------------------------------------------------
const crcTable = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c >>> 0
  }
  return t
})()

function crc32(buf) {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) c = crcTable[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const typeBuf = Buffer.from(type, 'ascii')
  const body = Buffer.concat([typeBuf, data])
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length, 0)
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body), 0)
  return Buffer.concat([len, body, crc])
}

function encodePng(width, height, rgba) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // color type RGBA
  ihdr[10] = 0
  ihdr[11] = 0
  ihdr[12] = 0

  const stride = width * 4
  const raw = Buffer.alloc((stride + 1) * height)
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0 // filter: none
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride)
  }
  const idat = deflateSync(raw, { level: 9 })

  return Buffer.concat([
    sig,
    chunk('IHDR', ihdr),
    chunk('IDAT', idat),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

// --- drawing ---------------------------------------------------------------
function blend(dst, i, r, g, b, a) {
  const da = dst[i + 3] / 255
  const sa = a
  const outA = sa + da * (1 - sa)
  if (outA === 0) return
  for (let k = 0; k < 3; k++) {
    const s = [r, g, b][k]
    const d = dst[i + k]
    dst[i + k] = Math.round((s * sa + d * da * (1 - sa)) / outA)
  }
  dst[i + 3] = Math.round(outA * 255)
}

function inRoundedRect(x, y, w, h, r) {
  if (x < r && y < r) return Math.hypot(r - x, r - y) <= r
  if (x > w - r && y < r) return Math.hypot(x - (w - r), r - y) <= r
  if (x < r && y > h - r) return Math.hypot(r - x, y - (h - r)) <= r
  if (x > w - r && y > h - r) return Math.hypot(x - (w - r), y - (h - r)) <= r
  return true
}

function render(size) {
  const s = size
  const buf = Buffer.alloc(s * s * 4) // transparent
  const radius = s * 0.22
  const indigo = [99, 102, 241]
  const bars = [
    { y: 0.3, w: 0.5, a: 0.95 },
    { y: 0.47, w: 0.5, a: 0.72 },
    { y: 0.64, w: 0.32, a: 0.5 },
  ]
  const barX = s * 0.25
  const barH = Math.max(1, Math.round(s * 0.085))

  for (let y = 0; y < s; y++) {
    for (let x = 0; x < s; x++) {
      const i = (y * s + x) * 4
      if (!inRoundedRect(x + 0.5, y + 0.5, s, s, radius)) continue
      blend(buf, i, indigo[0], indigo[1], indigo[2], 1)
      for (const bar of bars) {
        const by = s * bar.y
        if (x >= barX && x <= barX + s * bar.w && y >= by && y <= by + barH) {
          blend(buf, i, 255, 255, 255, bar.a)
        }
      }
    }
  }
  return encodePng(s, s, buf)
}

mkdirSync(OUT_DIR, { recursive: true })
for (const size of [16, 32, 48, 128]) {
  const png = render(size)
  writeFileSync(resolve(OUT_DIR, `icon${size}.png`), png)
  console.log(`icons/icon${size}.png (${png.length} bytes)`)
}
