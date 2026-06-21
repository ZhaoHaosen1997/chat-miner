/**
 * JSON/文本高亮工具 — 零依赖，适配浅色主题
 */

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// ── JSON 高亮 ────────────────────────────────────────────────

function colorValue(val) {
  const t = val.trim()
  if (/^(true|false|null)$/.test(t)) {
    return `<span class="text-rose-500">${t}</span>`
  }
  if (/^-?\d+\.?\d*$/.test(t)) {
    return `<span class="text-amber-600">${t}</span>`
  }
  if (/^&quot;.*&quot;$/.test(t)) {
    return `<span class="text-emerald-600">${t}</span>`
  }
  return t
}

function highlightJSON(text) {
  const pretty = JSON.stringify(JSON.parse(text), null, 2)
  let html = escapeHtml(pretty)

  const lines = html.split('\n')
  const colored = lines.map((line) => {
    const m = line.match(
      /^(\s*)&quot;(.+?)&quot;(\s*:\s*)(.*?)(,?)$/
    )
    if (m) {
      const [, indent, key, colon, rawVal, comma] = m
      const keyHtml = `<span class="text-indigo-600">&quot;${key}&quot;</span>`
      const valHtml = colorValue(rawVal)
      return `${indent}${keyHtml}${colon}${valHtml}${comma}`
    }
    line = line.replace(/([{}[\]])/g,
      '<span class="text-slate-500">$1</span>')
    line = line.replace(
      /(?<!<span class=")(?<!>)&quot;(.+?)&quot;/g,
      '<span class="text-emerald-600">&quot;$1&quot;</span>'
    )
    return line
  })

  return colored.join('\n')
}

// ── 混合内容高亮（非 JSON 文本） ────────────────────────────

function highlightMixed(text) {
  let html = escapeHtml(text)

  const lines = html.split('\n')
  const colored = lines.map((line) => {
    // 聊天行: [HH:MM] [N]: 或 [HH:MM] [N] 开头
    const chatMatch = line.match(
      /^(\[(\d{2}:\d{2})\])?\s*(\[(\d+)\])(:?\s*)/
    )
    if (chatMatch && chatMatch[2]) {
      const timeHtml = `<span class="text-amber-600">${chatMatch[1]}</span>`
      const speakerHtml = `<span class="text-indigo-500">${chatMatch[3]}</span>`
      const rest = line.slice(chatMatch[0].length)
      return `${timeHtml} ${speakerHtml}${chatMatch[5]}${colorInline(rest)}`
    }

    // Markdown 标题: # / ## / ### 开头
    const hMatch = line.match(/^(#{1,3}\s+)(.+)$/)
    if (hMatch) {
      return `<span class="text-slate-800 font-semibold">${hMatch[1]}${hMatch[2]}</span>`
    }

    // 列表项: - 开头
    const liMatch = line.match(/^(\s*)(-)(\s+)(.+)$/)
    if (liMatch) {
      const dashHtml = `<span class="text-slate-400">${liMatch[2]}</span>`
      return `${liMatch[1]}${dashHtml}${liMatch[3]}${colorInline(liMatch[4])}`
    }

    // 普通行：仍有内联着色
    return colorInline(line)
  })

  return colored.join('\n')
}

/** 内联着色：粗体、中文冒号键值、方括号标记 */
function colorInline(text) {
  // **粗体**
  text = text.replace(
    /\*\*(.+?)\*\*/g,
    '<strong class="text-slate-800">$1</strong>'
  )
  // 【标记文字】
  text = text.replace(
    /(【.+?】)/g,
    '<span class="text-violet-500 font-medium">$1</span>'
  )
  // 中文冒号 key：value（key 为中文/英文词）
  text = text.replace(
    /(\b[一-鿿\w]+)(：)/g,
    '<span class="text-slate-600">$1</span>$2'
  )
  return text
}

// ── 统一入口 ────────────────────────────────────────────────

/**
 * 智能高亮：JSON → 语法着色；非 JSON → 混合内容着色
 */
export function highlightContent(text) {
  if (!text) return ''
  try {
    JSON.parse(text)
    return highlightJSON(text)
  } catch {
    return highlightMixed(text)
  }
}

export default highlightContent
