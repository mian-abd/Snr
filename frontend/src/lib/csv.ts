export type CsvValue = string | number | null | undefined

const cell = (value: CsvValue) => {
  if (value == null) return ''
  const text = String(value)
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** Rows to CSV text (RFC 4180: quoted where needed, CRLF line ends). */
export const toCsv = (rows: CsvValue[][]) => `${rows.map((row) => row.map(cell).join(',')).join('\r\n')}\r\n`

/** Save text as a file in the browser (with a byte-order mark so spreadsheets read UTF-8). */
export function downloadText(name: string, text: string, type = 'text/csv;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([String.fromCharCode(0xfeff), text], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
