// Runs inside the dashboard's existing state closure.
let companyCategory = '大厂', companyNature = '', companySector = '', companyLimit = 24;
const companyCategories = ['大厂','央国企','金融机构','其他公司','全部公司'];
function chip(label, selected, handler, className='chip') {
  const b = document.createElement('button');
  b.className = className + (selected ? ' active' : ''); b.textContent = label;
  b.setAttribute('aria-pressed',String(selected)); b.onclick = handler; return b;
}
function companyOptions() {
  return {category:companyCategory,nature:companyNature,sector:companySector,query:$('companyQuery').value,sort:$('companySort').value};
}
function renderCompanyFilters() {
  $('companyCategories').replaceChildren(...companyCategories.map(c=>chip(c,c===companyCategory,()=>{
    companyCategory=c; companyNature=''; companySector=''; companyLimit=24;
    renderCompanyFilters(); renderCompanies();
  },'category-tab')));
  $('companyNatures').hidden = companyCategory!=='央国企';
  $('companyNatures').replaceChildren(...[['','全部'],['央企','央企'],['地方国企','地方国企'],['待细分国企','待细分']].map(([v,l])=>chip(l,companyNature===v,()=>{
    companyNature=v; companySector=''; companyLimit=24; renderCompanyFilters(); renderCompanies();
  })));
  const sectors = [...new Set(BoardCompanies.select(companyCatalog.groups,{category:companyCategory,nature:companyNature}).map(g=>g.sector))].sort((a,b)=>a.localeCompare(b,'zh'));
  const label = document.createElement('span'); label.className='filter-label'; label.textContent='行业';
  $('companySectors').replaceChildren(label,...['',...sectors].map(s=>chip(s||'全部',companySector===s,()=>{
    companySector=s; companyLimit=24; renderCompanyFilters(); renderCompanies();
  })));
}
function renderCompanies() {
  const groups = BoardCompanies.select(companyCatalog.groups,companyOptions());
  $('companyHeading').textContent = companyCategory + (companySector?' · '+companySector:'');
  $('companyCount').textContent = groups.length+' 家公司 / 集团';
  const grid=$('companyGrid'); grid.replaceChildren();
  let lastTier;
  groups.slice(0,companyLimit).forEach(g=>{
    if (companyCategory==='大厂' && $('companySort').value==='rank' && g.tier!==lastTier) {
      const title=document.createElement('h3'); title.className='tier-heading';
      title.textContent=g.tier===1?'头部大厂':'知名企业'; grid.appendChild(title); lastTier=g.tier;
    }
    const card=document.createElement('button'); card.className='company-card';
    const count=g.jobs.length;
    card.innerHTML=`<h3>${esc(g.name)}</h3><span class="card-meta">${esc(g.sector)}${companyCategory==='央国企'?' · '+(g.category==='待细分国企'?'性质待细分':esc(g.category)):''}</span><span class="card-foot"><span>${count} 条招聘信息</span><span aria-hidden="true">→</span></span>`;
    card.setAttribute('aria-label',g.name+'，'+count+'条招聘信息，查看岗位');
    card.onclick=()=>openCompany(g); grid.appendChild(card);
  });
  if (!groups.length) {
    const empty=document.createElement('div'); empty.className='empty-state';
    empty.textContent='当前分类没有匹配公司。';
    const all=document.createElement('button'); all.className='btn'; all.textContent='在全部公司中查找'; all.style.marginLeft='12px';
    all.onclick=()=>{companyCategory='全部公司';companyNature='';companySector='';companyLimit=24;renderCompanyFilters();renderCompanies();};
    empty.appendChild(all); grid.appendChild(empty);
  }
  $('moreCompanies').hidden=groups.length<=companyLimit;
  $('companyRankNote').textContent=companyCategory==='大厂'?'梯队为浏览顺序，可切换行业和排序。':companyCategory==='央国企'?'已确认的集团归并展示，其他国企保留原名，列入“待细分”。':'';
}
function showCompanyHome() {
  $('companyHome').hidden=false; $('jobsWorkspace').hidden=true;
  $('companiesTab').classList.add('active'); $('jobsTab').classList.remove('active');
  $('companiesTab').setAttribute('aria-pressed','true'); $('jobsTab').setAttribute('aria-pressed','false');
}
function showJobs() {
  $('companyHome').hidden=true; $('jobsWorkspace').hidden=false;
  $('companiesTab').classList.remove('active'); $('jobsTab').classList.add('active');
  $('companiesTab').setAttribute('aria-pressed','false'); $('jobsTab').setAttribute('aria-pressed','true');
}
function clearJobFilters() {
  $('q').value=''; $('fStatus').value='';
  ['fRef','fFree','fFav'].forEach(id=>$(id).checked=false);
  [msTag,msType,msJtype,msCity].forEach(m=>m.clear());
  document.querySelectorAll('.stat.active').forEach(s=>s.classList.remove('active'));
}
function openCompany(group) {
  activeCompany=group; clearJobFilters();
  $('companyContext').hidden=false; $('stats').hidden=true;
  $('activeCompanyName').textContent=group.name;
  $('activeCompanyMeta').textContent=group.jobs.length+' 条招聘信息 · '+group.units.length+' 个单位 / 业务条目';
  const options=[new Option('全部招聘单位 / 业务',''),...group.units.map(u=>new Option(u,u))];
  $('unitFilter').replaceChildren(...options); $('unitFilter').value='';
  $('unitFilter').hidden=group.units.length<2;
  showJobs(); applyFilters(); $('companyContext').scrollIntoView({block:'start'});
}
$('companiesTab').onclick=showCompanyHome;
$('jobsTab').onclick=()=>{activeCompany=null;$('companyContext').hidden=true;$('stats').hidden=false;$('unitFilter').value='';showJobs();applyFilters();};
$('backCompanies').onclick=()=>{showCompanyHome();$('companyHome').scrollIntoView({block:'start'});};
$('unitFilter').onchange=applyFilters;
$('companyQuery').oninput=()=>{companyLimit=24;renderCompanies();};
$('companySort').onchange=()=>{companyLimit=24;renderCompanies();};
$('moreCompanies').onclick=()=>{companyLimit+=24;renderCompanies();};
renderCompanyFilters(); renderCompanies();
