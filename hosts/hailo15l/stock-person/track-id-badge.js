/* Display only: actual tracker ID, inside the person's box. */
globalThis.drawPersonTrackId = function (ctx, detection, left, top) {
  if (detection.tracking_id == null) return;
  const ratio = ctx.canvas.width / (ctx.canvas.clientWidth || ctx.canvas.width);
  const padding = 8 * ratio;
  const text = `ID ${detection.tracking_id}`;
  const x = Math.max(0, Math.min(left + padding, ctx.canvas.width - 120 * ratio));
  const y = Math.max(0, Math.min(top + padding, ctx.canvas.height - 60 * ratio));
  ctx.save();
  ctx.font = `bold ${Math.round(36 * ratio)}px sans-serif`;
  const width = ctx.measureText(text).width + 2 * padding;
  const height = 52 * ratio;
  const safeX = Math.max(0, Math.min(x, ctx.canvas.width - width));
  ctx.fillStyle = 'rgba(0,0,0,0.85)';
  ctx.fillRect(safeX, y, width, height);
  ctx.fillStyle = '#ffffff';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, safeX + padding, y + height / 2);
  ctx.restore();
};
