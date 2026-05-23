const demo = {
  score: {D: 5.2, E: 17.4, T: 15.86, total: 38.46, deduction: 0.7},
  deductions: [
    {v: "0.3", text: "第4跳落点偏右", tag: "落点", cls: "orange"},
    {v: "0.3", text: "后半套姿态打开略不足", tag: "完成分", cls: "orange"},
    {v: "0.1", text: "空中姿态保持基本稳定", tag: "完成分", cls: "green"}
  ],
  times: [1.09,1.18,1.25,1.11,1.28,1.21,1.26,1.20,null,null],
  landings: [
    [46,49],[54,38],[62,42],[66,57],[57,58],[62,65],[60,48],[58,51]
  ],
  jumps: [
    ["1","后直体跳","2.0","16.7","14.80","33.50","+0.03 m","✓"],
    ["2","前空翻团身","5.0","17.3","15.40","37.70","+0.05 m","✓"],
    ["3","后空翻团身","5.2","17.5","16.10","38.80","-0.02 m","✓"],
    ["4","巴拉尼","5.0","17.1","15.20","37.30","+0.18 m","!"],
    ["5","后直体跳","2.0","16.8","14.70","33.50","+0.04 m","✓"],
    ["6","前空翻团身","5.0","17.2","15.60","37.80","-0.01 m","✓"],
    ["7","后空翻团身","5.2","17.4","16.00","38.60","-0.03 m","✓"],
    ["8","巴拉尼","5.0","17.4","15.86","38.46","+0.12 m","进行中"],
    ["9","后直体跳","-","-","-","-","-","待完成"],
    ["10","前空翻团身","-","-","-","-","-","待完成"]
  ]
};

const $ = id => document.getElementById(id);
const stage = document.querySelector(".app-shell");
const videoContainer = $("video-container");
const canvas = $("analysis-canvas");
const ctx = canvas.getContext("2d");
let cornerPoints = [];
let calibrationActive = true;
let toastTimer;

