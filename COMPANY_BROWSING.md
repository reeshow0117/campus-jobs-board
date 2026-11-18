# 公司浏览

首页默认按公司浏览，也可切换回全部岗位。大厂以人工维护的梯队、知名度顺序展示；这只是浏览顺序，不代表薪酬或雇主评价。央国企优先显示已整理的常见集团，再显示待细分单位，可按行业、企业性质筛选。

`company_catalog.js` 维护公司别名、分类、展示顺序；`company_browser.js` 负责首页和集团内单位筛选。构建器把两者内嵌到 HTML，单文件离线打开仍可使用。新增别名时需先核对集团归属，并补充容易混淆的名称验证。不能仅凭“大厂”标签或名字中的共享字词判定集团。

归并保留原始公司名称、招聘信息和 ID，收藏及投递状态沿用原有本地存储。无法确认归属的企业保留原名；仅被原数据标为央国企的企业，放入“待细分”，不擅自认定为央企或地方国企。公司卡片计数为招聘信息条目数，不是招聘人数；单位/业务条目也可能包含招聘批次。

规则核对参考：

- [国务院国资委央企名录](https://wap.sasac.gov.cn/n2588045/n27271785/n27271792/c14159097/content.html)
- [阿里巴巴业务介绍](https://www.alibabagroup.com/en-US/about/businesses)
- [字节跳动产品与服务](https://www.bytedance.com/products-services)
- [中国中铁企业资质](https://www.crecg.com/creci/gsjj/zzry/qyzz/index.html)
- [深圳国资委企业简介](https://gzw.sz.gov.cn/ztzl/gzgqztzl/gyqyxxgk/qyjj/)

验证：`node --test tests/company_catalog.test.js`，`python data/build_dashboard.py`。Cloudflare 继续使用现有构建命令，读取线上最新岗位数据，无需更改数据刷新流程。
