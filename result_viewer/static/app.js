const $ = id => document.getElementById(id);
const state = {experiment:0, view:'overview', sample:null, overview:null, version:0};
function el(tag,text,cls){const n=document.createElement(tag); if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function showError(e){$('notice').replaceChildren(el('div',e.message,'error'));}
async function api(route,params={}){const r=await fetch('/api/'+route+'?'+new URLSearchParams({experiment:state.experiment,...params}));if(!r.ok){const e=await r.json();throw Error(e.error||r.statusText);}return r.json();}
function fileUrl(path){return '/api/file?'+new URLSearchParams({experiment:state.experiment,path});}
async function textFile(path){const r=await fetch(fileUrl(path));if(!r.ok)throw Error('无法读取 '+path);return r.text();}
function pretty(value){return typeof value==='string'?value:JSON.stringify(value,null,2);}
function pre(value){return el('pre',pretty(value));}
function empty(parent,text='未找到对应记录'){parent.append(el('div',text,'empty'));}
function scored(summary){return $('evaluation').value?summary?.reevaluations?.[$('evaluation').value]:summary;}
function scoreLabel(summary){const s=scored(summary);return s?.accuracies?.map(v=>v===null?'—':v).join(' / ')||'评分未记录';}
function lazy(parent,title,path){const d=el('details');const s=el('summary',title);s.append(el('span',path,'source'));d.append(s);let loaded=false;d.addEventListener('toggle',async()=>{if(d.open&&!loaded){loaded=true;try{d.append(pre(await textFile(path)));}catch(e){loaded=false;d.append(el('p',e.message,'error'));}}});parent.append(d);return d;}
function image(parent,path){const f=el('figure');const a=el('a');a.href=fileUrl(path);a.target='_blank';a.rel='noopener';const im=el('img');im.src=fileUrl(path);im.alt=path.split('/').pop();im.loading='lazy';a.append(im);f.append(a,el('figcaption',path));parent.append(f);}
function listSamples(){const q=$('search').value.toLowerCase();$('samples').replaceChildren();for(const sample of state.overview.samples.filter(s=>s.id.toLowerCase().includes(q))){const b=el('button',sample.id+'\n'+scoreLabel(sample.summary),sample.id===state.sample?'selected':'');b.onclick=()=>{state.sample=sample.id;state.view='sample';render();};$('samples').append(b);}}
async function load(){state.version++;$('notice').replaceChildren();state.overview=await api('overview');const previous=$('evaluation').value;$('evaluation').replaceChildren(new Option('原始评分',''));const names=new Set(Object.keys(state.overview.summary?.reevaluations||{}));for(const s of state.overview.samples)for(const name of Object.keys(s.summary?.reevaluations||{}))names.add(name);for(const n of names)$('evaluation').add(new Option(n,n));if(names.has(previous))$('evaluation').value=previous;if(!state.overview.samples.some(s=>s.id===state.sample))state.sample=state.overview.samples[0]?.id;await render();}
async function render(){const version=++state.version;listSamples();$('notice').replaceChildren();document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));$('title').textContent={overview:'实验概览',sample:'单题过程',knowledge:'知识库快照'}[state.view];const content=el('div');$('content').replaceChildren(content);try{if(state.view==='overview')overview(content);else if(state.view==='sample')await sampleView(content,version);else await knowledge(content);}catch(e){if(version===state.version)showError(e);}}
function overview(parent){const s=scored(state.overview.summary);const cards=el('div',undefined,'cards');for(const [label,value] of [['已有题目',state.overview.samples.length],['每题 rollout',s?.num_rollouts??'—'],['评分来源',$('evaluation').selectedOptions[0].text]]){const c=el('div',undefined,'card');c.append(el('div',label,'muted'),el('div',String(value),'number'));cards.append(c);}parent.append(cards);const table=el('table');const head=el('tr');for(const t of ['题目 ID','Rollout 得分','已保存的完成状态'])head.append(el('th',t));table.append(head);for(const item of state.overview.samples){const tr=el('tr');const td=el('td');const b=el('button',item.id);b.onclick=()=>{state.sample=item.id;state.view='sample';render();};td.append(b);tr.append(td,el('td',scoreLabel(item.summary)),el('td',scored(item.summary)?.completed===true?'完成':scored(item.summary)?.completed===false?'未完成':'未记录'));table.append(tr);}parent.append(table);if(s){const d=el('details');d.append(el('summary','数据集指标 · 保存的原值'),pre(s));parent.append(d);}else empty(parent,'该评分来源没有数据集汇总记录');}
async function sampleView(parent,version){if(!state.sample){empty(parent);return;}const files=await api('sample',{sample:state.sample});if(version!==state.version)return;const prefix=state.sample+'/';const at=name=>files.find(f=>f.path===prefix+name)?.path;parent.append(el('h2',state.sample));const rollouts=[...new Set(files.filter(f=>f.name==='traj.jsonl'||f.name==='metrics.json').map(f=>f.path.slice(0,f.path.lastIndexOf('/'))))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));const first=files.find(f=>f.name==='traj.jsonl');if(first){try{const raw=await textFile(first.path);const metadata=JSON.parse(raw.split('\n').find(l=>l.trim()));const box=el('div',undefined,'panel');box.append(el('h3','题目'),el('p',metadata.initial_prompt||metadata.prompt||'未记录题目'),el('span','标准答案（评估用）','tag'),pre(metadata.ground_truth??'未记录'));parent.append(box);}catch(e){parent.append(el('p','题目记录读取失败：'+e.message,'error'));}}
const originals=files.filter(f=>f.name.startsWith('original_image')&&/\.(jpg|jpeg|png|webp)$/i.test(f.name)&&(!rollouts.length||f.path.startsWith(rollouts[0]+'/')));const gallery=el('div',undefined,'gallery');originals.forEach(f=>image(gallery,f.path));parent.append(gallery);
const tabs=el('div',undefined,'tabs');const body=el('div');parent.append(tabs,body);const modes=['Rollout 执行','Phase 1 · 知识积累','Phase 2 · 知识使用'];for(const mode of modes){const b=el('button',mode);b.onclick=async()=>{tabs.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));body.replaceChildren();try{if(mode===modes[0])rolloutView(body,files,rollouts);else if(mode===modes[1])phaseOne(body,files,at);else await phaseTwo(body,at);}catch(e){body.append(el('p',e.message,'error'));}};tabs.append(b);}tabs.firstChild.click();}
function phaseOne(parent,files,at){parent.append(el('p','仅显示已保存的积累记录。单题经验、技能片段不等于最终入库内容。','muted'));let found=false;for(const [title,names] of [['轨迹总结',['exp_summary_prompt.txt','exp_summary_resp.txt']],['跨 Rollout 批评 → 解析经验',['exp_intra_prompt.txt','exp_intra_resp.txt','exp_items.json']],['技能提取结果（已清理文本）',['skill_raw.md']]]){const paths=names.map(at).filter(Boolean);if(!paths.length)continue;found=true;parent.append(el('h2',title));const cols=el('div',undefined,'columns');for(const path of paths)lazy(cols,path.split('/').pop(),path);parent.append(cols);}const captions=files.filter(f=>f.path.includes('/.analysis_cache/'));if(captions.length){found=true;const d=el('details');d.append(el('summary','图像分析 · '+captions.length+' 条'));for(const f of captions){const c=el('div',undefined,'panel');const stem=f.name.replace('_analysis.txt','');const directory=f.path.split('/.analysis_cache/')[0];const picture=files.find(x=>x.path.startsWith(directory+'/')&&x.name.replace(/\.[^.]+$/,'')===stem);if(picture)image(c,picture.path);lazy(c,'分析文本',f.path);d.append(c);}parent.append(d);}if(!found)empty(parent);}
async function phaseTwo(parent,at){const path=at('tt_decomposition_info.txt');let found=false;if(path){found=true;const raw=await textFile(path);const marker='ORIGINAL RETRIEVED EXPERIENCES (Before Rewrite)';const rewritten='REWRITTEN EXPERIENCES (After Rewrite)';const originalIndex=raw.indexOf(marker);const rewrittenIndex=raw.indexOf(rewritten);parent.append(el('h2','任务分解与经验检索'),pre(originalIndex>=0?raw.slice(0,originalIndex):raw));if(originalIndex>=0&&rewrittenIndex>=0){const parse=txt=>Object.fromEntries([...txt.matchAll(/^\[([^\]]+)\]\s*\n-+\s*\n([\s\S]*?)(?=^\[[^\]]+\]\s*\n-+|(?![\s\S]))/gm)].map(m=>[m[1],m[2].replace(/\n=+\s*$/,'').trim()]));const before=parse(raw.slice(originalIndex+marker.length,rewrittenIndex));const after=parse(raw.slice(rewrittenIndex+rewritten.length));parent.append(el('h2','经验改写前后'));for(const id of new Set([...Object.keys(before),...Object.keys(after)])){const d=el('details');d.append(el('summary',id+(after[id]?'':' · 改写结果未保留')));const columns=el('div',undefined,'columns');for(const [label,value] of [['检索原文',before[id]],['改写结果',after[id]]]){const c=el('div');c.append(el('h3',label),pre(value??'未记录'));columns.append(c);}d.append(columns);parent.append(d);}}lazy(parent,'完整检索记录',path);}for(const name of ['tt_skill_original.md','tt_skill_adapted.md'])if(at(name)){found=true;lazy(parent,name==='tt_skill_adapted.md'?'适配后的技能（已处理文本）':'原始技能',at(name));}parent.append(el('p','实际注入的完整 system prompt 位于各 rollout。检索、改写或注入记录不代表模型实际遵循了这些知识。','muted'));if(!found)empty(parent);}
function pythonCode(source){
  const box=el('div',undefined,'python-code');
  const toolbar=el('div',undefined,'code-toolbar');
  const copy=el('button','复制代码');
  copy.onclick=async()=>{
    try{
      if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(source);
      else{
        const input=el('textarea',source,'copy-source');
        document.body.append(input);
        input.select();
        const copied=document.execCommand('copy');
        input.remove();
        if(!copied)throw Error('复制失败，请手动选择代码');
      }
      copy.textContent='已复制';
    }catch(e){copy.textContent=e.message;}
  };
  toolbar.append(el('span','Python'),copy);
  const block=el('pre'),code=el('code');
  // Tokenize for display only; never interpret or execute saved code.
  const tokens=/(?:[rubf]{0,2})(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|#[^\n]*|\b(?:False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b|\b\d+(?:\.\d+)?\b/gi;
  let offset=0;
  for(const match of source.matchAll(tokens)){
    code.append(document.createTextNode(source.slice(offset,match.index)));
    const token=match[0];
    const kind=token.startsWith('#')?'comment':/^[rubf]*["']/i.test(token)?'string':/^\d/.test(token)?'number':'keyword';
    code.append(el('span',token,'py-'+kind));
    offset=match.index+token.length;
  }
  code.append(document.createTextNode(source.slice(offset)));
  block.append(code);
  box.append(toolbar,block);
  return box;
}

function toolResult(parent,result,rows,files,shownImages){
  if(typeof result!=='string'){parent.append(pre(result));return;}
  // Resolve Markdown image aliases to saved images in this rollout.
  const pattern=/!\[([^\]]*)\]\(([^)\n]+)\)/g;
  let offset=0,matched=false;
  for(const match of result.matchAll(pattern)){
    matched=true;
    const text=result.slice(offset,match.index).trim();
    if(text)parent.append(pre(text));
    const saved=rows.find(r=>r.tool_image?.image_name===match[1])?.tool_image;
    const filename=match[2].split('/').pop();
    const file=files.find(f=>f.name===(saved?.file_path??filename));
    if(file){
      if(!shownImages.has(file.path)){image(parent,file.path);shownImages.add(file.path);}
    }else parent.append(el('p','未找到已保存图片：'+match[1],'muted'),pre(match[0]));
    offset=match.index+match[0].length;
  }
  if(!matched){parent.append(pre(result));return;}
  const rest=result.slice(offset).trim();
  if(rest)parent.append(pre(rest));
  const original=el('details');
  original.append(el('summary','原始工具返回'),pre(result));
  parent.append(original);
}