function toast(message){
  const node = $("toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 2600);
}
function resizeCanvas(){
  const r = videoContainer.getBoundingClientRect();
  canvas.width = Math.round(r.width);
  canvas.height = Math.round(r.height);
  drawCorners();
}
function drawCorners(){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if(!cornerPoints.length) return;
  ctx.lineWidth = 3;
  ctx.strokeStyle = "#28e7c0";
  ctx.fillStyle = "rgba(33,104,243,.16)";
  if(cornerPoints.length > 1){
    ctx.beginPath();
    ctx.moveTo(cornerPoints[0].x,cornerPoints[0].y);
    cornerPoints.slice(1).forEach(p => ctx.lineTo(p.x,p.y));
    if(cornerPoints.length === 4){ctx.closePath();ctx.fill();}
    ctx.stroke();
  }
  const labels = ["前左","前右","后右","后左"];
  cornerPoints.forEach((p,i)=>{
    ctx.beginPath(); ctx.arc(p.x,p.y,7,0,Math.PI*2);
    ctx.fillStyle = "#20e9bd"; ctx.fill();
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = "#ffffff"; ctx.font = "bold 12px Microsoft YaHei";
    ctx.fillText(`${i+1} ${labels[i]}`,p.x+10,p.y-10);
  });
}
function updateCornerState(){
  $("corner-count").textContent = `${cornerPoints.length}/4`;
  const labels = ["前左","前右","后右","后左"];
  $("corner-next").textContent = cornerPoints.length < 4 ? `下一点：${labels[cornerPoints.length]}` : "角点完整，可开始分析";
  $("start-trampoline-analysis").disabled = cornerPoints.length !== 4;
  $("calibration-footer").textContent = cornerPoints.length === 4 ? "标定完成" : "标定中";
}
videoContainer.addEventListener("click", e=>{
  if(!calibrationActive || e.target.closest("button") || cornerPoints.length >= 4) return;
  const r = videoContainer.getBoundingClientRect();
  cornerPoints.push({x:e.clientX-r.left,y:e.clientY-r.top});
  drawCorners(); updateCornerState();
});

function setCalibrationMode(reset=false){
  calibrationActive = true;
  stage.dataset.analysisStage = "calibration";
  $("corner-marking-step").classList.remove("hidden");
  $("sequence-step").classList.add("hidden");
  $("workflow-title").textContent = "床面标定";
  $("show-calibration").classList.add("active");
  $("show-results").classList.remove("active");
  $("video-state-tag").textContent = "床面标定";
  $("frame-info").innerHTML = `<p>步骤：<strong>床面四角标定</strong></p><p>顺序：<strong>前左 → 前右 → 后右 → 后左</strong></p><p>点击视频标记角点</p>`;
  const chip = $("process-chip");
  chip.innerHTML = `<i class="dot amber"></i><span>等待标定</span>`;
  if(reset){cornerPoints=[];drawCorners();updateCornerState();}
  toast("当前为标定交互区域：请在视频画面中标记床面四角");
}
function buildChart(){
  const svg=$("flight-chart"), w=410,h=170,l=35,r=12,t=14,b=35;
  const cw=w-l-r,ch=h-t-b,x=i=>l+(cw/9)*i,y=v=>t+ch-(v/2)*ch;
  let out="";
  for(let i=0;i<=4;i++){
    const yy=t+ch/4*i, val=(2-i*.5).toFixed(1);
    out+=`<line class="chart-grid" x1="${l}" y1="${yy}" x2="${w-r}" y2="${yy}"/><text class="chart-label" x="4" y="${yy+4}">${val}</text>`;
  }
  out+=`<line class="chart-axis" x1="${l}" y1="${t}" x2="${l}" y2="${h-b}"/><line class="chart-axis" x1="${l}" y1="${h-b}" x2="${w-r}" y2="${h-b}"/>`;
  const pts=demo.times.map((v,i)=>v===null?null:{x:x(i),y:y(v),v}).filter(Boolean);
  out+=`<path class="chart-line" d="${pts.map((p,i)=>(i?"L":"M")+p.x+" "+p.y).join(" ")}"/>`;
  demo.times.forEach((v,i)=>{
    out+=`<text class="chart-label" x="${x(i)-3}" y="${h-16}">${i+1}</text>`;
    if(v===null) out+=`<circle class="chart-placeholder" cx="${x(i)}" cy="${y(1.18)}" r="3"/>`;
    else out+=`<circle class="chart-dot" cx="${x(i)}" cy="${y(v)}" r="4"/><text class="chart-value" x="${x(i)-11}" y="${y(v)-9}">${v.toFixed(2)}</text>`;
  });
  out+=`<text class="chart-label" x="${l}" y="${h-3}">跳次</text><text class="chart-label" x="${w/2-24}" y="${h-3}">— 腾空时间</text>`;
  svg.innerHTML=out;
}
function renderEmptyChart(){
  const original = demo.times.slice();
  demo.times = [null,null,null,null,null,null,null,null,null,null];
  buildChart();
  demo.times = original;
}
function renderLandings(){
  const bed=$("landing-map-bed");
  bed.querySelectorAll(".landing-dot").forEach(n=>n.remove());
  $("empty-landing").classList.add("hidden");
  demo.landings.forEach((p,i)=>{
    const dot=document.createElement("span");
    dot.className=`landing-dot${i===demo.landings.length-1?" current":""}`;
    dot.style.left=p[0]+"%"; dot.style.top=p[1]+"%";
    bed.appendChild(dot);
  });
}
function renderScore(){
  $("score-d").textContent=demo.score.D.toFixed(1);
  $("score-e").textContent=demo.score.E.toFixed(1);
  $("score-t").textContent=demo.score.T.toFixed(2);
  $("score-total").textContent=demo.score.total.toFixed(2);
  $("deduction-total").textContent=demo.score.deduction.toFixed(1);
  $("deduction-list").innerHTML=demo.deductions.map(d=>`<li><i class="point ${d.cls}"></i><b>${d.v}</b><span>${d.text}</span><em class="badge">${d.tag}</em></li>`).join("");
}
function clearScore(){
  ["score-d","score-e","score-t","score-total","deduction-total"].forEach(id=>$(id).textContent="--");
  $("deduction-list").innerHTML='<li class="empty">完成分析后生成评分明细</li>';
  $("landing-map-bed").querySelectorAll(".landing-dot").forEach(n=>n.remove());
  $("empty-landing").classList.remove("hidden");
  renderEmptyChart();
}
function renderTable(){
  $("jump-table-body").innerHTML=demo.jumps.map((row,i)=>`<tr class="${i===7?"active-row":""}">
   ${row.map((cell,j)=>{
       let cls="";
       if(j===6 && (i===3||i===7)) cls="warning";
       if(j===7 && cell==="✓") cls="ok";
       if(j===7 && cell==="进行中") cls="working";
       if(j===7 && cell==="!") cls="warning";
       return `<td class="${cls}">${cell}</td>`;
   }).join("")}</tr>`).join("");
}
function addLog(text){
  const now=new Date().toLocaleTimeString("zh-CN",{hour12:false});
  $("log-list").insertAdjacentHTML("afterbegin",`<p><time>${now}</time>${text}</p>`);
}
function showResult(){
  calibrationActive=false;
  stage.dataset.analysisStage="results";
  $("corner-marking-step").classList.add("hidden");
  $("sequence-step").classList.remove("hidden");
  $("workflow-title").textContent="动作序列";
  $("show-calibration").classList.remove("active");
  $("show-results").classList.add("active");
  $("video-state-tag").textContent="分析结果回放";
  $("frame-info").innerHTML=`<p>动作：<strong>后空翻团身</strong></p><p>阶段：<strong>腾空</strong></p><p>当前跳次：08 / 10</p>`;
  $("process-chip").innerHTML='<i class="dot green"></i><span>分析完成</span>';
  $("progress-fill").style.width="100%";
  $("progress-text").textContent="100%";
  $("progress-stage").textContent="分析完成，可查看逐跳结果与 AI 建议";
  $("calibration-footer").textContent="已完成";
  $("jump-count").textContent="8 / 10";
  renderScore(); renderLandings(); buildChart(); renderTable();
  $("ai-waiting").classList.add("hidden"); $("ai-content").classList.remove("hidden");
  addLog("视频分析完成，已生成落点、评分与 AI 分析建议。");
  toast("分析结果展示完成；“重新标定”按钮始终保留");
}
function runAnalysis(){
  if(cornerPoints.length !== 4){toast("请先标记 4 个床面角点，或点击“加载演示角点”");return;}
  let p=0;
  $("progress-stage").textContent="正在分析视频：跳次识别与评分计算";
  $("process-chip").innerHTML='<i class="dot blue"></i><span>处理中</span>';
  const timer=setInterval(()=>{
    p+=20;$("progress-fill").style.width=p+"%";$("progress-text").textContent=p+"%";
    if(p>=100){clearInterval(timer);showResult();}
  },160);
}
$("mock-points").addEventListener("click",()=>{
  resizeCanvas();
  const w=canvas.width,h=canvas.height;
  cornerPoints=[{x:w*.17,y:h*.73},{x:w*.82,y:h*.73},{x:w*.75,y:h*.90},{x:w*.24,y:h*.90}];
  drawCorners();updateCornerState();toast("已载入 4 个演示角点，可保存并开始分析");
});
$("reset-corners").addEventListener("click",()=>{cornerPoints=[];drawCorners();updateCornerState();});
$("start-trampoline-analysis").addEventListener("click",runAnalysis);
$("bottom-analyze").addEventListener("click",()=>{
  if(cornerPoints.length===4) runAnalysis(); else {setCalibrationMode();toast("开始分析前需要先完成床面四角标定");}
});
$("enter-calibration").addEventListener("click",()=>setCalibrationMode(false));
$("bottom-calibrate").addEventListener("click",()=>setCalibrationMode(false));
$("recalibrate").addEventListener("click",()=>setCalibrationMode(false));
$("show-calibration").addEventListener("click",()=>setCalibrationMode(false));
$("show-results").addEventListener("click",()=>{showResult();});
$("demo-result").addEventListener("click",()=>{showResult();});
$("reset-demo").addEventListener("click",()=>{
  setCalibrationMode(true);clearScore();$("progress-fill").style.width="0%";$("progress-text").textContent="0%";$("progress-stage").textContent="等待完成床面标定";
  $("ai-content").classList.add("hidden");$("ai-waiting").classList.remove("hidden");$("jump-count").textContent="0 / 10";
});
$("browse-btn").addEventListener("click",()=>$("video-input").click());
$("video-input").addEventListener("change",e=>{
 const file=e.target.files[0]; if(!file) return;
 const video=$("video-player"); video.src=URL.createObjectURL(file); video.classList.remove("hidden"); $("demo-frame").classList.add("hidden");
 $("filename").textContent=file.name; setCalibrationMode(true); toast("视频已载入，请暂停到合适帧后进行床面标定");
});
$("live-tab").addEventListener("click",()=>toast("正式工程中此按钮跳转实时裁判页 /；本预览聚焦离线视频分析"));
$("offline-tab").addEventListener("click",()=>toast("当前已处于离线视频分析页面"));
$("detail-analysis").addEventListener("click",()=>toast("可复用原项目 SSE 接口 /api/video/llm_analysis/<video_id> 输出详细解读"));
$("export-report").addEventListener("click",downloadReport);
$("download-json").addEventListener("click",downloadReport);
function downloadReport(){
 const report={mode:"offline_video_analysis",calibration_points:cornerPoints,score:demo.score,jumps:demo.jumps,generated_at:new Date().toISOString()};
 const blob=new Blob([JSON.stringify(report,null,2)],{type:"application/json;charset=utf-8"});
 const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="trampoline_video_analysis_demo_result.json";a.click();URL.revokeObjectURL(a.href);
 toast("已导出演示结果 JSON");
}
window.addEventListener("resize",resizeCanvas);
document.addEventListener("DOMContentLoaded",()=>{resizeCanvas();updateCornerState();clearScore();renderTable();});
