const STORAGE_KEY = 'yuanbao.acceptance.v2';
const LEGACY_STORAGE_KEY = 'yuanbao.acceptance.v1';
const HOST_KEY = 'yuanbao.acceptance.host.v1';
const API_KEY_STORAGE = 'yuanbao.acceptance.sync-key.v1';
const API_PATH = '/acceptance';
const IMPLEMENTATION_LABELS = {
  implemented: '已实现', 'requires-config': '需配置', 'platform-pending': '平台待验证',
  partial: '部分实现', 'not-implemented': '未实现', 'optional-last': '最后阶段可选',
};
const RESULT_LABELS = { 'not-run':'未测试', pass:'通过', fail:'失败', blocked:'阻塞', na:'不适用' };
const FIELD_LABELS = {
  result: '测试结果', notes: '备注', 'evidence.add': '新增证据', 'evidence.remove': '删除证据',
  'meta.environment': '测试环境', 'meta.deploymentId': 'Deployment ID', 'meta.tester': '测试人',
};
let cases = [];
let saved = loadSaved();
let host = loadHost();
let syncBusy = false;
let remoteAvailable = false;
let writeProtected = false;
const notesTimers = new Map();

function defaultState() {
  return { schemaVersion:2, revision:0, meta:{ environment:'preview', deploymentId:'', tester:'' }, cases:{}, audit:[], updatedAt:'' };
}
function loadJson(key, fallback) { try { return JSON.parse(localStorage.getItem(key) || '') || fallback; } catch { return fallback; } }
function loadSaved() {
  const current = loadJson(STORAGE_KEY, null);
  if (current) return { ...defaultState(), ...current, meta:{...defaultState().meta,...(current.meta||{})}, cases:current.cases||{}, audit:current.audit||[] };
  const legacy = loadJson(LEGACY_STORAGE_KEY, null);
  return legacy ? { ...defaultState(), meta:{...defaultState().meta,...(legacy.meta||{})}, cases:legacy.cases||{} } : defaultState();
}
function loadHost() {
  const current = loadJson(HOST_KEY, null);
  if (current?.hostId) return current;
  const hostId = crypto.randomUUID();
  const platform = navigator.userAgentData?.platform || navigator.platform || '浏览器';
  return { hostId, hostName:`${platform} · ${hostId.slice(0, 6)}` };
}
function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  localStorage.setItem(HOST_KEY, JSON.stringify(host));
  updateSummary();
}
function esc(value) { return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function list(items, ordered=false) {
  const values = Array.isArray(items) ? items : [];
  const tag = ordered ? 'ol' : 'ul';
  return `<${tag}>${values.map(item=>`<li>${esc(item)}</li>`).join('')}</${tag}>`;
}
function formatTime(value) {
  if (!value) return '暂无';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? esc(value) : new Intl.DateTimeFormat('zh-CN',{dateStyle:'short',timeStyle:'medium'}).format(date);
}
function formatBytes(size) {
  const value = Number(size || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024*1024) return `${(value/1024).toFixed(1)} KB`;
  return `${(value/1024/1024).toFixed(1)} MB`;
}
function withEdgeOneAuth(path) {
  const current = new URLSearchParams(location.search);
  const token = current.get('eo_token');
  const time = current.get('eo_time');
  if (!token || !time) return path;
  const url = new URL(path, location.href);
  url.searchParams.set('eo_token', token);
  url.searchParams.set('eo_time', time);
  return `${url.pathname}${url.search}${url.hash}`;
}
function record(id) {
  return { result:'not-run', notes:'', evidence:[], updatedAt:'', updatedByHostId:'', updatedByHostName:'', updatedByTester:'', ...(saved.cases?.[id]||{}) };
}
function caseHistory(id) { return (saved.audit||[]).filter(item=>item.caseId===id).slice(0, 30); }
function identity() { return { hostId:host.hostId, hostName:host.hostName, tester:document.querySelector('#tester')?.value.trim()||saved.meta.tester||'' }; }
function apiHeaders() {
  const key = document.querySelector('#sync-key')?.value || localStorage.getItem(API_KEY_STORAGE) || '';
  return { 'Content-Type':'application/json', ...(key ? {'X-Acceptance-Key':key} : {}) };
}
async function api(body) {
  const response = await fetch(withEdgeOneAuth(API_PATH), {
    method:body ? 'POST' : 'GET', credentials:'same-origin', headers:body ? apiHeaders() : undefined,
    body:body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json().catch(()=>({}));
  if (!response.ok) {
    const error = new Error(payload.error || `同步失败（HTTP ${response.status}）`);
    error.status = response.status; error.payload = payload; throw error;
  }
  return payload;
}
function setSyncStatus(kind, message) {
  const node = document.querySelector('#sync-status');
  if (!node) return;
  node.className = `sync-status ${kind}`;
  node.textContent = message;
}
function applyRemote(state) {
  saved = { ...defaultState(), ...state, meta:{...defaultState().meta,...(state.meta||{})}, cases:state.cases||{}, audit:state.audit||[] };
  persist();
  fillMeta();
  render();
}
async function refreshRemote(showMessage=true) {
  if (syncBusy) return;
  syncBusy = true;
  setSyncStatus('syncing','正在从 Makers Blob 同步…');
  try {
    const state = await api();
    writeProtected = Boolean(state.writeProtected);
    remoteAvailable = true;
    applyRemote(state);
    setSyncStatus('online',`已同步 · 版本 ${saved.revision} · ${formatTime(saved.updatedAt)}`);
    document.querySelector('#security-note').textContent = writeProtected ? '服务端已启用同步密钥保护。' : '当前未设置同步密钥；仅应在受保护的 Preview 使用。';
    if (showMessage) toast('已取得其他主机的最新记录');
  } catch (error) {
    remoteAvailable = false;
    setSyncStatus('offline',`离线模式：${error.message}；文本仍保存在本机`);
  } finally { syncBusy = false; }
}
function safetyFor(test) {
  const safety = test.safety || {};
  const destructive = ['CORE-08','SEARCH-03','PRO-08','SEC-02','AUTH-03','CONNECT-01'].includes(test.id);
  return {
    environment: safety.environment || (destructive ? '仅 Preview / 本地，不得在 Production 制造故障' : '优先 Preview；Production 只做只读回归'),
    impact: safety.impact || (destructive ? '使用专用测试会话、测试数据或临时无效配置；禁止修改生产 Provider、密钥和正式数据' : '只操作带 TEST- 前缀的测试数据，完成后按清理步骤恢复'),
    rollback: safety.rollback || '测试后删除 TEST- 数据，关闭为测试临时打开的面板，并确认页面恢复正常。',
  };
}
function evidenceMarkup(test, current) {
  const items = current.evidence || [];
  const files = items.length ? items.map(item=>`<li>
    <a href="${esc(withEdgeOneAuth(item.contentUrl || `${API_PATH}?evidence=${encodeURIComponent(item.key)}`))}" target="_blank" rel="noopener">${esc(item.kind==='video'?'🎬':'🖼️')} ${esc(item.name)}</a>
    <small>${esc(formatBytes(item.size))} · ${esc(item.uploadedByHostName||'未知主机')} · ${esc(formatTime(item.uploadedAt))}</small>
    <button class="link danger" type="button" data-remove-evidence="${esc(test.id)}" data-evidence-id="${esc(item.id)}">删除</button>
  </li>`).join('') : '<li class="muted-text">尚未上传证据</li>';
  return `<div class="evidence-box">
    <label class="upload-button">上传图片/视频<input type="file" accept="image/*,video/*" multiple data-evidence="${esc(test.id)}" /></label>
    <small>图片 ≤20MB，视频 ≤100MB；文件保存到 Makers Blob。</small>
    <ul class="evidence-list">${files}</ul>
  </div>`;
}
function historyMarkup(test, current) {
  const history = caseHistory(test.id);
  const last = current.updatedAt ? `${current.updatedByHostName||'未知主机'} · ${current.updatedByTester||'未填测试人'} · ${formatTime(current.updatedAt)}` : '暂无编辑';
  const rows = history.length ? history.map(item=>`<li><b>${esc(FIELD_LABELS[item.field]||item.field)}</b> · ${esc(item.hostName||'未知主机')} · ${esc(item.tester||'未填测试人')}<br><small>${esc(formatTime(item.editedAt))}${item.source==='import'?' · JSON 导入':''}</small></li>`).join('') : '<li class="muted-text">暂无历史</li>';
  return `<details class="history"><summary>编辑记录（${history.length}）</summary><p>最后编辑：${esc(last)}</p><ul>${rows}</ul></details>`;
}
function row(test) {
  const current = record(test.id);
  const safety = safetyFor(test);
  return `<tr data-id="${esc(test.id)}">
    <td><span class="case-id">${esc(test.id)}</span><span class="module">${esc(test.module)}</span></td>
    <td><strong class="title">${esc(test.title)}</strong><div class="scope">${esc(test.scope)}</div></td>
    <td><span class="pill ${esc(test.implementation)}">${esc(IMPLEMENTATION_LABELS[test.implementation])}</span>${test.releaseBlocker?'<span class="blocker">生产阻断</span>':''}</td>
    <td><div class="detail-grid">
      <div class="detail safety full"><b>执行环境与生产安全</b><ul><li><strong>环境：</strong>${esc(safety.environment)}</li><li><strong>隔离：</strong>${esc(safety.impact)}</li><li><strong>恢复：</strong>${esc(safety.rollback)}</li></ul></div>
      <div class="detail"><b>前置条件</b>${list(test.preconditions)}</div>
      <div class="detail"><b>测试数据</b>${list(test.data)}</div>
      <div class="detail full"><b>控制台 / 网页详细操作</b>${list(test.steps,true)}</div>
      <div class="detail full"><b>逐项核对的预期结果</b>${list(test.expected)}</div>
      <div class="detail full"><b>应保留的证据</b>${list(test.evidence)}</div>
      ${test.cleanup?.length ? `<div class="detail cleanup full"><b>测试后清理</b>${list(test.cleanup,true)}</div>` : ''}
    </div></td>
    <td><select class="result-select ${esc(current.result)}" data-result="${esc(test.id)}">${Object.entries(RESULT_LABELS).map(([value,label])=>`<option value="${value}" ${current.result===value?'selected':''}>${label}</option>`).join('')}</select></td>
    <td><textarea data-notes="${esc(test.id)}" placeholder="只写实际现象、错误信息、请求 ID 和复现条件；证据文件请在右侧上传。">${esc(current.notes)}</textarea><small class="save-hint">离开输入框时自动同步</small></td>
    <td>${evidenceMarkup(test,current)}${historyMarkup(test,current)}</td>
  </tr>`;
}
function filtered() {
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
function bindRows() {
  document.querySelectorAll('[data-result]').forEach(el=>el.addEventListener('change',event=>{
    event.target.className=`result-select ${event.target.value}`;
    void saveRecord(event.target.dataset.result,{result:event.target.value});
  }));
  document.querySelectorAll('[data-notes]').forEach(el=>{
    el.addEventListener('input',event=>{
      const id=event.target.dataset.notes; clearTimeout(notesTimers.get(id));
      notesTimers.set(id,setTimeout(()=>{notesTimers.delete(id);void saveRecord(id,{notes:event.target.value.trim()});},700));
    });
    el.addEventListener('change',event=>{
      const id=event.target.dataset.notes; clearTimeout(notesTimers.get(id));notesTimers.delete(id);
      void saveRecord(id,{notes:event.target.value.trim()});
    });
  });
  document.querySelectorAll('[data-evidence]').forEach(el=>el.addEventListener('change',event=>void uploadEvidence(event.target.dataset.evidence,[...event.target.files]).finally(()=>{event.target.value='';})));
  document.querySelectorAll('[data-remove-evidence]').forEach(el=>el.addEventListener('click',event=>void removeEvidence(event.target.dataset.removeEvidence,event.target.dataset.evidenceId)));
}
function render() {
  const visible=filtered();
  document.querySelector('#case-body').innerHTML=visible.map(row).join('');
  document.querySelector('#empty-state').hidden=visible.length!==0;
  bindRows();
}
function updateSummary() {
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
async function saveRecord(id,patch) {
  const current=record(id); const optimistic={...current,...patch,updatedAt:new Date().toISOString(),updatedByHostId:host.hostId,updatedByHostName:host.hostName,updatedByTester:identity().tester};
  saved.cases={...(saved.cases||{}),[id]:optimistic}; persist(); updateSummary(); setSyncStatus('syncing',`${id} 正在保存…`);
  try {
    const payload=await api({operation:'saveCase',caseId:id,patch,baseUpdatedAt:current.updatedAt,...identity()});
    remoteAvailable=true; applyRemote(payload.state); setSyncStatus('online',`${id} 已保存 · 版本 ${saved.revision}`);
  } catch(error) {
    if(error.status===409&&error.payload?.record){saved.cases[id]=error.payload.record;persist();render();}
    setSyncStatus('offline',`${id} 未同步：${error.message}`);
    toast(error.status===409?'另一台主机刚刚修改了此用例，已载入服务端版本，请重新填写。':`保存失败，内容仍保存在本机：${error.message}`,true);
  }
}
function collectMeta() { return { environment:document.querySelector('#environment').value, deploymentId:document.querySelector('#deployment-id').value.trim(), tester:document.querySelector('#tester').value.trim() }; }
async function saveMeta() {
  saved.meta=collectMeta(); persist();
  try { const payload=await api({operation:'saveMeta',meta:saved.meta,...identity()}); remoteAvailable=true; applyRemote(payload.state); setSyncStatus('online',`运行信息已同步 · 版本 ${saved.revision}`); }
  catch(error){setSyncStatus('offline',`运行信息仅保存在本机：${error.message}`);}
}
function fillMeta() {
  document.querySelector('#environment').value=saved.meta.environment||'preview';
  document.querySelector('#deployment-id').value=saved.meta.deploymentId||'';
  document.querySelector('#tester').value=saved.meta.tester||'';
  document.querySelector('#host-name').value=host.hostName||'';
  document.querySelector('#host-id').textContent=host.hostId;
}
async function uploadEvidence(caseId,files) {
  if(!files.length)return;
  if(!remoteAvailable){toast('证据必须上传到 Makers Blob；请先恢复在线同步。',true);return;}
  for(const file of files){
    setSyncStatus('syncing',`${caseId} 正在上传 ${file.name}…`);
    try{
      const signed=await api({operation:'createUpload',caseId,name:file.name,contentType:file.type,size:file.size,...identity()});
      const uploaded=await fetch(signed.url,{method:'PUT',headers:{'Content-Type':file.type},body:file});
      if(!uploaded.ok)throw new Error(`Blob 直传失败（HTTP ${uploaded.status}）`);
      const payload=await api({operation:'attachEvidence',caseId,evidence:signed.evidence,...identity()});
      applyRemote(payload.state); setSyncStatus('online',`${file.name} 已持久化到 Makers Blob`);
    }catch(error){setSyncStatus('offline',`${file.name} 上传失败：${error.message}`);toast(error.message,true);}
  }
}
async function removeEvidence(caseId,evidenceId) {
  if(!confirm('确认删除这份证据？该操作会同时删除 Makers Blob 中的文件，无法恢复。'))return;
  try{const payload=await api({operation:'removeEvidence',caseId,evidenceId,...identity()});applyRemote(payload.state);setSyncStatus('online','证据已删除并记录审计');}
  catch(error){toast(`删除失败：${error.message}`,true);}
}
function exportResults() {
  saved.meta=collectMeta();persist();
  const payload={schemaVersion:2,exportedAt:new Date().toISOString(),revision:saved.revision,...saved.meta,host,cases:cases.map(test=>({id:test.id,module:test.module,title:test.title,releaseBlocker:test.releaseBlocker,implementation:test.implementation,...record(test.id)})),audit:saved.audit||[]};
  const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`yuanbao-acceptance-${Date.now()}.json`;link.click();URL.revokeObjectURL(link.href);
}
async function importFile(file) {
  if(!file)return;
  try{
    const payload=JSON.parse(await file.text());
    const result=await api({operation:'import',payload,...identity()});
    applyRemote(result.state);setSyncStatus('online',`已导入 ${result.imported} 条记录并同步`);toast(`导入完成：${result.imported} 条用例发生变化`);
  }catch(error){toast(`导入失败：${error.message}`,true);}
}
function toast(message,isError=false){const node=document.querySelector('#toast');node.textContent=message;node.className=`toast ${isError?'error':''} show`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.classList.remove('show'),4200);}
async function boot() {
  const response=await fetch('./cases.json'); cases=await response.json();
  const modules=[...new Set(cases.map(test=>test.module))];document.querySelector('#module-filter').innerHTML+=modules.map(value=>`<option value="${esc(value)}">${esc(value)}</option>`).join('');
  fillMeta();document.querySelector('#sync-key').value=localStorage.getItem(API_KEY_STORAGE)||'';
  ['search','module-filter','implementation-filter','result-filter','blocker-only'].forEach(id=>document.querySelector(`#${id}`).addEventListener(id==='search'?'input':'change',render));
  ['environment','deployment-id','tester'].forEach(id=>document.querySelector(`#${id}`).addEventListener('change',()=>void saveMeta()));
  document.querySelector('#host-name').addEventListener('change',event=>{host.hostName=event.target.value.trim()||`未命名主机 · ${host.hostId.slice(0,6)}`;persist();render();});
  document.querySelector('#sync-key').addEventListener('change',event=>{localStorage.setItem(API_KEY_STORAGE,event.target.value);void refreshRemote(false);});
  document.querySelector('#refresh').addEventListener('click',()=>void refreshRemote());
  document.querySelector('#export').addEventListener('click',exportResults);
  document.querySelector('#import').addEventListener('click',()=>document.querySelector('#import-file').click());
  document.querySelector('#import-file').addEventListener('change',event=>void importFile(event.target.files[0]).finally(()=>{event.target.value='';}));
  document.querySelector('#reset').addEventListener('click',()=>{if(confirm('只清空当前浏览器缓存？Makers Blob 上的共享记录和证据不会删除。')){localStorage.removeItem(STORAGE_KEY);saved=defaultState();fillMeta();render();updateSummary();void refreshRemote(false);}});
  render();updateSummary();await refreshRemote(false);
}
boot().catch(error=>{document.querySelector('#case-body').innerHTML=`<tr><td colspan="7">测试用例载入失败：${esc(error.message)}</td></tr>`;setSyncStatus('offline',error.message);});