function trajectoryView(parent,raw,files){
  // Group saved events into turns without changing their recorded order.
  const turns=new Map();
  let line=0;
  for(const text of raw.split('\n')){
    line++;
    if(!text.trim())continue;
    let row;
    try{row=JSON.parse(text);}catch{parent.append(el('p','第 '+line+' 行 JSON 不完整','error'));continue;}
    if(row.turn_idx===undefined)continue;
    if(!turns.has(row.turn_idx))turns.set(row.turn_idx,[]);
    turns.get(row.turn_idx).push(row);
  }
  parent.append(el('h3','执行过程 · '+turns.size+' 轮'));
  for(const [turn,rows] of turns){
    const card=el('details');
    const tools=[...new Set(rows.map(r=>r.tool_call?.tool_name??r.tool_error?.tool_name??r.tool_image?.source_tool).filter(Boolean))];
    const failed=rows.some(r=>r.tool_error);
    card.append(el('summary','Turn '+turn+(tools.length?' · '+tools.join(' / '):' · 模型回答')+(failed?' · 工具错误':'')));
    const shownImages=new Set();
    // Keep model text, tool results, images and errors visibly distinct.
    for(const row of rows){
      const section=el('section',undefined,'turn-event');
      if(row.tool_call){
        const tool=row.tool_call;
        section.append(el('h3','工具调用 · '+tool.tool_name));
        if(tool.tool_name==='code_interpreter'&&typeof tool.parameters?.code==='string'){
          section.append(pythonCode(tool.parameters.code));
          const other=Object.fromEntries(Object.entries(tool.parameters).filter(([key])=>key!=='code'));
          if(Object.keys(other).length)section.append(el('div','其他参数','muted'),pre(other));
        }else section.append(el('div','调用参数','muted'),pre(tool.parameters));
        section.append(el('h3','执行结果'));
        toolResult(section,tool.result,rows,files,shownImages);
      }else if(row.tool_error){
        section.append(el('h3','工具错误 · '+row.tool_error.tool_name),el('div',pretty(row.tool_error.error),'error'));
      }else if(row.tool_image){
        if(files.some(f=>f.name===row.tool_image.file_path&&shownImages.has(f.path)))continue;
        section.append(el('h3','工具图片 · '+row.tool_image.source_tool));
      }else if(row.text_output!==undefined||row.content!==undefined){
        section.append(el('h3','模型输出'),pre(row.text_output??row.content));
        if(row.content&&row.content!==row.text_output){
          const content=el('details');
          content.append(el('summary','响应正文（content）'),pre(row.content));
          section.append(content);
        }
        if(row.usage){
          const usage=el('details');
          usage.append(el('summary','Token 用量'),pre(row.usage));
          section.append(usage);
        }
      }else{
        section.append(el('h3','其他记录'),pre(row));
      }
      const encoded=JSON.stringify(row);
      const imgs=files.filter(f=>/\.(jpg|jpeg|png|webp)$/i.test(f.name)&&encoded.includes(f.name)&&!shownImages.has(f.path));
      if(imgs.length){
        const gallery=el('div',undefined,'gallery');
        for(const f of imgs){image(gallery,f.path);shownImages.add(f.path);}
        section.append(gallery);
      }else if(row.tool_image){
        section.append(pre(row.tool_image));
      }
      card.append(section);
    }
    parent.append(card);
  }
}

