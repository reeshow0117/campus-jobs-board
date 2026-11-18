const {test} = require('node:test');
const assert = require('node:assert/strict');
const {identify,build,select} = require('../company_catalog.js');
const group = company => identify({company}).id;
test('business variants merge without crossing similarly named companies',()=>{
  assert.equal(group('腾讯WXG微信事业群'),'腾讯');
  assert.equal(group('阿里云智能集团'),'阿里巴巴');
  assert.equal(group('字节跳动-火山引擎'),'字节跳动');
  assert.equal(group('京东方科技集团'),'京东方');
  assert.equal(group('京东JDS'),'京东');
  assert.notEqual(group('北京东西分析仪器'),'京东');
  assert.notEqual(group('蚂蚁集团'),'阿里巴巴');
  assert.notEqual(group('荣耀'),'华为');
  assert.equal(group('华为问界-赛力斯'),'赛力斯');
  assert.equal(group('百度-度小满'),'度小满');
  assert.notEqual(group('卓驭科技(原大疆车载)'),'大疆');
  assert.notEqual(group('格力博集团'),'格力电器');
  assert.notEqual(group('美的置业集团'),'美的集团');
});
test('state enterprise groups and ambiguous ownership stay distinct',()=>{
  assert.equal(group('中铁一局集团'),'中国中铁');
  assert.equal(group('中铁十一局集团'),'中国铁建');
  assert.equal(group('中建材集团'),'中国建材');
  assert.equal(group('中国电子科技集团'),'中国电科');
  assert.equal(group('中国电子信息产业集团'),'中国电子');
  assert.equal(group('国家电力投资集团'),'国家电投');
  assert.notEqual(group('国家能源集团'),group('国家电力投资集团'));
  assert.equal(identify({company:'某城市建设集团',company_type:'央国企'}).category,'待细分国企');
  assert.equal(identify({company:'某银行',company_type:'银行'}).category,'金融机构');
});
test('every source record remains exactly once, with IDs and raw names intact',()=>{
  const jobs=[{id:'1',company:'腾讯'},{id:'2',company:'腾讯云智'},{id:'3',company:'中国移动'},{id:'4',company:'某公司'},{id:'5',company:'某公司'}];
  const before=JSON.stringify(jobs), catalog=build(jobs);
  assert.equal(catalog.groups.flatMap(g=>g.jobs).length,jobs.length);
  assert.equal(catalog.membership.size,jobs.length);
  assert.equal(catalog.groups.find(g=>g.id==='腾讯').units.length,2);
  assert.equal(JSON.stringify(jobs),before);
});
test('category, industry, unit search and rank ordering compose',()=>{
  const {groups}=build([{company:'联想'},{company:'腾讯云智'},{company:'国家电网'},{company:'上海电气'},{company:'未知国企',company_type:'央国企'}]);
  assert.deepEqual(select(groups,{category:'大厂'}).map(g=>g.name),['腾讯','联想']);
  assert.equal(select(groups,{category:'大厂',query:'云智'})[0].name,'腾讯');
  assert.equal(select(groups,{category:'大厂',sector:'硬件与通信'})[0].name,'联想');
  assert.equal(select(groups,{category:'央国企'}).length,3);
  assert.equal(select(groups,{category:'央国企',nature:'地方国企'})[0].name,'上海电气');
  assert.equal(select(groups,{category:'全部公司'}).length,5);
});
