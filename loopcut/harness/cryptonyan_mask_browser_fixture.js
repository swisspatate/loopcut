// SPDX-License-Identifier: GPL-3.0-or-later
// Actual editor event handlers under a small deterministic DOM/canvas double.
const fs = require("node:fs"), vm = require("node:vm");
const request = JSON.parse(fs.readFileSync(0,"utf8"));
const script = fs.readFileSync(process.argv[2],"utf8");
(async function () {
  if (request.mode === "raster") {
    const context = vm.createContext({}); vm.runInContext(script,context);
    const results = request.projects.map(project => {
      try {return {pixels:Array.from(context.CryptoNyanMask.render(project))};}
      catch(error) {return {error:error.message};}
    });
    process.stdout.write(JSON.stringify(results)); return;
  }
  const elements = {}, clicks = [];
  let saved = null;
  function element(id) {
    const events = {};
    return elements[id] = {value:({mode:"paint",radius:"2",value:"255",intent:""})[id] || "",
      events, addEventListener:(type,handler)=>{events[type]=handler;},
      getBoundingClientRect:()=>({left:0,top:0,width:400,height:200}),setPointerCapture:()=>{},
      getContext:()=>({drawImage:()=>{},putImageData:image=>{elements[id].lastImage=image;}}),
      click:()=>{clicks.push(id);}};
  }
  for (const id of ["paint","reference","status","intent","mode","radius","value","undo","redo","save","load"]) element(id);
  const context = vm.createContext({CRYPTONYAN_DATA:{project:request.project,image:"fixture"},structuredClone,
    document:{getElementById:id=>elements[id],createElement:()=>({click:()=>clicks.push("download")})},
    Image:class {set src(value) {this.onload();}},
    ImageData:class {constructor(w,h){this.data=new Uint8ClampedArray(w*h*4);}},
    Blob:class {constructor(parts){this.parts=parts;}},URL:{createObjectURL:blob=>{saved=JSON.parse(blob.parts[0]);return "blob:fixture";},revokeObjectURL:()=>{}},
    setTimeout:handler=>handler()});
  vm.runInContext(script,context);
  const fire=(type,x,y)=>elements.paint.events[type]({button:0,pointerId:1,clientX:x,clientY:y});
  fire("pointerdown",100,100);fire("pointermove",300,100);fire("pointerup",300,100);
  elements.undo.onclick();elements.save.onclick();const afterUndo=structuredClone(saved);
  elements.redo.onclick();elements.save.onclick();const afterRedo=structuredClone(saved);
  elements.mode.value="erase";elements.radius.value="1";
  fire("pointerdown",200,100);fire("pointerup",200,100);
  elements.intent.value="Neige sur le toit";elements.intent.events.input();
  elements.save.onclick();const painted=structuredClone(saved);
  const invalid=structuredClone(request.project);invalid.reference.sha256="f".repeat(64);
  await elements.load.onchange({target:{files:[{size:100,text:async()=>JSON.stringify(invalid)}]}});
  elements.save.onclick();
  process.stdout.write(JSON.stringify({afterUndo,afterRedo,painted,afterWrongReference:saved,clicks,
    pixels:Array.from(context.CryptoNyanMask.render(painted))}));
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
