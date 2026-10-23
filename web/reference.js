'use strict';

function referenceIsCurrent(review=project.reference_review) {
  return review && JSON.stringify(review.source_cues)===JSON.stringify(project.cues) && review.document.text===project.reference_document?.text;
}
function renderReference() {
  if(!project)return;
  const doc=project.reference_document,review=project.reference_review;
  $('referenceName').textContent=doc ? doc.name : '文稿与语音交叉核对';
  $('referenceStatus').textContent=!doc ? '导入 Word / TXT / Markdown，或粘贴解说词。识别后自动对照，差异由你确认。' : !review ? `${doc.text.length} 字 · 已随项目保存 · 下次识别后自动核对，也可对照现有字幕` : !referenceIsCurrent() ? '文稿或字幕已修改，请重新对照。' : `已对照 · ${review.rows.length} 处待核对 · ${review.matched_cues} 条文字一致（忽略标点与繁简差异）`;
  $('compareDocument').disabled=!doc || !project.cues.length || Boolean(currentJob);
  $('editDocument').textContent=doc?'查看 / 编辑文稿':'粘贴文稿';
  $('removeDocument').hidden=!doc;
  $('viewDocumentReview').hidden=!referenceIsCurrent();
}
const renderAllBeforeReference=renderAll;
renderAll=function(){renderAllBeforeReference();renderReference();};
const changedBeforeReference=changed;
changed=function(){changedBeforeReference();renderReference();};

action('importDocument',async()=>{
  const paths=await choose('document');if(!paths.length)return;
  const result=await api('import-document',{path:paths[0]});
  checkpoint();project.reference_document=result.document;delete project.reference_review;changed();
  toast(`已导入“${result.document.name}”。${project.cues.length?'现在可以点击“对照当前字幕”。':'自动识别完成后会显示核对结果。'}`);
});
action('editDocument',async()=>{
  const doc=project.reference_document||{name:'粘贴的文稿',text:''};
  if(!await modal('参考文稿',`<p>使用这段视频对应的解说词。文稿会随项目保存，最多 20000 字。</p><label>文稿名称<input id="documentName" maxlength="200" value="${escapeHTML(doc.name)}"></label><label>文稿正文<textarea id="documentText" rows="14" maxlength="20000" placeholder="粘贴解说词或拍摄文案…">${escapeHTML(doc.text)}</textarea></label>`,'保存文稿'))return;
  const text=$('documentText').value.trim();if(!text || !/[\p{L}\p{N}]/u.test(text))throw new Error('请填写文稿正文');
  checkpoint();project.reference_document={name:$('documentName').value.trim()||'粘贴的文稿',text};delete project.reference_review;changed();toast('文稿已保存，识别后将自动核对');
});
action('removeDocument',async()=>{
  if(!await modal('移除参考文稿','<p>从当前项目移除文稿和核对记录，字幕保留。</p>','移除'))return;
  checkpoint();delete project.reference_document;delete project.reference_review;changed();
});
async function compareDocument(){
  if(!project.reference_document)throw new Error('请先导入或粘贴文稿');
  if(!project.cues.length)throw new Error('请先识别或导入字幕');
  const before=clone(project.cues),document=clone(project.reference_document);
  $('compareDocument').disabled=true;$('referenceStatus').textContent='正在对照文稿…';
  try{
    const result=await api('compare-document',{cues:before,document});
    if(JSON.stringify(before)!==JSON.stringify(project.cues)||JSON.stringify(document)!==JSON.stringify(project.reference_document))throw new Error('字幕或文稿已改变，请重新对照');
    project.reference_review=result.comparison;changed();await showDocumentReview();
  }finally{renderReference();}
}
action('compareDocument',compareDocument);
action('viewDocumentReview',()=>showDocumentReview());

