/* Embedded-viewer click bridge only; no requests to Hailo or tracker changes. */
(() => {
  if (window.parent === window) return;
  const project = new URL(location.href); project.port = '8099';
  const canvases = new WeakMap();
  let selection = {state:'none',id:null}, received = 0;
  window.addEventListener('message', event => {
    if (event.source !== window.parent || event.origin !== project.origin || event.data?.type !== 'garuda-selection') return;
    selection = event.data.selection || {state:'none',id:null}; received = performance.now();
  });
  const draw = globalThis.drawPersonTrackId;
  globalThis.drawPersonTrackId = (ctx, detection, left, top, sx, sy) => {
    draw(ctx,detection,left,top);
    if (detection.tracking_id == null || !Number.isFinite(sx) || !Number.isFinite(sy)) return;
    let items = canvases.get(ctx.canvas);
    if (!items) {
      items = new Map(); canvases.set(ctx.canvas,items);
      // Hailo's controls overlay is a sibling of Video-Container, not its child.
      // Capture on their common player container so overlay clicks reach us too.
      (ctx.canvas.closest?.('.Video-PlayerContainer') || ctx.canvas.parentElement || ctx.canvas).addEventListener('click', event => {
        const rect=ctx.canvas.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        const x=(event.clientX-rect.left)*ctx.canvas.width/rect.width;
        const y=(event.clientY-rect.top)*ctx.canvas.height/rect.height;
        const within=b=>x>=b.x && y>=b.y && x<=b.x+b.w && y<=b.y+b.h;
        const fresh=[...items.values()].filter(item=>performance.now()-item.at<150);
        const badges=fresh.filter(item=>within(item.badge));
        const hits=badges.length ? badges : fresh.filter(within);
        if (!hits.length) return;
        event.preventDefault(); event.stopPropagation();
        window.parent.postMessage(hits.length===1 ? {type:'garuda-person-click',id:hits[0].id} : {type:'garuda-person-ambiguous'},project.origin);
      },true);
    }
    const ratio=ctx.canvas.width/(ctx.canvas.clientWidth||ctx.canvas.width), padding=8*ratio;
    ctx.save(); ctx.font=`bold ${Math.round(36*ratio)}px sans-serif`;
    const bw=ctx.measureText(`ID ${detection.tracking_id}`).width+2*padding;
    const bx=Math.max(0,Math.min(left+padding,ctx.canvas.width-120*ratio,ctx.canvas.width-bw));
    const by=Math.max(0,Math.min(top+padding,ctx.canvas.height-60*ratio));
    const box={id:detection.tracking_id,x:left,y:top,w:(detection.bbox.xmax-detection.bbox.xmin)*sx,
      h:(detection.bbox.ymax-detection.bbox.ymin)*sy,at:performance.now(),badge:{x:bx,y:by,w:bw,h:52*ratio}};
    items.set(box.id,box);
    for(const [id,item] of items) if(performance.now()-item.at>150) items.delete(id);
    if(selection.state==='selected' && selection.id===box.id && performance.now()-received<500) {
      ctx.strokeStyle='#55bbff';ctx.lineWidth=5*ratio;ctx.strokeRect(left+2*ratio,top+2*ratio,Math.max(0,box.w-4*ratio),Math.max(0,box.h-4*ratio));
    }
    ctx.restore();
  };
})();