function rolloutView(parent,files,rollouts){if(!rollouts.length){empty(parent);return;}const select=el('select');for(const r of rollouts)select.add(new Option(r.split('/').pop(),r));const body=el('div');parent.append(select,body);let request=0;select.onchange=async()=>{const token=++request;const dir=select.value;body.replaceChildren();const local=files.filter(f=>f.path.startsWith(dir+'/'));const find=name=>local.find(f=>f.path===dir+'/'+name)?.path;try{if(find('metrics.json')){const metric=JSON.parse(await textFile(find('metrics.json')));if(token!==request)return;const score=scored(metric);const p=el('div',undefined,'panel');p.append(el('h3','回答与评价'),pre({final_answer:metric.result?.final_answer,ground_truth:metric.result?.ground_truth,accuracy_score:score?.accuracy_score??null,explanation:score?.trajectory_analysis??'该评分未记录',extracted_answer:score?.extracted_answer}));body.append(p);lazy(body,'完整指标与保存的对话',find('metrics.json'));}if(find('injected_system_prompt.txt'))lazy(body,'实际注入的 system prompt',find('injected_system_prompt.txt'));if(find('traj.jsonl')){const raw=await textFile(find('traj.jsonl'));if(token!==request)return;trajectoryView(body,raw,local);}const pictures=local.filter(f=>/\.(jpg|jpeg|png|webp)$/i.test(f.name));if(pictures.length){const d=el('details');d.append(el('summary','本 rollout 的全部图片 · '+pictures.length));const gallery=el('div',undefined,'gallery');pictures.forEach(f=>image(gallery,f.path));d.append(gallery);body.append(d);}}catch(e){if(token===request)body.append(el('p',e.message,'error'));}};select.onchange();}
async function knowledge(parent){const files=await api('knowledge');parent.append(el('p','batch 快照保存的是处理前状态。以下差异仅描述文件变化，不推断合并原因或知识来源。','muted'));if(!files.length){empty(parent,'该实验没有可读的快照或 memory_bank；可切换到对应训练实验查看。');return;}const groups=Object.groupBy?Object.groupBy(files,f=>f.path.slice(0,f.path.lastIndexOf('/'))):files.reduce((a,f)=>{const k=f.path.slice(0,f.path.lastIndexOf('/'));(a[k]??=[]).push(f);return a;},{});for(const [name,items] of Object.entries(groups)){const d=el('details');d.append(el('summary',name+(name.startsWith('snapshots/')?' · 批次处理前':' · 当前文件')));for(const f of items)lazy(d,f.name,f.path);parent.append(d);}parent.append(el('h2','比较两个保存状态'));const left=el('select'),right=el('select'),kind=el('select');kind.add(new Option('经验库','experiences.json'));kind.add(new Option('技能文档','SKILL.md'));const controls=el('div',undefined,'columns');controls.append(kind,left,right);const run=el('button','查看差异');const out=el('div');parent.append(controls,run,out);kind.onchange=()=>{left.replaceChildren();right.replaceChildren();for(const f of files.filter(x=>x.name===kind.value)){left.add(new Option(f.path,f.path));right.add(new Option(f.path,f.path));}right.selectedIndex=Math.max(0,right.options.length-1);};kind.onchange();run.onclick=async()=>{try{if(!left.value||!right.value){empty(out);return;}const data=await api('diff',{left:left.value,right:right.value});out.replaceChildren();const p=el('pre');if(!data.diff)p.textContent='两个文件内容相同';else for(const line of data.diff.split('\n'))p.append(el('div',line,line.startsWith('+')?'added':line.startsWith('-')?'removed':''));out.append(p);}catch(e){showError(e);}};}
$('search').oninput=listSamples;$('evaluation').onchange=()=>render();$('refresh').onclick=()=>load().catch(showError);$('experiment').onchange=()=>{state.experiment=Number($('experiment').value);state.sample=null;state.view='overview';$('location').textContent=$('experiment').selectedOptions[0].dataset.path;load().catch(showError);};document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{state.view=b.dataset.view;render();});
(async()=>{const experiments=await api('experiments');for(const ex of experiments){const o=new Option(ex.name,ex.id);o.dataset.path=ex.path;$('experiment').add(o);}$('location').textContent=experiments[0]?.path||'';await load();})().catch(showError);
