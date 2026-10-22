const mediaTreeOpen = new Set();
const mediaSort = (a,b) => String(a).localeCompare(String(b),undefined,{numeric:true,sensitivity:'base'});
function mediaIDs(row){return ['imdb','tmdb','tvdb'].filter(kind=>row[kind+'_id']).map(kind=>kind+':'+String(row[kind+'_id']).trim().toLowerCase())}
function groupMedia(items){
    const groups=new Map();
    for(const row of items){
        const parts=row.relpath.split('/');const folder=parts.length>1?parts[0]:null;
        const key=JSON.stringify([row.library_id,folder===null?'file:'+row.id:folder]);
        if(!groups.has(key))groups.set(key,{key,library_id:row.library_id,folder,kind:row.kind,title:folder||row.relpath,rows:[]});
        groups.get(key).rows.push(row);
    }
    return [...groups.values()].sort((a,b)=>mediaSort(a.title,b.title)||mediaSort(a.key,b.key));
}
function fileCount(count){return `${count} ${count===1?'file':'files'}`}
const episodeMetadata=new Map(),episodeRequests=new Set();
function episodeKey(row){return JSON.stringify([row.id,mediaIDs(row),row.season,row.episode,row.episode_end])}
function episodeInfo(row){return episodeMetadata.get(episodeKey(row))}
function titleWithYear(title,year){return title?title+(year?' ('+year+')':''):'—'}
function mediaFile(row,depth=0){
    const info=episodeInfo(row);const bonus=row.extra_type;
    const episode=row.kind==='show'&&row.season!=null&&row.episode!=null?`S${String(row.season).padStart(2,'0')}E${String(row.episode).padStart(2,'0')}${row.episode_end?'–E'+String(row.episode_end).padStart(2,'0'):''}`:'';
    const name=info?.episode_title;
    const matched=titleWithYear(info?.title||row.matched_title,info?.year||row.matched_year||row.year_guess);
    const note=row.match_status==='error'?'Error':row.match_status!=='matched'?'Unmatched':'';
    return `<tr class="mediaFile"><td>${bonus?'Extra':row.kind==='show'?'TV':'Movie'}</td><td class="folderCell" style="padding-left:${16+depth*22}px"><span class="mediaFilename" title="${esc(row.real_path||row.relpath)}">${esc(row.relpath.split('/').pop())}</span></td><td>${esc(matched)}${bonus?'<small class="muted">Bonus video</small>':''}${episode?`<small class="episodeInfo">${esc(episode)}${name?' — '+esc(name):''}</small>`:''}${note?`<small class="warn">${note}</small>`:''}</td><td class="mediaIdentity">${esc(mediaIDs(row).join(' · ')||'—')}</td><td>${bonus?'<span class="muted">Uses folder match</span>':`<button class="matchBtn" data-kind="${row.kind}" data-id="${esc(row.id)}" data-file="${esc(row.relpath)}" data-title="${esc(info?.title||row.matched_title||row.title_guess||'')}" data-year="${esc(info?.year||row.matched_year||row.year_guess||'')}">${row.kind==='show'?'Match episode…':row.match_status==='matched'?'Rematch…':'Match…'}</button>`}</td></tr>`;
}
function rexFolderIndicator(rows){
 const missing=rows.filter(row=>row.rex_state!=='received');
 if(!missing.length)return '<small class="rexFolderState ok">✓ Complete in Rex</small>';
 if(rows.some(row=>!row.rex_state||row.rex_state==='unknown'))return '<small class="rexFolderState muted">Checking Rex…</small>';
 const episodes=missing.every(row=>row.kind==='show'&&row.season!=null&&row.episode!=null&&!row.extra_type);
 const unit=episodes?(missing.length===1?'episode':'episodes'):(missing.length===1?'file':'files');
 return `<small class="warn rexMissing">${missing.length} ${unit} not added to Rex</small>`;
}
function folderBranch(library,folder,rows,kind,depth=0){
    const name=folder.split('/').pop(),key=JSON.stringify([library,folder]),open=mediaTreeOpen.has(key);
    const matched=rows.filter(row=>row.match_status==='matched').length;
    const errors=rows.filter(row=>row.match_status==='error').length;
    const ids=[...new Set(rows.flatMap(mediaIDs))].sort(mediaSort);
    const titles=[...new Set(rows.filter(row=>row.match_status==='matched').map(row=>row.matched_title).filter(Boolean))];
    const years=[...new Set(rows.filter(row=>row.match_status==='matched').map(row=>row.matched_year).filter(Boolean))].sort();
    const label=errors?'Error':matched===rows.length?'Matched':matched?`${matched} of ${rows.length} matched`:'Unmatched';
    const title=titles.length===1?titleWithYear(titles[0],years.length===1?years[0]:null):titles.length?'Multiple titles':'—';
    let html=`<tr class="folderRow" data-tree-key="${esc(key)}"><td>${kind==='show'?'TV':'Movie'}</td><td class="folderCell" style="padding-left:${16+depth*22}px"><button type="button" class="folderToggle" data-tree-toggle="${esc(key)}" aria-expanded="${open}" title="${esc(folder)}"><span aria-hidden="true">${open?'▾':'▸'}</span> ${esc(name)}</button><small class="muted">${fileCount(rows.length)}</small>${rexFolderIndicator(rows)}</td><td>${esc(title)}${matched!==rows.length?`<small class="${errors?'bad':'warn'}">${label}</small>`:''}</td><td class="mediaIdentity">${esc(ids.join(' · ')||'—')}</td><td><button type="button" class="folderMatchBtn" data-library="${esc(library)}" data-folder="${esc(folder)}" data-title="${esc(titles.length===1?titles[0]:name)}">${matched?'Rematch…':'Match…'}</button></td></tr>`;
    if(!open)return html;
    const children=new Map(),files=[];
    for(const row of rows){const rest=row.relpath.slice(folder.length+1),parts=rest.split('/');if(parts.length===1)files.push(row);else{if(!children.has(parts[0]))children.set(parts[0],[]);children.get(parts[0]).push(row)}}
    html += [...children].sort(([a],[b])=>mediaSort(a,b)).map(([child,items])=>folderBranch(library,folder+'/'+child,items,kind,depth+1)).join('');
    return html+files.sort((a,b)=>mediaSort(a.relpath,b.relpath)).map(row=>mediaFile(row,depth+1)).join('');
}
function titleBranch(group){return group.folder===null?group.rows.map(row=>mediaFile(row)).join(''):folderBranch(group.library_id,group.folder,group.rows,group.kind)}
let currentTreeItems=[];
function renderMediaTree(items){
    currentTreeItems=items;
    const container=document.querySelector('#rows'),focused=document.activeElement;
    const focusKey=focused?.dataset.treeToggle;
    const focusFolder=focused?.classList.contains('folderMatchBtn')?[focused.dataset.library,focused.dataset.folder]:null;
    const focusFile=focused?.classList.contains('matchBtn')?focused.dataset.id:null;
    const markup=groupMedia(items).map(titleBranch).join('')||`<tr><td colspan="5" class="treeEmpty muted">${document.querySelector('#search').value||document.querySelector('#kind').value||document.querySelector('#status').value?'No files match these filters.':'Scanned files will appear here.'}</td></tr>`;
    if(container._treeMarkup===markup)return;
    container._treeMarkup=markup;container.innerHTML=markup;loadVisibleEpisodeNames(items);
    for(const button of container.querySelectorAll('button')){
        if((focusKey&&button.dataset.treeToggle===focusKey)||(focusFile&&button.classList.contains('matchBtn')&&button.dataset.id===focusFile)||(focusFolder&&button.classList.contains('folderMatchBtn')&&button.dataset.library===focusFolder[0]&&button.dataset.folder===focusFolder[1]))button.focus({preventScroll:true});
    }
}
document.addEventListener('click',event=>{const button=event.target.closest('[data-tree-toggle]');if(!button)return;const key=button.dataset.treeToggle;if(mediaTreeOpen.has(key))mediaTreeOpen.delete(key);else mediaTreeOpen.add(key);renderMediaTree(currentTreeItems)});

async function loadVisibleEpisodeNames(items){
 const visible=new Set([...document.querySelectorAll('.mediaFile .matchBtn[data-kind=show]')].map(button=>button.dataset.id));
 const pending=items.filter(row=>visible.has(row.id)&&row.match_status==='matched'&&!episodeMetadata.has(episodeKey(row))&&!episodeRequests.has(episodeKey(row))).slice(0,50);
 if(!pending.length)return;
 for(const row of pending)episodeRequests.add(episodeKey(row));
 try{const response=await api('/api/episodes/metadata',{method:'POST',body:{items:pending.map(row=>row.id)}});for(const row of pending)episodeMetadata.set(episodeKey(row),response.items[row.id]||null)}catch(error){for(const row of pending)episodeMetadata.set(episodeKey(row),null)}
 finally{for(const row of pending)episodeRequests.delete(episodeKey(row));renderMediaTree(currentTreeItems);loadVisibleEpisodeNames(currentTreeItems)}
}
