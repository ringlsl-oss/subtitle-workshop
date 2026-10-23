'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="app-token"]').content;
const escapeHTML = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone = value => JSON.parse(JSON.stringify(value));
let project, profiles = [], selected = -1, history = [], future = [], saveTimer, toastTimer, saveQueue = Promise.resolve(), revision = 0, currentJob = null, modalResolve = null;
const video = $('video');
const defaultStyle = {font:'Microsoft YaHei',size:48,color:'#f5f5f2',outline:2,shadow:1,background:false,margin:60,position:'bottom'};
const styleKeys = Object.keys(defaultStyle);
let pendingEdits = false, savedStyle = null, outputsData = [], dataDirectory = '', rulesDirty = false;

async function api(path, body) {
  const response = await fetch('/api/' + path, {method:body === undefined ? 'GET':'POST',headers:{'X-App-Token':token,'Content-Type':'application/json'},body:body === undefined ? undefined:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作失败');
  return result;
}
function toast(message, duration=4500) { $('toast').textContent=message; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,duration); }
function report(error) { console.error(error); toast(error.message || String(error),8000); $('status').textContent='操作未完成：' + (error.message || error); }
function action(id, fn) { $(id).addEventListener('click', () => Promise.resolve().then(fn).catch(report)); }
function modal(title, html, confirm='确定') {
  if (modalResolve) modalResolve(null);
  $('modalTitle').textContent=title; $('modalBody').innerHTML=html; $('modalConfirm').textContent=confirm;
  $('modal').returnValue='cancel'; $('modal').showModal();
  return new Promise(resolve=>modalResolve=resolve);
}
$('modal').addEventListener('close',()=>{const done=modalResolve;modalResolve=null;if(done)done($('modal').returnValue==='ok' ? $('modalBody') : null);});
async function choose(kind, multiple=false, filename='') {
  if (window.pywebview?.api) return window.pywebview.api.choose(kind,multiple,filename);
  const body=await modal(filename?'选择保存位置':'选择本地文件',`<p>浏览器调试模式：输入完整文件路径。桌面版会打开系统文件选择窗口。</p><label>文件路径<textarea id="pathInput" rows="3" placeholder="E:\\视频\\作品.mp4"></textarea></label>${multiple?'<p>多个文件每行一个路径。</p>':''}`);
  return body ? $('pathInput').value.split('\n').map(v=>v.trim().replace(/^"|"$/g,'')).filter(Boolean) : [];
}
function checkpoint() { if(!project)return; history.push(clone(project)); if(history.length>80)history.shift(); future=[]; updateUndo(); }
function updateUndo() { $('undo').disabled=!history.length; $('redo').disabled=!future.length; }
function changed() { revision++; pendingEdits=true; $('saveStatus').textContent='正在保存…'; clearTimeout(saveTimer); saveTimer=setTimeout(save,600); updateTimeline(); updateOverlay(); }
function save() {
  clearTimeout(saveTimer); const snapshot=clone(project), rev=revision;
  saveQueue=saveQueue.catch(()=>{}).then(()=>api('project',snapshot)).then(()=>{if(rev===revision){pendingEdits=false;$('saveStatus').textContent='已自动保存';}}).catch(error=>{$('saveStatus').textContent='未保存 · 请检查字幕时间与内容';$('status').textContent=error.message;});
  return saveQueue;
}
function duration() { return Math.max(project?.media?.duration||0, ...((project?.cues||[]).map(c=>c.end)),1); }
function clock(sec) { sec=Math.max(0,Number(sec)||0);const m=Math.floor(sec/60),s=(sec%60).toFixed(2).padStart(5,'0');return `${String(m).padStart(2,'0')}:${s}`; }
function profile() { return profiles.find(p=>p.id===project.profile_id)||profiles[0]; }
function updateProfiles() {
  if(!profiles.some(p=>p.id===project.profile_id))project.profile_id=profiles[0].id;
  for(const id of ['profileSelect','memoryProfileSelect']){$(id).innerHTML=profiles.map(p=>`<option value="${escapeHTML(p.id)}">${escapeHTML(p.name)}</option>`).join('');$(id).value=project.profile_id;}
  renderMemory();
}
function renderMedia() {
  const media=project.media;
  $('mediaInfo').textContent=media?`${media.name} · ${media.has_video?`${media.width} × ${media.height}`:'音频'}`:'尚未导入素材';
  $('emptyStage').hidden=Boolean(media);$('audioStage').hidden=!media||media.has_video;
  $('compatPreview').hidden=true;
  if(media?.url){if(video.getAttribute('src')!==media.url){video.src=media.url;video.load();}}
  else {video.removeAttribute('src');video.load();}
  if(media&&!media.url){$('emptyStage').hidden=false;$('status').textContent='原始媒体文件已移动，请重新导入；字幕仍然保留。';}
}
function renderStyles() { for(const key of styleKeys){if(key==='background')$(key).checked=project.style[key];else $(key).value=project.style[key];}updateOverlay(); }
function renderAll() { $('projectName').value=project.name;updateProfiles();renderMedia();renderStyles();renderCues();updateTransport();updateUndo(); }
function selectCue(index, seek=false) {
  selected=index;
  document.querySelectorAll('.cue-row').forEach(row=>row.classList.toggle('selected',Number(row.dataset.index)===index));
  if(seek && project.cues[index]){video.currentTime=project.cues[index].start;$('seek').value=project.cues[index].start;updateOverlay(project.cues[index].start);updateTransport(project.cues[index].start);}
  updateTimeline();
}
function renderCues() {
  const list=$('cueList'), query=$('find').value;
  $('cueCount').textContent=`${project.cues.length} 条`;
  if(!project.cues.length){list.innerHTML='<div class="empty-list"><span>01</span><h3>字幕会出现在这里</h3><p>自动识别语音，或导入已有 SRT / ASS。</p><p>校对完成后，可将成稿加入断句习惯。</p></div>';selected=-1;updateTimeline();return;}
  list.innerHTML=project.cues.map((c,i)=>`<div class="cue-row ${selected===i?'selected':''}" data-index="${i}" ${query&&!c.text.includes(query)?'hidden':''}><div class="cue-index">${String(i+1).padStart(2,'0')}</div><div class="cue-content"><div class="cue-times"><input type="number" step="0.01" min="0" data-field="start" value="${c.start.toFixed(3)}" aria-label="第${i+1}条开始秒数"><span>→</span><input type="number" step="0.01" min="0" data-field="end" value="${c.end.toFixed(3)}" aria-label="第${i+1}条结束秒数"><small>${c.text.replace(/\n/g,'').length} 字</small></div><textarea rows="${Math.max(1,c.text.split('\n').length)}" aria-label="第${i+1}条字幕">${escapeHTML(c.text)}</textarea></div></div>`).join('');
  list.querySelectorAll('.cue-row').forEach(row=>{
    const i=Number(row.dataset.index);
    row.addEventListener('click',event=>selectCue(i,event.target.tagName!=='INPUT'&&event.target.tagName!=='TEXTAREA'));
    row.querySelectorAll('input,textarea').forEach(input=>{
      input.addEventListener('focus',()=>{checkpoint();selectCue(i);});
      input.addEventListener('input',()=>{
        if(input.tagName==='TEXTAREA'){project.cues[i].text=input.value;delete project.cues[i].words;row.querySelector('small').textContent=input.value.replace(/\n/g,'').length+' 字';}
        else {project.cues[i][input.dataset.field]=Number(input.value);delete project.cues[i].words;}
        const c=project.cues[i];row.classList.toggle('mismatch',c.start<0||c.end<=c.start||(i>0&&c.start<project.cues[i-1].end)||!c.text.trim());changed();
      });
    });
  });
  updateTimeline();updateOverlay();
}
function updateTimeline() {
  const total=duration();
  $('timelineCues').innerHTML=project.cues.map((c,i)=>`<button class="timeline-block ${i===selected?'selected':''}" style="left:${100*c.start/total}%;width:${Math.max(.2,100*(c.end-c.start)/total)}%" data-index="${i}" title="${escapeHTML(c.text)}">${escapeHTML(c.text)}</button>`).join('');
  $('timelineCues').querySelectorAll('button').forEach(button=>button.onclick=()=>{selectCue(Number(button.dataset.index),true);document.querySelector(`.cue-row[data-index="${selected}"]`)?.scrollIntoView({block:'nearest'});});
  $('seek').max=total;updateTransport();
}
function updateTransport(time=video.currentTime||Number($('seek').value)||0) { $('timeLabel').textContent=`${clock(time)} / ${clock(duration())}`;$('seek').value=time;$('playhead').style.left=`${Math.min(100,time/duration()*100)}%`;$('play').textContent=video.paused?'▶':'Ⅱ'; }
function updateOverlay(time=video.currentTime||Number($('seek').value)||0) {
  if(!project)return;
  const index=project.cues.findIndex(c=>c.start<=time&&c.end>time), cue=project.cues[index], el=$('subtitleOverlay'), style=project.style;
  el.replaceChildren();if(cue){const span=document.createElement('span');span.textContent=cue.text;span.style.background=style.background?'rgba(16,16,16,.65)':'transparent';span.style.padding=style.background?'1px 5px':'0';el.append(span);}
  const media=project.media, width=media?.width||1920,height=media?.height||1080;
  const bounds=$('stage').getBoundingClientRect(),scale=Math.min(bounds.width/width,bounds.height/height), renderedHeight=height*scale, renderedWidth=width*scale,offsetY=(bounds.height-renderedHeight)/2;
  el.style.fontFamily=style.font;el.style.fontSize=`${style.size*scale}px`;el.style.color=style.color;el.style.width=`${renderedWidth*.94}px`;el.style.left=`${(bounds.width-renderedWidth*.94)/2}px`;
  el.style.webkitTextStroke=`${Number(style.outline)*scale}px #101010`;el.style.paintOrder='stroke fill';el.style.textShadow=style.shadow?`${style.shadow*scale}px ${style.shadow*scale}px ${style.shadow*scale}px #101010`:'none';
  el.style.bottom=style.position==='bottom'?`${offsetY+Number(style.margin)*scale}px`:'auto';el.style.top=style.position==='top'?`${offsetY+Number(style.margin)*scale}px`:style.position==='center'?'50%':'auto';el.style.transform=style.position==='center'?'translateY(-50%)':'none';
  document.querySelectorAll('.cue-row').forEach(row=>row.classList.toggle('playing',Number(row.dataset.index)===index));
}
function renderMemory() {
  const p=profile();if(!p)return;const r=p.rules,stats=p.stats;
  $('memoryStats').innerHTML=[['作品',p.samples.length],['字幕条数',stats.cue_count||0],['样本常用字数',stats.median_chars||'—']].map(([label,n])=>`<div class="stat"><strong>${n}</strong><span>${label}</span></div>`).join('');
  $('sampleList').innerHTML=p.samples.length?p.samples.map(s=>`<div class="sample-row"><strong>${escapeHTML(s.name)}</strong><span>${s.cues.length} 条 · 已学习</span></div>`).join(''):'<p class="hint">还没有历史样本。可以先使用默认规则，再导入成稿。</p>';
  $('ruleName').value=p.name;$('ruleSource').textContent=p.samples.length?'已学习 · 可调整':'默认规则';
  for(const [id,key] of Object.entries({targetChars:'target_chars',maxChars:'max_chars',lineChars:'line_chars',maxLines:'max_lines',pause:'pause'}))$(id).value=r[key];
  $('keepPunctuation').checked=r.keep_punctuation;$('protectedTerms').value=r.protected_terms.join('\n');
}
function setPage(page) { $('editorPage').hidden=page!=='editor';$('memoryPage').hidden=page!=='memory';$('outputsPage').hidden=page!=='outputs';document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));if(page==='memory')renderMemory();else if(page==='outputs')refreshOutputs().catch(report);else updateOverlay(); }
document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>setPage(b.dataset.page));
async function importMedia() {
  const paths=await choose('media');if(!paths.length)return;
  if(project.media&&project.cues.length){const yes=await modal('替换媒体','<p>替换媒体后会保留当前字幕。请确认新素材与字幕时间一致。</p>','替换媒体');if(!yes)return;}
  const result=await api('media',{path:paths[0]});checkpoint();project.media=result.media;if(project.name==='未命名项目')project.name=result.media.name.replace(/\.[^.]+$/,'');renderAll();changed();toast('素材已导入');
}
action('importMedia',importMedia);action('emptyImport',importMedia);
action('importSubs',async()=>{const paths=await choose('subtitles');if(!paths.length)return;if(project.cues.length&&!await modal('替换当前字幕','<p>将导入的字幕作为当前稿件。你可以通过撤销恢复。</p>','导入'))return;const result=await api('import-subtitles',{path:paths[0]});checkpoint();project.cues=result.cues;project.original_cues=clone(result.cues);selected=0;renderCues();changed();toast('已导入 '+result.cues.length+' 条字幕');});
action('demoButton',()=>{checkpoint();project.cues=[{start:0,end:3,text:'好的字幕\n应该跟得上说话的节奏'},{start:3,end:5.5,text:'也保留一句话的完整意思'},{start:5.5,end:8,text:'在这里修改文字和时间'},{start:8,end:11,text:'再把你确认的断句习惯记下来'}];project.original_cues=clone(project.cues);project.name='字幕编辑示例';selected=0;renderAll();changed();toast('这是编辑示例，尚未关联视频。可修改、拆分和导出字幕。');});
action('addCue',()=>{checkpoint();let start=video.currentTime||0;const next=project.cues.find(c=>c.start>=start);if(project.cues.some(c=>c.start<=start&&c.end>start)||(next&&next.start-start<.2))start=project.cues.at(-1)?.end||0;const following=project.cues.find(c=>c.start>start);const cue={start,end:Math.min(start+2,following?.start||Infinity),text:'请输入字幕'};project.cues.push(cue);project.cues.sort((a,b)=>a.start-b.start);selected=project.cues.indexOf(cue);renderCues();changed();document.querySelector(`.cue-row[data-index="${selected}"] textarea`)?.focus();});
let cursorPosition=null;
$('cueList').addEventListener('keyup',e=>{if(e.target.tagName==='TEXTAREA')cursorPosition=e.target.selectionStart;});
$('cueList').addEventListener('mouseup',e=>{if(e.target.tagName==='TEXTAREA')cursorPosition=e.target.selectionStart;});
action('splitCue',()=>{const cue=project.cues[selected];if(!cue)throw new Error('请先选中一条字幕');const pos=cursorPosition??Math.floor(cue.text.length/2);if(pos<=0||pos>=cue.text.length||!cue.text.slice(0,pos).trim()||!cue.text.slice(pos).trim())throw new Error('请把文字光标放在要拆分的位置');checkpoint();const split=Number((cue.start+(cue.end-cue.start)*pos/cue.text.length).toFixed(3));project.cues.splice(selected,1,{start:cue.start,end:split,text:cue.text.slice(0,pos)},{start:split,end:cue.end,text:cue.text.slice(pos)});cursorPosition=null;renderCues();changed();toast('已拆分，时间按字数估算，请试听校对');});
action('mergeCue',()=>{const a=project.cues[selected],b=project.cues[selected+1];if(!a||!b)throw new Error('请选择一条有后续字幕的条目');checkpoint();const space=/[a-z0-9]$/i.test(a.text)&&/^[a-z0-9]/i.test(b.text)?' ':'';project.cues.splice(selected,2,{start:a.start,end:b.end,text:a.text+space+b.text});renderCues();changed();});
action('deleteCue',()=>{if(selected<0)return;checkpoint();project.cues.splice(selected,1);selected=Math.min(selected,project.cues.length-1);renderCues();changed();});
action('shiftCue',async()=>{const body=await modal('整体调整时间','<p>正数延后，负数提前。单位为秒。</p><label>偏移秒数<input id="shiftAmount" type="number" value="0" step="0.1"></label>');if(!body)return;const offset=Number($('shiftAmount').value);if(!Number.isFinite(offset)||project.cues.some(c=>c.start+offset<0))throw new Error('偏移后不能出现负数时间');checkpoint();project.cues.forEach(c=>{c.start=Number((c.start+offset).toFixed(3));c.end=Number((c.end+offset).toFixed(3));if(c.words)c.words.forEach(w=>{w.start+=offset;w.end+=offset;});});renderCues();changed();});
action('replaceAll',()=>{const from=$('find').value,to=$('replace').value;if(!from)return;const matches=project.cues.filter(c=>c.text.includes(from));if(!matches.length)return toast('没有找到匹配文字');if(matches.some(c=>!c.text.replaceAll(from,to).trim()))throw new Error('替换会产生空字幕，请修改替换内容或单独删除条目');checkpoint();matches.forEach(c=>{c.text=c.text.replaceAll(from,to);delete c.words;});$('find').value='';renderCues();changed();toast(`已替换 ${matches.length} 条字幕`);});
$('find').addEventListener('input',renderCues);
action('undo',()=>{if(!history.length)return;future.push(clone(project));project=history.pop();selected=-1;renderAll();changed();});
action('redo',()=>{if(!future.length)return;history.push(clone(project));project=future.pop();selected=-1;renderAll();changed();});
$('projectName').addEventListener('change',()=>{checkpoint();project.name=$('projectName').value.trim()||'未命名项目';changed();});
for(const key of styleKeys){$(key).addEventListener('change',()=>{checkpoint();project.style[key]=key==='background'?$(key).checked:['font','color','position'].includes(key)?$(key).value:Number($(key).value);$('stylePreset').value='custom';changed();});}
$('stylePreset').onchange=()=>{const kind=$('stylePreset').value;checkpoint();if(kind==='classic')project.style=clone(defaultStyle);if(kind==='film')project.style={...defaultStyle,font:'SimHei',size:42,outline:1,shadow:1,margin:78};if(kind==='label')project.style={...defaultStyle,size:44,outline:0,shadow:0,background:true};if(kind==='saved')project.style=clone(savedStyle);renderStyles();changed();};
action('saveStyle',async()=>{await api('style-preset',project.style);savedStyle=clone(project.style);addSavedStyle();$('stylePreset').value='saved';toast('已保存样式，下次可直接选择“我的预设”');});
function addSavedStyle(){if(savedStyle&&!$('stylePreset').querySelector('[value="saved"]'))$('stylePreset').add(new Option('我的预设','saved'));}
for(const id of ['profileSelect','memoryProfileSelect'])$(id).onchange=()=>changeProfile($(id).value).catch(report);
action('applyProfile',()=>previewHabit());
action('simplifyCues',async()=>{if(!project.cues.length)throw new Error('请先导入或识别字幕');const before=JSON.stringify(project.cues);const result=await api('simplify',{cues:project.cues});if(before!==JSON.stringify(project.cues))throw new Error('字幕刚刚发生变化，请重新点击繁转简');if(JSON.stringify(result.cues)===before)return toast('当前字幕已经是简体');checkpoint();project.cues=result.cues;renderCues();changed();toast('全部字幕已转为简体，时间与断句保持不变，可撤销');});
action('learnFiles',()=>learnFromFiles());
action('learnCurrent',()=>learnConfirmed());
action('newProfile',async()=>{if(rulesDirty)await saveHabitRules();if(!await modal('新建空白习惯','<p>新习惯不会继承其他习惯的样本。已有学习结果可直接在上方选择，无需新建。</p><label>名称<input id="newProfileName" placeholder="例如：日常口播、访谈"></label>'))return;const result=await api('profile',{name:$('newProfileName').value});profiles=result.profiles;project.profile_id=result.profile.id;rulesDirty=false;updateProfiles();changed();});
action('saveRules',()=>saveHabitRules());
action('forgetProfile',async()=>{if(!await modal('清空这套习惯','<p>这会删除当前习惯的学习样本，并恢复默认规则。原始字幕文件不受影响。</p>','清空'))return;const result=await api('forget',{profile_id:project.profile_id});profiles=result.profiles;updateProfiles();toast('已清空当前习惯');});
action('saveProject',()=>exportFile('project'));
async function exportFile(kind){const ext=kind==='project'?'zmproj':kind;const paths=await choose(kind==='project'?'project':kind,false,project.name+'.'+ext);if(!paths.length)return;let path=paths[0];if(!path.toLowerCase().endsWith('.'+ext))path+='.'+ext;if(kind==='mp4'){await startJob({kind:'burn',project:clone(project),path});}else{await api('export-text',{project,path,format:kind});setPage('outputs');toast('文件已保存，可在这里查看结果或打开所在文件夹',7000);}}
action('exportButton',async()=>{const body=await modal('导出作品',`<label>导出格式<select id="exportFormat"><option value="mp4">带字幕的视频 · MP4</option><option value="srt">字幕文件 · SRT</option><option value="ass">带样式字幕 · ASS</option><option value="txt">纯文本 · TXT</option></select></label><p>视频导出保留原分辨率，使用 H.264 编码。SRT 只包含文字与时间，ASS 保留字幕样式。</p>`,'选择保存位置');if(body)await exportFile($('exportFormat').value);});
action('openProject',async()=>{const paths=await choose('project');if(!paths.length)return;if(pendingEdits)await save();const result=await api('open-project',{path:paths[0]});checkpoint();project=result.project;selected=-1;renderAll();changed();});
action('newProject',async()=>{if(project.cues.length&&!await modal('开始新项目','<p>新项目会替换当前自动恢复记录。需要保留当前项目时，请先“另存项目”。</p>','新建'))return;checkpoint();video.pause();project={version:1,id:crypto.randomUUID(),name:'未命名项目',media:null,cues:[],original_cues:[],style:clone(defaultStyle),profile_id:profile().id};selected=-1;renderAll();changed();});
function busy(value){document.querySelectorAll('.topbar button,main button,main input,main textarea,main select').forEach(el=>{if(value){el.dataset.wasDisabled=String(el.disabled);el.disabled=true;}else el.disabled=el.dataset.wasDisabled==='true';});if(!value)updateUndo();}
async function startJob(data){if(currentJob)throw new Error('已有任务正在进行');if(data.kind==='transcribe'){if(rulesDirty)await saveHabitRules();data.profile_id=project.profile_id;if(project.reference_document)data.reference_document=clone(project.reference_document);if(!profile().samples.length&&!await modal('这套习惯还没有学习样本',`<p>“${escapeHTML(profile().name)}”没有历史成稿，本次只使用其字数、换行等规则。已学习的其他习惯不会自动混入。可取消后在断句习惯页切换。</p>`,'使用这套规则识别'))return;}await save();const result=await api('jobs',data);currentJob=result.job;$('jobPanel').hidden=false;$('cancelJob').textContent='取消任务';$('jobTitle').textContent=data.kind==='burn'?'导出成片':data.kind==='preview'?'生成兼容预览':'本地语音识别';busy(true);pollJob();}
async function pollJob(){try{const result=await api('jobs/'+currentJob.id);const job=result.job;$('jobMessage').textContent=job.message;if(job.kind==='transcribe'&&job.state==='running')$('jobProgress').removeAttribute('value');else $('jobProgress').value=job.progress;
  if(['running','cancelling'].includes(job.state)){setTimeout(pollJob,700);return;}
  currentJob=null;busy(false);
  if(job.state==='done'){
    if(job.kind==='transcribe'){checkpoint();project.original_cues=clone(job.result.original_cues||job.result.cues);project.cues=job.result.cues;project.application=job.result.application;project.last_comparison={before:clone(project.original_cues),after:clone(project.cues),application:job.result.application};project.reference_review=job.result.comparison||null;selected=0;renderCues();updateProfiles();changed();if(job.result.comparison)setTimeout(()=>showDocumentReview().catch(report),0);if(job.result.comparison_error)toast('语音已保留；文稿对照未完成：'+job.result.comparison_error,10000);toast('识别完成，已应用“'+(project.application?.name||profile().name)+'”，可查看断句对比');}
    else if(job.kind==='preview'){video.src=job.result.media.url;video.load();$('compatPreview').hidden=true;toast('兼容预览已就绪，导出仍使用原始素材');}
    else {setPage('outputs');toast('视频已导出，可以在保存与导出页直接播放成片',8000);}
    $('jobPanel').hidden=true;
  }else if(job.state==='error'){$('cancelJob').textContent='关闭';$('status').textContent='任务失败，可以修改设置后重试';}
  else {$('jobPanel').hidden=true;toast('任务已取消，编辑内容保留');}
}catch(error){currentJob=null;busy(false);$('jobPanel').hidden=true;report(error);}}
action('cancelJob',async()=>{if(currentJob)await api('jobs/'+currentJob.id+'/cancel',{});else $('jobPanel').hidden=true;});
action('recognize',async()=>{if(!project.media)throw new Error('请先导入视频或音频');if(!project.media.has_audio)throw new Error('该素材没有音轨');if(!await modal('自动识别语音',`<label>识别模型<select id="model"><option value="small">Small · 推荐，中文更准确</option><option value="tiny">Tiny · 快速试用</option><option value="base">Base · 轻量</option><option value="medium">Medium · 更慢，更占内存</option></select></label><label>语言<select id="language"><option value="zh">中文 / 中英混说</option><option value="en">英语</option><option value="">自动检测</option></select></label>${project.reference_document?`<p class="reference-warning">已关联文稿：${escapeHTML(project.reference_document.name)}。语音独立识别完成后自动对照，差异由你确认采用。</p>`:'<p>可先导入文稿，识别完成后自动交叉核对。</p>'}<label>人名与术语提示<input id="recognitionPrompt" placeholder="例如：小津安二郎、镜头语言"></label><p>使用本地 CPU 识别；首次使用未缓存模型时需要联网下载。完成后替换当前字幕，并应用“${escapeHTML(profile().name)}”，可撤销。</p>`,'开始识别'))return;await startJob({kind:'transcribe',path:project.media.path,model:$('model').value,language:$('language').value,prompt:$('recognitionPrompt').value});});
action('compatPreview',()=>startJob({kind:'preview',media:project.media}));
action('play',async()=>{if(!project.media?.url)return toast('请先导入视频或音频');if(video.paused)await video.play();else video.pause();});
$('seek').addEventListener('input',()=>{const time=Number($('seek').value);if(project.media?.url)video.currentTime=time;updateOverlay(time);updateTransport(time);});
$('speed').onchange=()=>video.playbackRate=Number($('speed').value);
video.addEventListener('timeupdate',()=>{updateTransport(video.currentTime);updateOverlay(video.currentTime);});
video.addEventListener('play',()=>updateTransport());video.addEventListener('pause',()=>updateTransport());
video.addEventListener('loadedmetadata',()=>{updateOverlay();updateTransport();});
video.addEventListener('error',()=>{if(project?.media?.has_video)$('compatPreview').hidden=false;});
new ResizeObserver(()=>updateOverlay()).observe($('stage'));
document.addEventListener('keydown',event=>{const editing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName);if($('modal').open||currentJob)return;if(event.code==='Space'&&!editing){event.preventDefault();$('play').click();}if(event.ctrlKey&&event.key.toLowerCase()==='s'){event.preventDefault();$('saveProject').click();}if(event.ctrlKey&&event.key.toLowerCase()==='z'&&!editing){event.preventDefault();$(event.shiftKey?'redo':'undo').click();}});
window.addEventListener('beforeunload',event=>{if(pendingEdits){save();event.preventDefault();event.returnValue='';}});
document.addEventListener('dragover',event=>{event.preventDefault();$('stage').classList.add('drop-active');});
document.addEventListener('dragleave',event=>{if(!event.relatedTarget)$('stage').classList.remove('drop-active');});
document.addEventListener('drop',async event=>{
  event.preventDefault();$('stage').classList.remove('drop-active');if(currentJob)return;
  try{
    const files=Array.from(event.dataTransfer.files);if(!files.length)return;
    if(project.cues.length&&!await modal('导入拖入的文件','<p>拖入的字幕会替换当前稿件，拖入媒体会替换预览素材。文件会复制到本地缓存；大视频建议用“导入视频”选择原文件。</p>','导入'))return;
    for(const file of files){
      $('status').textContent='正在导入 '+file.name+'…';const form=new FormData();form.append('file',file);
      const response=await fetch('/api/upload',{method:'POST',headers:{'X-App-Token':token},body:form});const result=await response.json();if(!response.ok)throw new Error(result.error);
      if(/\.(srt|ass|ssa)$/i.test(file.name)){const data=await api('import-subtitles',{path:result.path});checkpoint();project.cues=data.cues;project.original_cues=clone(data.cues);}
      else {const data=await api('media',{path:result.path});checkpoint();project.media={...data.media,name:file.name};if(project.name==='未命名项目')project.name=file.name.replace(/\.[^.]+$/,'');}
    }renderAll();changed();toast('拖入文件已导入');$('status').textContent='准备就绪';
  }catch(error){report(error);}
});
async function init(){const state=await api('state');project=state.project;profiles=state.profiles;savedStyle=state.style_preset;outputsData=state.outputs||[];dataDirectory=state.data_dir;addSavedStyle();renderAll();$('status').textContent='准备就绪 · Ctrl+S 另存项目';$('localStatus').textContent=state.ffmpeg?'本地处理 · FFmpeg 就绪':'未检测到 FFmpeg，视频导出不可用';}
init().catch(report);
