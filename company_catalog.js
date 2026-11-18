/* Company browsing rules. Source records and job IDs are never rewritten. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BoardCompanies = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const rules = [];
  function add(name, category, sector, tier, aliases, exclude) {
    rules.push({id:name, name, category, sector, tier, rank:rules.length,
      aliases:[...new Set([name,...(aliases || [])])], exclude:exclude || []});
  }
  const tech = (n,s,t,a,e) => add(n,'大厂',s,t,a,e);
  tech('腾讯','互联网',1,['腾讯','PUBG MOBILE国际发行部（腾讯旗下）']);
  tech('阿里巴巴','互联网',1,['阿里巴巴','阿里云','阿里国际','阿里淘天','淘天','阿里妈妈','阿里灵犀','高德地图','飞猪','虎鲸文娱','菜鸟集团','钉钉','饿了么','盒马']);
  tech('字节跳动','互联网',1,['字节跳动','抖音集团','火山引擎']);
  tech('华为','硬件与通信',1,['华为','海思'],['华为问界']);
  tech('百度','互联网',1,['百度'],['百度-度小满','百度·度小满']);
  tech('美团','互联网',1); tech('京东','互联网',1,['京东'],['京东方']);
  tech('拼多多','互联网',1,['拼多多','拼多多集团','多多买菜']);
  tech('网易','互联网',1); tech('蚂蚁集团','金融科技',1,['蚂蚁集团','蚂蚁技术研究院','蚂蚁（']);
  tech('小米','硬件与通信',1); tech('快手','互联网',1); tech('小红书','互联网',1);
  tech('大疆','硬件与通信',1,['大疆','深圳市大疆']);
  tech('比亚迪','汽车',1); tech('宁德时代','新能源',1);
  tech('联想','硬件与通信',2); tech('中兴通讯','硬件与通信',2);
  tech('荣耀','硬件与通信',2); tech('OPPO','硬件与通信',2,['OPPO']); tech('vivo','硬件与通信',2,['vivo']);
  tech('京东方','硬件与通信',2,['京东方','BOE京东方']);
  tech('携程','互联网',2); tech('哔哩哔哩','互联网',2,['哔哩哔哩','B站']); tech('滴滴','互联网',2);
  tech('米哈游','游戏',2); tech('莉莉丝','游戏',2); tech('完美世界','游戏',2); tech('三七互娱','游戏',2);
  tech('科大讯飞','人工智能',2,['科大讯飞','讯飞']); tech('商汤','人工智能',2); tech('旷视','人工智能',2);
  tech('理想汽车','汽车',2); tech('蔚来','汽车',2); tech('小鹏','汽车',2); tech('吉利','汽车',2);
  tech('长城汽车','汽车',2); tech('赛力斯','汽车',2,['赛力斯','华为问界']); tech('零跑','汽车',2);
  tech('美的集团','家电与制造',2,['美的集团','美的（','美的-','美的·'],['美的置业']);
  tech('格力电器','家电与制造',2,['格力电器','珠海格力','格力·珠海凌达']);
  tech('海尔','家电与制造',2); tech('海信','家电与制造',2); tech('TCL','家电与制造',2,['TCL']);
  tech('传音','硬件与通信',2); tech('华勤','硬件与通信',2); tech('韶音','硬件与通信',2);
  tech('度小满','金融科技',2,['度小满','百度-度小满','百度·度小满']);
  tech('卓驭科技','汽车',2,['卓驭','【原大疆车载】卓驭']);
  tech('微软','互联网',1,['微软','Microsoft']); tech('谷歌','互联网',1,['谷歌','Google']);
  tech('苹果','硬件与通信',1,['苹果公司','苹果（','Apple']); tech('英伟达','硬件与通信',1,['英伟达','NVIDIA']);
  tech('亚马逊','互联网',1,['亚马逊','Amazon']); tech('特斯拉','汽车',1,['特斯拉','Tesla']);
  const soe = (n,s,a) => add(n,'央企',s,1,a);
  soe('国家电网','能源电力',['国家电网','国网']); soe('南方电网','能源电力',['中国南方电网','南方电网','南网']);
  soe('中国移动','通信',['中国移动','中移']); soe('中国电信','通信',['中国电信','中电信']); soe('中国联通','通信',['中国联通','联通集团']);
  soe('中国石油','能源电力',['中国石油天然气','中国石油（','中国石油集团','中石油']);
  soe('中国石化','能源电力',['中国石化','中国石油化工','中石化']); soe('中国海油','能源电力',['中国海油','中国海洋石油','中海油']);
  soe('国家能源集团','能源电力',['国家能源集团','国家能源投资','中国神华']);
  soe('国家电投','能源电力',['国家电投','国家电力投资']); soe('中国华能','能源电力',['中国华能','华能集团']);
  soe('中国大唐','能源电力',['中国大唐','大唐集团']); soe('中国华电','能源电力',['中国华电','华电集团']);
  soe('三峡集团','能源电力',['中国长江三峡','三峡集团']); soe('中广核','能源电力',['中广核','中国广核']);
  soe('中核集团','能源电力',['中国核工业','中核']); soe('国家管网','能源电力',['国家管网']);
  soe('中国航天科技','航空航天',['中国航天科技','航天科技集团']); soe('中国航天科工','航空航天',['中国航天科工','航天科工']);
  soe('中国航空工业','航空航天',['中国航空工业','航空工业集团','中航工业']); soe('中国航发','航空航天',['中国航发','中国航空发动机']);
  soe('中国商飞','航空航天',['中国商飞','中国商用飞机']); soe('中国船舶','装备制造',['中国船舶']);
  soe('中国电科','电子科技',['中国电科','中国电子科技','中电科']); soe('中国电子','电子科技',['中国电子信息','中国电子（','中国电子集团']);
  soe('中国兵器工业','装备制造',['中国兵器工业','兵器工业集团']); soe('中国兵器装备','装备制造',['中国兵器装备','兵器装备集团']);
  soe('中国中车','装备制造',['中国中车','中车']); soe('中国一汽','汽车',['中国一汽','一汽']); soe('东风汽车','汽车',['东风汽车']);
  soe('中国长安汽车','汽车',['中国长安汽车','长安汽车']);
  soe('中国建筑','建筑基建',['中国建筑','中建']);
  soe('中国建材','钢铁材料',['中国建材','中建材']);
  soe('中国中铁','建筑基建',['中国中铁','中国铁路工程','中铁一局','中铁二局','中铁三局','中铁四局','中铁五局','中铁六局','中铁七局','中铁八局','中铁九局','中铁十局','中铁建工']);
  soe('中国铁建','建筑基建',['中国铁建','中国铁道建筑','中铁十一局','中铁十二局','中铁十三局','中铁十四局','中铁十五局','中铁十六局','中铁十七局','中铁十八局','中铁十九局','中铁二十局','中铁二十一局','中铁二十二局','中铁二十三局','中铁二十四局','中铁二十五局','中铁建设']);
  soe('中国交建','建筑基建',['中国交建','中国交通建设','中交']); soe('中国电建','建筑基建',['中国电建','中国电力建设']); soe('中国能建','建筑基建',['中国能建','中国能源建设']);
  soe('招商局集团','综合集团',['招商局']); soe('华润集团','综合集团',['华润']); soe('保利集团','综合集团',['中国保利','保利集团','保利发展']);
  soe('中粮集团','综合集团',['中粮']); soe('中国中化','综合集团',['中国中化','中化集团']); soe('中国五矿','综合集团',['中国五矿','五矿集团']);
  soe('中国宝武','钢铁材料',['中国宝武','宝武集团','宝钢']); soe('鞍钢集团','钢铁材料',['鞍钢']); soe('中国铝业','钢铁材料',['中国铝业','中铝']);
  soe('中远海运','交通物流',['中国远洋海运','中远海运']); soe('中国国航','交通物流',['中国国际航空','中国国航']);
  soe('中国东航','交通物流',['中国东方航空','中国东航']); soe('中国南航','交通物流',['中国南方航空','中国南航']);
  soe('中国国药','医药健康',['中国医药集团','国药集团']);
  add('上汽集团','地方国企','汽车',1,['上汽集团','上海汽车集团']);
  add('上海电气','地方国企','装备制造',1,['上海电气']);
  add('上海建工','地方国企','建筑基建',1,['上海建工']);
  add('山东能源','地方国企','能源电力',1,['山东能源','兖矿能源']);
  add('深圳市投资控股','地方国企','综合集团',1,['深圳市投资控股','深圳投控']);
  ['中国工商银行','中国建设银行','中国农业银行','中国银行','交通银行','中国邮政储蓄银行','招商银行','中信银行','浦发银行','兴业银行','中国民生银行','平安银行','中国光大银行','华夏银行','广发银行'].forEach(n=>add(n,'金融机构','银行',1,[n]));
  const norm = s => String(s || '').normalize('NFKC').replace(/\s+/g,'').toLowerCase();
  // Longest alias wins. Shared substrings (e.g. 京东/京东方) cannot steal matches.
  const aliases = rules.flatMap(r=>r.aliases.map(a=>({rule:r, key:norm(a)}))).sort((a,b)=>b.key.length-a.key.length);
  function identify(job) {
    const raw = String(job.company || '').trim() || '未注明公司';
    const name = norm(raw);
    const hit = aliases.find(a=>name.startsWith(a.key) && !a.rule.exclude.some(e=>name.startsWith(norm(e))));
    if (hit) return hit.rule;
    const kind = String(job.company_type || '') + ' ' + String(job.industry || '');
    const category = /银行|证券|保险|基金|金融/.test(kind) ? '金融机构' : /央国企|国企|央企/.test(kind) ? '待细分国企' : '其他公司';
    return {id:'raw:'+norm(raw),name:raw,category,sector:category==='金融机构'?'其他金融':'其他',tier:3,rank:9999};
  }
  function build(jobs) {
    const groups = new Map(), membership = new Map();
    for (const job of jobs) {
      const meta = identify(job);
      if (!groups.has(meta.id)) groups.set(meta.id,{...meta,jobs:[],units:new Set()});
      const group = groups.get(meta.id);
      group.jobs.push(job); group.units.add(String(job.company || '').trim() || '未注明公司');
      membership.set(job, group.id);
    }
    return {groups:[...groups.values()].map(g=>({...g,units:[...g.units].sort((a,b)=>a.localeCompare(b,'zh'))})),membership};
  }
  function select(groups, options) {
    const {category='大厂',nature='',sector='',query='',sort='rank'}=options || {};
    const q = norm(query);
    return groups.filter(g=>(category==='全部公司' || category==='央国企' && ['央企','地方国企','待细分国企'].includes(g.category) || category===g.category)
      && (!nature || g.category===nature) && (!sector || g.sector===sector)
      && (!q || norm(g.name).includes(q) || g.units.some(u=>norm(u).includes(q))))
      .sort((a,b)=>sort==='name'?a.name.localeCompare(b.name,'zh'):sort==='count'?b.jobs.length-a.jobs.length || a.rank-b.rank : a.tier-b.tier || a.rank-b.rank || a.name.localeCompare(b.name,'zh'));
  }
  return {build,select,identify};
});
