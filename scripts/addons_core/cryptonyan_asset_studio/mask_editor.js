// SPDX-License-Identifier: GPL-3.0-or-later
// The same integer-pixel replay contract as mask_paint.py, usable without a DOM.
(function (global) {
  "use strict";
  function exact(value, keys) {
    if (!value || typeof value !== "object" || Array.isArray(value) ||
        Object.keys(value).sort().join(",") !== [...keys].sort().join(",")) throw Error("Champs du tracé invalides");
  }
  function number(value, low, high, integer = false) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < low || value > high ||
        (integer && !Number.isInteger(value))) throw Error("Valeur du pinceau invalide");
  }
  function validate(project) {
    exact(project, ["schema", "reference", "intent", "strokes"]);
    if (project.schema !== "cryptonyan.mask-paint/1") throw Error("Version de tracé inconnue");
    exact(project.reference, ["sha256", "width", "height"]);
    if (typeof project.reference.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(project.reference.sha256)) throw Error("Référence invalide");
    number(project.reference.width, 1, 4096, true); number(project.reference.height, 1, 4096, true);
    if (project.reference.width * project.reference.height > 1048576) throw Error("Image trop grande");
    if (typeof project.intent !== "string" || [...project.intent].length > 512 || /[\x00-\x08\x0b-\x1f]/.test(project.intent)) throw Error("Intention invalide");
    if (!Array.isArray(project.strokes) || project.strokes.length > 128) throw Error("128 traits maximum");
    let total = 0;
    for (const stroke of project.strokes) {
      exact(stroke, ["mode", "radius_px", "value", "points"]);
      if (!["paint", "erase"].includes(stroke.mode)) throw Error("Outil inconnu");
      number(stroke.radius_px, 1, 128, true); number(stroke.value, 0, 255, true);
      if (!Array.isArray(stroke.points) || !stroke.points.length || stroke.points.length > 512) throw Error("512 points par trait maximum");
      total += stroke.points.length;
      if (total > 4096) throw Error("4096 points maximum");
      for (const point of stroke.points) {
        if (!Array.isArray(point) || point.length !== 2) throw Error("Position du pinceau invalide");
        point.forEach(v => number(v, 0, 1));
      }
    }
    return project;
  }
  function render(project) {
    validate(project);
    const {width, height} = project.reference;
    const mask = new Uint8Array(width * height);
    let work = 0;
    for (const stroke of project.strokes) {
      const radius = stroke.radius_px;
      const points = stroke.points.map(p => [p[0] * width, p[1] * height]);
      const segments = points.length === 1 ? [[points[0], points[0]]] : points.slice(1).map((p, i) => [points[i], p]);
      for (const [[ax, ay], [bx, by]] of segments) {
        const x0 = Math.max(0, Math.floor(Math.min(ax,bx)-radius)), x1 = Math.min(width-1, Math.floor(Math.max(ax,bx)+radius));
        const y0 = Math.max(0, Math.floor(Math.min(ay,by)-radius)), y1 = Math.min(height-1, Math.floor(Math.max(ay,by)+radius));
        work += (x1-x0+1)*(y1-y0+1);
        if (work > 33554432) throw Error("Tracé trop complexe : simplifier les traits");
        const dx = bx-ax, dy = by-ay, length2 = dx*dx+dy*dy;
        for (let y=y0; y<=y1; y++) for (let x=x0; x<=x1; x++) {
          const t = length2 ? Math.max(0, Math.min(1, ((x+.5-ax)*dx+(y+.5-ay)*dy)/length2)) : 0;
          if ((x+.5-ax-t*dx)**2+(y+.5-ay-t*dy)**2 <= radius*radius) mask[y*width+x] = stroke.mode === "erase" ? 0 : stroke.value;
        }
      }
    }
    return mask;
  }
  global.CryptoNyanMask = {validate, render};
  if (typeof document === "undefined") return;
  const initial = CRYPTONYAN_DATA.project;
  let project = structuredClone(initial), redo = [], active = null;
  const canvas = document.getElementById("paint"), background = document.getElementById("reference");
  const status = document.getElementById("status"), intent = document.getElementById("intent");
  canvas.width = background.width = initial.reference.width;
  canvas.height = background.height = initial.reference.height;
  function refresh() {
    try {
      const mask = render(project), image = new ImageData(canvas.width, canvas.height);
      for (let i=0; i<mask.length; i++) {
        image.data[i*4] = 255;
        image.data[i*4+1] = 80;
        image.data[i*4+3] = Math.round(mask[i] * .55);
      }
      canvas.getContext("2d").putImageData(image,0,0);
      status.textContent = project.strokes.length + " trait(s) ; rouge = zone à modifier. La valeur du masque reste en gris.";
    } catch (error) { status.textContent = error.message; }
  }
  const image = new Image();
  image.onload = () => { background.getContext("2d").drawImage(image,0,0); refresh(); };
  image.src = "data:image/png;base64," + CRYPTONYAN_DATA.image;
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return [Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)), Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];
  }
  function finish() { active = null; }
  canvas.addEventListener("pointerdown", event => {
    if (event.button !== 0 || active) return;
    const stroke = {mode:document.getElementById("mode").value, radius_px:Number(document.getElementById("radius").value),
                    value:Number(document.getElementById("value").value), points:[point(event)]};
    try {
      const candidate = {...project,strokes:[...project.strokes,stroke]};
      validate(candidate); render(candidate);
      project.strokes.push(stroke); active = stroke; redo = [];
      canvas.setPointerCapture(event.pointerId); refresh();
    } catch (error) { status.textContent = error.message; }
  });
  canvas.addEventListener("pointermove", event => {
    if (!active || active.points.length >= 512) return;
    const p = point(event), last = active.points[active.points.length-1];
    if (Math.hypot((p[0]-last[0])*canvas.width,(p[1]-last[1])*canvas.height) < 1) return;
    active.points.push(p);
    try { validate(project); render(project); } catch (error) { active.points.pop(); status.textContent=error.message; return; }
    refresh();
  });
  for (const event of ["pointerup","pointercancel","lostpointercapture"]) canvas.addEventListener(event,finish);
  intent.addEventListener("input", () => {project.intent=intent.value;});
  document.getElementById("undo").onclick = () => {finish(); if(project.strokes.length) redo.push(project.strokes.pop()); refresh();};
  document.getElementById("redo").onclick = () => {finish(); if(redo.length) project.strokes.push(redo.pop()); refresh();};
  document.getElementById("save").onclick = () => {
    try {
      validate(project); render(project);
      const url=URL.createObjectURL(new Blob([JSON.stringify(project,null,2)],{type:"application/json"}));
      const link=document.createElement("a"); link.href=url; link.download="cryptonyan-mask-strokes.json"; link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch(error) {status.textContent=error.message;}
  };
  document.getElementById("load").onchange = async event => {
    try {
      finish();
      const file=event.target.files[0]; if(!file) return;
      if(file.size>1048576) throw Error("Tracé trop grand");
      const incoming=validate(JSON.parse(await file.text()));
      if (incoming.reference.sha256 !== initial.reference.sha256 || incoming.reference.width !== initial.reference.width ||
          incoming.reference.height !== initial.reference.height) throw Error("Le tracé appartient à une autre image");
      render(incoming); project=incoming; redo=[]; intent.value=project.intent; refresh();
    } catch(error) {status.textContent=error.message;}
  };
})(globalThis);
