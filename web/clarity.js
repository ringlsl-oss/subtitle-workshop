'use strict';
const displayDate = value => value ? new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Hong_Kong',hour12:false}) : '此前已保存';
function ruleSummary(r){return `常用 ${r.target_chars} 字 / 最多 ${r.max_chars} 字 · ${r.max_lines} 行 · ${r.keep_punctuation?'保留标点':'去除标点'} · 停顿 ${r.pause} 秒保留分隔`;}
const baseRenderMemory=renderMemory;
renderMemory=function(){
  if(!project)return;
  if(!rulesDirty)baseRenderMemory();
  const p=profile();
  $('profileOverview').innerHTML=profiles.map(item=>`<button class="profile-choice ${item.id===p.id?'active':''}" data-profile="${escapeHTML(item.id)}"><strong>${escapeHTML(item.name)} ${item.id===p.id?'· 当前使用':''}</strong><small>${item.samples.length} 个作品 · ${item.samples.reduce((n,s)=>n+s.cues.length,0)} 条字幕${item.samples.length?'':' · 未学习'}</small></button>`).join('');
  $('profileOverview').querySelectorAll('button').forEach(b=>b.onclick=()=>changeProfile(b.dataset.profile).catch(report));
  const alternatives=profiles.filter(item=>item.id!==p.id&&item.samples.length);
  $('learningNotice').classList.toggle('warning',!p.samples.length);
  let notice=p.samples.length?`<strong>“${escapeHTML(p.name)}”已学习 ${p.samples.length} 个作品、${p.samples.reduce((n,s)=>n+s.cues.length,0)} 条字幕。</strong><p>下面显示保存的规则与样本。新识别将使用这套习惯；已有字幕需要点击“预览并应用”。</p>`:`<strong>当前“${escapeHTML(p.name)}”还没有学习样本。</strong><p>只会使用下面的默认或手动规则。新建习惯不会继承另一套习惯的样本。</p>`;
  if(!p.samples.length&&alternatives.length)notice+=`<p>你的学习结果保存在其他习惯：</p>`+alternatives.map(item=>`<button data-use-profile="${escapeHTML(item.id)}">使用“${escapeHTML(item.name)}”（${item.samples.reduce((n,s)=>n+s.cues.length,0)} 条）</button>`).join('');
  if(p.last_learning){const r=p.last_learning;notice+=`<p>最近导入：新增 ${r.added} 个 · 更新 ${r.updated||0} 个 · 重复跳过 ${r.duplicates} 个 · 失败 ${r.failed} 个<br>${displayDate(r.saved_at)}</p>`;if(r.errors?.length)notice+=`<details><summary>查看导入失败原因</summary>${r.errors.map(e=>`<p>${escapeHTML(e)}</p>`).join('')}</details>`;}
  $('learningNotice').innerHTML=notice;
  $('learningNotice').querySelectorAll('[data-use-profile]').forEach(b=>b.onclick=()=>changeProfile(b.dataset.useProfile).catch(report));
  $('savedRuleSummary').innerHTML=`<strong>已保存的规则 · ${escapeHTML(p.name)}</strong>${escapeHTML(ruleSummary(p.rules))}<br>保护词：${escapeHTML(p.rules.protected_terms.join('、')||'未设置')}<br><small>${displayDate(p.saved_at)}</small>`;
  $('ruleSource').textContent=p.samples.length?'已学习':p.saved_at?'手动规则 / 无样本':'未学习';
  $('ruleSaveState').textContent=rulesDirty?'有未保存修改，尚未生效':'规则已保存 · 不会自动改写当前字幕';
  $('sampleList').innerHTML=p.samples.length?p.samples.map((s,i)=>`<div class="sample-row"><div><strong>${escapeHTML(s.name)}</strong><p class="hint">${s.cues.length} 条字幕 · 已保存</p></div><button data-sample="${i}">查看学到的断句</button></div>`).join(''):'<p class="hint">这套习惯没有样本，请导入 SRT / ASS 成稿，或切换到已有样本的习惯。</p>';
  $('sampleList').querySelectorAll('button').forEach(b=>b.onclick=()=>{const s=profile().samples[Number(b.dataset.sample)];modal(s.name,`<p>已保存 ${s.cues.length} 条，下面显示前 ${Math.min(100,s.cues.length)} 条原始断句。</p><div class="compare-column">${comparisonCues(s.cues)}</div>`,'知道了');});
  refreshProfileStatus();
};
const baseUpdateProfiles=updateProfiles;
updateProfiles=function(){baseUpdateProfiles();for(const id of ['profileSelect','memoryProfileSelect']){for(const option of $(id).options){const p=profiles.find(p=>p.id===option.value);option.textContent=`${p.name} · ${p.samples.reduce((n,s)=>n+s.cues.length,0)} 条已学习字幕`;}}refreshProfileStatus();};
function refreshProfileStatus(){
  if(!project)return;const p=profile(),a=project.application;
  $('activeProfileStatus').classList.toggle('warning',!p.samples.length);
  $('activeProfileStatus').innerHTML=`<strong>下次识别 / 应用：${escapeHTML(p.name)}</strong><br>${p.samples.length?`${p.samples.length} 个学习作品`:'尚无样本，仅使用规则'} · ${escapeHTML(ruleSummary(p.rules))}<br><small>${a?`当前字幕上次应用：${escapeHTML(a.name)} · ${displayDate(a.applied_at)}`:'当前字幕尚无应用记录，请预览并应用。'}</small>`;
  $('viewComparison').disabled=!project.last_comparison;
}
async function changeProfile(identifier){
  if(identifier===project.profile_id)return;
  if(rulesDirty){if(!await modal('当前规则尚未保存','<p>保存当前修改后，再切换到另一套习惯。</p>','保存并切换')){for(const id of ['profileSelect','memoryProfileSelect'])$(id).value=project.profile_id;return;}await saveHabitRules();}
  project.profile_id=identifier;rulesDirty=false;updateProfiles();changed();
  $('status').textContent=`当前选择“${profile().name}”；已有字幕请预览并应用，新识别将使用此习惯。`;
}
function formProfile(){const p=clone(profile());p.name=$('ruleName').value.trim()||'未命名习惯';p.rules={target_chars:Number($('targetChars').value),max_chars:Number($('maxChars').value),line_chars:Number($('lineChars').value),max_lines:Number($('maxLines').value),pause:Number($('pause').value),keep_punctuation:$('keepPunctuation').checked,protected_terms:$('protectedTerms').value.split('\n').map(v=>v.trim()).filter(Boolean)};return p;}
async function saveHabitRules(){const result=await api('profile',formProfile());profiles=result.profiles;rulesDirty=false;updateProfiles();$('ruleSaveState').textContent='保存成功 · '+displayDate(result.profile.saved_at);toast('规则已保存。点击“预览并应用”可修改当前字幕。');}
for(const id of ['ruleName','targetChars','maxChars','lineChars','maxLines','pause','keepPunctuation','protectedTerms'])$(id).addEventListener('input',()=>{rulesDirty=true;$('ruleSaveState').textContent='有未保存修改，尚未生效';});
function comparisonCues(cues){return cues.slice(0,100).map((c,i)=>`<div class="comparison-cue"><small>${i+1} · ${clock(c.start)} → ${clock(c.end)}</small>${escapeHTML(c.text)}</div>`).join('');}
function comparisonMarkup(before,after,application){return `<p>习惯：<strong>${escapeHTML(application?.name||'未记录')}</strong> · ${application?.sample_count||0} 个学习作品</p><p>${application?escapeHTML(ruleSummary(application.rules)):''}</p><p>下面显示各自前 100 条；文字内容、拆分位置和时间都可直接比较。</p><div class="compare-columns"><div class="compare-column"><h3>应用前 · ${before.length} 条</h3>${comparisonCues(before)}</div><div class="compare-column"><h3>应用后 · ${after.length} 条</h3>${comparisonCues(after)}</div></div>`;}
async function previewHabit(){
  if(!project.cues.length)throw new Error('请先导入或识别字幕，再预览断句效果');
  if(rulesDirty)await saveHabitRules();
  const before=clone(project.cues),identifier=project.profile_id;
  const result=await api('resegment',{cues:before,profile_id:identifier});
  if(!await modal('断句效果对比',comparisonMarkup(before,result.cues,result.application),'应用到当前字幕'))return;
  if(JSON.stringify(before)!==JSON.stringify(project.cues)||identifier!==project.profile_id)throw new Error('字幕或习惯已改变，请重新预览');
  checkpoint();project.cues=result.cues;project.application=result.application;project.last_comparison={before,after:clone(result.cues),application:result.application};selected=-1;renderCues();refreshProfileStatus();changed();setPage('editor');toast('已应用“'+result.application.name+'”，可撤销或查看上次对比');
}
action('previewRules',previewHabit);
action('viewComparison',()=>{const c=project.last_comparison;if(c)return modal('上次应用记录',comparisonMarkup(c.before,c.after,c.application),'知道了');});
async function learnFromFiles(){
  if(rulesDirty)await saveHabitRules();const paths=await choose('subtitles',true);if(!paths.length)return;
  const identifier=project.profile_id;const result=await api('learn',{profile_id:identifier,paths});profiles=result.profiles;rulesDirty=false;updateProfiles();setPage('memory');
  const r=result.report;toast(`“${result.profile.name}”：新增 ${r.added} 个，重复跳过 ${r.duplicates} 个，失败 ${r.failed} 个。详情已保存在此页。`,8000);
}
async function learnConfirmed(){
  if(!project.cues.length)throw new Error('还没有可学习的字幕');if(rulesDirty)await saveHabitRules();
  if(!await modal('确认学习成稿',`<p>将当前 ${project.cues.length} 条字幕保存到“${escapeHTML(profile().name)}”。同一项目会更新旧样本。</p>`,'确认学习'))return;
  const result=await api('learn',{profile_id:project.profile_id,cues:project.cues,name:project.name,source_id:project.id});profiles=result.profiles;rulesDirty=false;updateProfiles();setPage('memory');toast('成稿已保存到“'+result.profile.name+'”，可查看样本与规则');
}
async function refreshOutputs(){const result=await api('outputs');outputsData=result.outputs;renderOutputs();}
function renderOutputs(){
  $('autosaveLocation').textContent=dataDirectory+'\\autosave.json';
  const labels={mp4:'成片视频',srt:'SRT 字幕',ass:'ASS 字幕',txt:'纯文本',project:'项目文件'};
  $('outputList').innerHTML=outputsData.length?outputsData.map(r=>`<div class="output-row"><div><h3>${escapeHTML(r.path.split(/[\\/]/).at(-1))}</h3><p>${labels[r.format]||r.format} · ${displayDate(r.saved_at)}</p><p>${escapeHTML(r.path)}</p></div><div class="output-actions"><button data-preview="${r.id}">${r.format==='mp4'?'播放导出视频':'查看保存内容'}</button><button data-folder="${r.id}">打开所在文件夹</button></div></div>`).join(''):'<div class="output-empty">还没有新版本的导出记录。<br>右上角“导出”生成成片或字幕后，会在这里显示文件与路径。<br>之前版本导出的文件仍在原保存位置，本页不会扫描其他文件。</div>';
  $('outputList').querySelectorAll('[data-preview]').forEach(b=>b.onclick=async()=>{try{const data=await api('output-preview',{id:b.dataset.preview});const entry=outputsData.find(r=>r.id===b.dataset.preview);await modal('查看保存结果',`<p>${escapeHTML(entry.path)}</p>`+(data.media?`<video controls src="${escapeHTML(data.media.url)}"></video>`:`<pre>${escapeHTML(data.text)}</pre>`),'关闭');const player=$('modalBody').querySelector('video');if(player)player.pause();}catch(e){report(e);}});
  $('outputList').querySelectorAll('[data-folder]').forEach(b=>b.onclick=()=>api('open-output-folder',{id:b.dataset.folder}).catch(report));
}
action('refreshOutputs',refreshOutputs);action('openDataFolder',()=>api('open-output-folder',{}));
if(project)updateProfiles();