async function showDocumentReview(){
  const review=project.reference_review;if(!referenceIsCurrent(review))throw new Error('字幕或文稿已改变，请重新对照');
  const rows=review.rows;
  const markup=`<div class="reference-review"><p><strong>${escapeHTML(review.document.name)}</strong> · 文字匹配度 ${review.similarity}%（不是识别正确率）</p><p>语音和文稿独立对照。标点、空格与繁简差异已忽略。请试听后勾选要采用的文稿文字，未选项保留识别结果。</p>${review.low_match?'<div class="reference-warning">两份文字匹配度较低，可能不是同一版本或顺序不同。请检查文稿，本次仅显示差异，需手动修改。</div>':''}<div class="reference-review-summary">${rows.length?`${rows.length} 处差异待核对`:'未发现正文文字差异'} · ${review.matched_cues} 条文字一致</div>${rows.length?'<label class="check"><input id="selectReferenceChanges" type="checkbox">勾选全部可采用项（仍需试听确认）</label>':'<p>文字一致仍可能包含双方共有的错误，建议试听重点人名、数字和术语。</p>'}<div class="reference-rows">${rows.map((row,index)=>{
    const cue=review.source_cues[row.cue_index];
    return `<article class="reference-row"><header><strong>${cue?`第 ${row.cue_index+1} 条 · ${clock(cue.start)} → ${clock(cue.end)}`:'文稿中有，未定位到语音'}</strong>${cue?`<button type="button" data-listen-cue="${row.cue_index}">试听这句</button>`:''}</header><div class="reference-texts"><div><small>语音识别 / 当前字幕</small><p>${escapeHTML(row.original||'未找到对应文字')}</p></div><div><small>${row.suggestion!==null?'采用文稿后的预览':'文稿差异片段'}</small><p>${escapeHTML(row.suggestion??(row.document||row.differences.map(d=>d.document||'〔文稿无此内容〕').join(' / ')))}</p></div></div><div class="reference-differences">${row.differences.map(d=>`<span>${escapeHTML(d.recognized||'〔识别未包含〕')} <b>↔</b> <mark>${escapeHTML(d.document||'〔文稿未包含〕')}</mark></span>`).join('')}</div><p class="hint">${escapeHTML(row.reason)}</p>${row.suggestion!==null?`<label class="check"><input type="checkbox" data-reference-change="${index}">采用这条文稿文字，保留原时间</label>`:'<small>请在字幕编辑区手动核对。</small>'}</article>`;
  }).join('')}</div><p class="hint">采用后可撤销；修改过的词级对齐会清除，后续重新断句的时间可能按字数估算。</p></div>`;
  const answer=modal('文稿与语音核对',markup,rows.some(r=>r.suggestion!==null)?'采用勾选项':'关闭');
  const selectAll=$('selectReferenceChanges');if(selectAll)selectAll.onchange=()=>document.querySelectorAll('[data-reference-change]').forEach(c=>c.checked=selectAll.checked);
  let stopPreview;
  document.querySelectorAll('[data-listen-cue]').forEach(button=>button.onclick=()=>{
    const cue=review.source_cues[Number(button.dataset.listenCue)];
    if(!project.media?.url)return toast('请先关联视频或音频，才能试听');
    if(stopPreview)video.removeEventListener('timeupdate',stopPreview);
    video.currentTime=cue.start;stopPreview=()=>{if(video.currentTime>=cue.end){video.pause();video.removeEventListener('timeupdate',stopPreview);}};
    video.addEventListener('timeupdate',stopPreview);video.play().catch(report);
  });
  const body=await answer;if(stopPreview){video.pause();video.removeEventListener('timeupdate',stopPreview);}
  if(!body)return;
  const choices=Array.from(body.querySelectorAll('[data-reference-change]:checked')).map(c=>rows[Number(c.dataset.referenceChange)]);
  if(!choices.length)return;
  if(!referenceIsCurrent(review))throw new Error('字幕或文稿已改变，请重新对照');
  checkpoint();
  for(const row of choices){project.cues[row.cue_index].text=row.suggestion;delete project.cues[row.cue_index].words;}
  renderCues();changed();toast(`已采用 ${choices.length} 条文稿文字，时间轴保留，可撤销。`);
}
if(project)renderReference();
