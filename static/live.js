(() => {
  const $ = (id) => document.getElementById(id);
  let latestCards = [];
  let cardOffset = 0;

  function topOf(obj){
    const entries=Object.entries(obj||{}).sort((a,b)=>b[1]-a[1]);
    return entries[0] || null;
  }
  function renderBars(id, data, maxRows=7){
    const el=$(id); el.innerHTML='';
    const rows=Object.entries(data||{}).sort((a,b)=>b[1]-a[1]).slice(0,maxRows);
    if(!rows.length){el.innerHTML='<div class="empty-live">응답 대기 중</div>';return;}
    const max=Math.max(...rows.map(x=>x[1]),1);
    rows.forEach(([label,count])=>{
      const row=document.createElement('div'); row.className='bar-row';
      const pct=Math.max(5,Math.round(count/max*100));
      row.innerHTML=`<div class="bar-label"><span>${escapeHtml(label)}</span><b>${count}</b></div><div class="bar-track"><i style="width:${pct}%"></i></div>`;
      el.appendChild(row);
    });
  }
  function escapeHtml(s){
    return String(s??'').replace(/[&<>'"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  function renderKeywords(words){
    const el=$('keywordCloud'); el.innerHTML='';
    if(!words?.length){el.innerHTML='<span class="muted">응답이 들어오면 자동으로 나타납니다.</span>';return;}
    const max=Math.max(...words.map(x=>x.count));
    words.forEach((x,i)=>{
      const s=document.createElement('span'); s.className='keyword';
      const size=17 + Math.round((x.count/max)*24);
      s.style.fontSize=size+'px'; s.style.opacity=String(Math.max(.45,1-i*.025)); s.textContent=x.word;
      el.appendChild(s);
    });
  }
  function renderCards(){
    const el=$('responseCards'); el.innerHTML='';
    if(!latestCards.length){el.innerHTML='<div class="empty-live">아직 자유응답이 없습니다.</div>';return;}
    const subset=[];
    for(let i=0;i<Math.min(3,latestCards.length);i++) subset.push(latestCards[(cardOffset+i)%latestCards.length]);
    subset.forEach(c=>{
      const card=document.createElement('article'); card.className='voice-card';
      card.innerHTML=`<div class="voice-meta"><span>${escapeHtml(c.category||'업무')}</span><span>${escapeHtml(c.frequency||'')}</span><span>${escapeHtml(c.rule||'')}</span></div><h3>${escapeHtml(c.title)}</h3>${c.detail?`<p>${escapeHtml(c.detail)}</p>`:''}`;
      el.appendChild(card);
    });
  }
  async function refresh(){
    try{
      const res=await fetch(window.LIVE_API,{cache:'no-store'}); if(!res.ok) throw new Error('HTTP '+res.status);
      const d=await res.json();
      $('responseCount').textContent=d.response_count??0;
      const tc=topOf(d.distributions?.q1); $('topCategory').textContent=tc?tc[0]:'응답 대기 중'; $('topCategoryCount').textContent=tc?`${tc[1]}명`:'-';
      const tr=topOf(d.distributions?.q4); $('topReason').textContent=tr?tr[0]:'응답 대기 중'; $('topReasonCount').textContent=tr?`${tr[1]}명 선택`:'-';
      $('aiAverage').textContent=d.ai_average==null?'-':d.ai_average.toFixed(1);
      renderBars('categoryChart',d.distributions?.q1,7); renderBars('reasonChart',d.distributions?.q4,8); renderKeywords(d.keywords||[]);
      latestCards=d.cards||[]; cardOffset=Math.min(cardOffset,Math.max(0,latestCards.length-1)); renderCards();
      $('updateIndicator').innerHTML='● LIVE · <span>방금 갱신</span>';
    }catch(e){$('updateIndicator').innerHTML='● LIVE · <span>연결 확인 중</span>';}
  }
  $('shuffleBtn')?.addEventListener('click',()=>{if(latestCards.length){cardOffset=(cardOffset+3)%latestCards.length;renderCards();}});
  refresh(); setInterval(refresh,2000);
})();
