const STORAGE_KEY = 'yuanbao.acceptance.v1';
const IMPLEMENTATION_LABELS = {
  implemented: '已实现', 'requires-config': '需配置', 'platform-pending': '平台待验证',
  partial: '部分实现', 'not-implemented': '未实现', 'optional-last': '最后阶段可选',
};
const RESULT_LABELS = { 'not-run':'未测试', pass:'通过', fail:'失败', blocked:'阻塞', na:'不适用' };
let cases = [];
let saved = loadSaved();

function loadSaved(){ try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}')}catch{return{}} }
function persist(){ localStorage.setItem(STORAGE_KEY,JSON.stringify(saved)); updateSummary(); }
function esc(value){ return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function list(items,ordered=false){ const tag=ordered?'ol':'ul'; return `<${tag}>${items.map(item=>`<li>${esc(item)}</li>`).join('')}</${tag}>`; }
function record(id){ return saved.cases?.[id]||{result:'not-run',notes:''}; }
function saveRecord(id,patch){ saved.cases={...(saved.cases||{}),[id]:{...record(id),...patch,updatedAt:new Date().toISOString()}}; persist(); }

function row(test){
  const current=record(test.id);
  return `<tr data-id="${esc(test.id)}">
    <td><span class="case-id">${esc(test.id)}</span><span class="module">${esc(test.module)}</span></td>
    <td><strong class="title">${esc(test.title)}</strong><div class="scope">${esc(test.scope)}</div></td>
    <td><span class="pill ${esc(test.implementation)}">${esc(IMPLEMENTATION_LABELS[test.implementation])}</span>${test.releaseBlocker?'<span class="blocker">生产阻断</span>':''}</td>
    <td><div class="detail-grid">
      <div class="detail"><b>前置条件</b>${list(test.preconditions)}</div>
      <div class="detail"><b>测试数据</b>${list(test.data)}</div>
      <div class="detail full"><b>操作步骤</b>${list(test.steps,true)}</div>
      <div class="detail full"><b>预期结果</b>${list(test.expected)}</div>
      <div class="detail full"><b>需要保留的证据</b>${list(test.evidence)}</div>
    </div></td>
    <td><select class="result-select ${esc(current.result)}" data-result="${esc(test.id)}">${Object.entries(RESULT_LABELS).map(([value,label])=>`<option value="${value}" ${current.result===value?'selected':''}>${label}</option>`).join('')}</select></td>
    <td><textarea data-notes="${esc(test.id)}" placeholder="填写实际结果、请求 ID、截图名或问题描述">${esc(current.notes)}</textarea></td>
  </tr>`;
}

function filtered(){
  const query=document.querySelector('#search').value.trim().toLowerCase();
  const module=document.querySelector('#module-filter').value;
  const implementation=document.querySelector('#implementation-filter').value;
  const result=document.querySelector('#result-filter').value;
  const blockers=document.querySelector('#blocker-only').checked;
  return cases.filter(test=>{
    const haystack=JSON.stringify(test).toLowerCase();
    return (!query||haystack.includes(query))&&(!module||test.module===module)&&(!implementation||test.implementation===implementation)&&(!result||record(test.id).result===result)&&(!blockers||test.releaseBlocker);
  });
}
function render(){
  const visible=filtered(); document.querySelector('#case-body').innerHTML=visible.map(row).join('');
  document.querySelector('#empty-state').hidden=visible.length!==0;
  document.querySelectorAll('[data-result]').forEach(el=>el.addEventListener('change',e=>{e.target.className=`result-select ${e.target.value}`;saveRecord(e.target.dataset.result,{result:e.target.value});}));
  document.querySelectorAll('[data-notes]').forEach(el=>el.addEventListener('change',e=>saveRecord(e.target.dataset.notes,{notes:e.target.value.trim()})));
}
function updateSummary(){
  const results=cases.map(test=>record(test.id).result); const blockers=cases.filter(test=>test.releaseBlocker);
  const failed=results.filter(v=>v==='fail').length, passed=results.filter(v=>v==='pass').length;
  const blockersPassed=blockers.filter(test=>record(test.id).result==='pass').length;
  document.querySelector('#total-count').textContent=cases.length; document.querySelector('#blocker-count').textContent=blockers.length;
  document.querySelector('#passed-count').textContent=passed; document.querySelector('#failed-count').textContent=failed;
  document.querySelector('#pending-count').textContent=cases.length-passed-failed;
  const gate=document.querySelector('#gate-status'), detail=document.querySelector('#gate-detail');
  if(blockers.length&&blockersPassed===blockers.length){gate.textContent='可以申请生产发布';detail.textContent=`${blockersPassed}/${blockers.length} 项阻断用例通过`;}
  else{gate.textContent='禁止生产发布';detail.textContent=`阻断用例通过 ${blockersPassed}/${blockers.length}`;}
}
function saveMeta(){ saved.meta={environment:document.querySelector('#environment').value,deploymentId:document.querySelector('#deployment-id').value.trim(),tester:document.querySelector('#tester').value.trim()};persist(); }
function exportResults(){
  saveMeta(); const payload={schemaVersion:1,exportedAt:new Date().toISOString(),...saved.meta,cases:cases.map(test=>({id:test.id,module:test.module,title:test.title,releaseBlocker:test.releaseBlocker,implementation:test.implementation,...record(test.id)}))};
  const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}); const link=document.createElement('a'); link.href=URL.createObjectURL(blob); link.download=`yuanbao-acceptance-${Date.now()}.json`; link.click(); URL.revokeObjectURL(link.href);
}
async function boot(){
  const response=await fetch('./cases.json'); cases=await response.json();
  const modules=[...new Set(cases.map(test=>test.module))]; document.querySelector('#module-filter').innerHTML+=[...modules].map(value=>`<option value="${esc(value)}">${esc(value)}</option>`).join('');
  const meta=saved.meta||{}; document.querySelector('#environment').value=meta.environment||'preview'; document.querySelector('#deployment-id').value=meta.deploymentId||''; document.querySelector('#tester').value=meta.tester||'';
  ['search','module-filter','implementation-filter','result-filter','blocker-only'].forEach(id=>document.querySelector(`#${id}`).addEventListener(id==='search'?'input':'change',render));
  ['environment','deployment-id','tester'].forEach(id=>document.querySelector(`#${id}`).addEventListener('change',saveMeta));
  document.querySelector('#export').addEventListener('click',exportResults);
  document.querySelector('#reset').addEventListener('click',()=>{ if(confirm('只清空当前浏览器中的验收结果和备注，确认继续？')){saved={};localStorage.removeItem(STORAGE_KEY);location.reload();} });
  render(); updateSummary();
}
boot().catch(error=>{document.querySelector('#case-body').innerHTML=`<tr><td colspan="6">测试用例载入失败：${esc(error.message)}</td></tr>`;});
