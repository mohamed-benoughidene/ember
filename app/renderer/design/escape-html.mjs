/** Pure text-escaping for design component HTML (the prototype's esc). */
export function esc(value) {
  return String(value).replace(/[&<>"]/g, (ch) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[ch],
  );
}
