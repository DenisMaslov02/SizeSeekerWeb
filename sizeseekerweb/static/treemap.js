/**
 * Squarified treemap layout (Bruls, Huizing, van Wijk).
 * `values` must be sorted descending and > 0. Returns one rect per value.
 */
export function squarify(values, x, y, width, height) {
  const total = values.reduce((a, b) => a + b, 0);
  if (!total || width <= 0 || height <= 0) return [];
  const areas = values.map((v) => (v / total) * width * height);
  const rects = [];
  let i = 0;
  while (i < areas.length) {
    const side = Math.min(width, height);
    const row = [areas[i]];
    let j = i + 1;
    while (j < areas.length && worst([...row, areas[j]], side) <= worst(row, side)) {
      row.push(areas[j]);
      j += 1;
    }
    const sum = row.reduce((a, b) => a + b, 0);
    if (width >= height) {
      const colWidth = sum / height;
      let cy = y;
      for (const area of row) {
        const h = area / colWidth;
        rects.push({ x, y: cy, w: colWidth, h });
        cy += h;
      }
      x += colWidth;
      width -= colWidth;
    } else {
      const rowHeight = sum / width;
      let cx = x;
      for (const area of row) {
        const w = area / rowHeight;
        rects.push({ x: cx, y, w, h: rowHeight });
        cx += w;
      }
      y += rowHeight;
      height -= rowHeight;
    }
    i = j;
  }
  return rects;
}

function worst(row, side) {
  let sum = 0;
  let max = -Infinity;
  let min = Infinity;
  for (const a of row) {
    sum += a;
    if (a > max) max = a;
    if (a < min) min = a;
  }
  const s2 = sum * sum;
  const w2 = side * side;
  return Math.max((w2 * max) / s2, s2 / (w2 * min));
}
