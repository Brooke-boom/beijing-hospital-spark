// ============================================================================
//  机构证据增强 —— 院区/挂牌证据 · 官方预约入口 · 出发点与地图导航
// ----------------------------------------------------------------------------
//  这个文件解决四个用户侧的真实困惑，每个都必须有据可查、不许编：
//
//  1) 院区与挂牌
//     「北京积水潭医院（回龙观院区）」是本院还是分院？「（301医院）」是不是又一家？
//     数据真源：data/processed/alias_map.csv（同一执业编码的挂牌别名，带 source 与
//     判定依据原文）+ 主表名称里的院区括号。判据写在 etl/export_campus_evidence.py，
//     产物内联为 window.__CAMPUS__；开发形态回退读同目录 campus_evidence.json。
//     ⚠️ 括号 ≠ 院区：主表 219 处括号是旧称/改名，这里一律单独归类、不冒充院区。
//
//  2) 官方预约入口
//     ⚠️ 本系统**不掌握也不模拟**任何号源、排班、候诊状态。因此这里只给
//     **平台级官方入口**（北京市预约挂号统一平台 / 114 电话 / 京医通）与该院
//     公开数据里已收录的官网、电话，**逐条标注核验日期**，绝不按机构编造
//     专属挂号链接 —— 编一个点不动的按钮比没有更糟。
//
//  3) 用户出发点
//     距离与导航都要有起点：我的定位 / 天安门 / 首都机场 / 大兴机场 / 任一机构。
//     沿用 app.js 既有的 curBase() 口径，域外一律标「市域外」，不臆造区名
//     （遵守 geolocation-out-of-bounds-guard）。
//
//  4) 地图导航跳转
//     用高德 URI：from=<出发坐标>&to=<目标坐标>&coordinate=gaode。
//     本项目坐标由 etl/geocode_amap.py 经高德 restapi 地理编码取得，本身就是
//     **GCJ-02**，与高德 URI 的 gaode 完全一致 —— 因此这里不需要任何坐标转换，
//     也就不会出现「导航走到几百米外」的经典错误。百度地图是 BD-09 体系，
//     直接塞 GCJ-02 会偏移，故不接入。
// ============================================================================
'use strict';

var EV = (function () {

  // 平台级官方入口。VERIFIED_ON = 我逐条 curl 实测可达的日期，
  // 不是一个「大概差不多」的时间；界面上原样显示，别改成自动计算的今天
  // ——自动算会让「今天可达」冒充「数据核验于今天」。
  var VERIFIED_ON = '2026-10-17';

  var OFFICIAL = {
    // 北京市预约挂号统一平台 —— 由北京市人民政府、北京市卫健委、北京12345服务导图
    // 三方口径一致确认（wjw.beijing.gov.cn 2019 年接入通知即写明
    // 「预约网址:http://www.114yygh.com,预约电话:114」）。
    platform: { name: '北京市预约挂号统一平台（114）', url: 'https://www.114yygh.com/',
                note: '官方平台入口 · 本系统不抓取号源与排班' },
    // 政务服务导图（市卫健委数据源），用于核对机构官方登记的预约方式。
    govmap:  { name: '北京12345 服务导图', url: 'https://map.beijing.gov.cn/',
                note: '市卫健委数据源 · 可按机构名检索官方登记的预约方式' },
  };

  var NAV_MODES = [
    { k: 'car',     label: '驾车' },
    { k: 'walk',    label: '步行' },
    { k: 'ride',    label: '骑行' },
    { k: 'transit', label: '公交' },
  ];

  var DATA_ = null;          // campus_evidence.json
  var LOADING = null;

  // ---------------------------------------------------------------- 数据装载
  function load() {
    if (DATA_ || LOADING) return LOADING;
    if (window.__CAMPUS__) { DATA_ = window.__CAMPUS__; return Promise.resolve(DATA_); }
    // 开发形态：app.js 以 <script src> 加载，没有内联 __CAMPUS__，回退读同目录 JSON。
    LOADING = fetch('campus_evidence.json')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { DATA_ = j || EMPTY(); return DATA_; })
      .catch(function () { DATA_ = EMPTY(); return DATA_; });
    return LOADING;
  }

  function EMPTY() {
    return { campus_groups: [], id2group: {}, aliases_by_host: {},
             legacy_count: 0, summary: {}, meta: {} };
  }

  function data() { return DATA_ || EMPTY(); }

  // ---------------------------------------------------------------- 工具
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function faint(c) { return '<span style="color:' + c + '">'; }

  function campusOf(r) {
    var d = data();
    var gi = (d.id2group || {})[String(r.id)];
    if (gi == null || !d.campus_groups || !d.campus_groups[gi]) return null;
    return d.campus_groups[gi];
  }
  function aliasesOf(r) {
    return (data().aliases_by_host || {})[String(r.id)] || null;
  }

  // ---------------------------------------------------------------- 院区 / 挂牌
  // 返回 HTML 或 ''。三类证据分开写，绝不混成一句「这家有好几个名字」。
  function campusBlock(r, C) {
    var g = campusOf(r), al = aliasesOf(r);
    if (!g && !al) return '';
    var h = '<div class="blk"><h4><span class="bar"></span>院区与挂牌证据' +
      '<span class="r">判据见 data/processed/govern_report_dedup_full.md</span></h4>';

    if (g) {
      var mine = g.members.filter(function (m) { return String(m.id) === String(r.id); })[0];
      h += '<div class="ibox"><div class="k">本机构院区</div><div class="v">' +
        (mine ? '<b>' + esc(mine.campus) + '</b>' : '—') +
        '<div class="mini" style="margin-top:4px;color:' + C.faint + ';font-size:10.5px;line-height:1.6">' +
        (g.sibling_count > 1
          ? '「' + esc(g.main_name) + '」在主表中按院区<b>分别建档</b>，共 ' + g.sibling_count + ' 条：' +
            g.members.map(function (m) {
              return (String(m.id) === String(r.id) ? '【' + esc(m.campus) + '】' : esc(m.campus));
            }).join('、') + '。这些是同一主办单位下的不同执业地点，不是重复收录。'
          : '「' + esc(g.main_name) + '」在本数据集中仅有本条院区记录。院区单独建档是既有口径，' +
            '不与本部合并——因此在列表里看到主名相同、括号不同的两条，是两个不同的执业地点。') +
        '</div></div></div>';

      if (g.sibling_count > 1) {
        h += '<div style="margin-top:8px"><div class="mini" style="color:' + C.faint +
          ';font-size:10.5px;margin-bottom:6px">同院区其他机构（点开看详情）</div><div class="deptchips">';
        g.members.forEach(function (m) {
          if (String(m.id) === String(r.id)) {
            h += '<span class="chip acc">' + esc(m.campus) + '（当前）</span>';
          } else {
            h += '<span class="chip" data-ev-open="' + esc(m.id) + '" style="cursor:pointer">' +
                 esc(m.campus) + ' · ' + esc(m.district || '') + '</span>';
          }
        });
        h += '</div></div>';
      }
    }

    if (al) {
      h += '<div class="ibox" style="margin-top:10px"><div class="k">同一执业编码下的挂牌名（' +
        al.length + ' 个）</div><div class="v">' +
        '<div class="deptchips">' + al.map(function (a) {
          return '<span class="chip">' + esc(a.alias_name) + '</span>';
        }).join('') + '</div>' +
        '<div class="mini" style="margin-top:6px;color:' + C.faint + ';font-size:10.5px;line-height:1.7">' +
        '这些不是独立机构，而是<b>同一个执业编码</b>下的多块牌子，已并入本机构统计；' +
        '在此单列是为了避免用户搜到其中任一名称时找不到结果。</div>';
      // 逐条给依据：有判定依据才配当证据展示，没有就说明白。
      h += '<div style="margin-top:8px">';
      al.forEach(function (a) {
        h += '<details class="evdet"><summary>' + esc(a.alias_name) + '</summary>' +
          '<div class="mini" style="color:' + C.faint + ';font-size:10.5px;line-height:1.7;margin-top:5px">' +
          '关系：' + esc(a.relation || '—') + '<br/>依据：' + esc(a.source || '—') + '<br/>' +
          esc(a.evidence || '') + '</div></details>';
      });
      h += '</div></div></div>';
    }
    return h + '</div>';
  }

  // ---------------------------------------------------------------- 官方预约入口
  function bookingBlock(r, C) {
    var w = esc(r.website || '');
    var hasWeb = !!String(r.website || '').trim();
    var h = '<div class="blk"><h4><span class="bar"></span>预约挂号入口' +
      '<span class="r">链接核验日期 ' + VERIFIED_ON + '</span></h4>';

    h += '<div class="linklist">';
    h += linkRow(C, '北京市预约挂号统一平台（114）',
      '电脑端入口 · 搜索机构名后选择科室与号源', OFFICIAL.platform.url);
    h += linkRow(C, '电话预约 114',
      '电话预约与平台同属统一平台，号源以平台实时信息为准', 'tel:114');
    h += linkRow(C, '北京12345 服务导图（市卫健委数据源）',
      '可查该机构官方登记的预约渠道、放号周期与咨询电话', OFFICIAL.govmap.url);
    if (hasWeb) {
      h += linkRow(C, '该院官网（本数据集收录）',
        '数据快照中的机构官网字段 · 本系统不核验其号源页', w);
    }
    h += '</div>';

    h += '<div class="mini" style="margin-top:9px;color:' + C.faint + ';font-size:10.5px;line-height:1.7">' +
      '<b>口径声明</b>：本系统是机构资源数据的查询与筛选平台，' +
      '数据集内<b>没有</b>各院号源、放号周期与排班数据，因此' +
      (hasWeb ? '上表的官网链接来自数据快照、未逐条核验；' : '本机构官网未被公开数据收录，无法给出；') +
      '所有号源信息请以北京市预约挂号统一平台的实时页面为准。' +
      (hasWeb ? '' : '若需确认该院是否接号，请在上方平台内搜索机构全称。') +
      '</div>';

    h += '<div class="mini" style="margin-top:6px;color:' + C.faint + ';font-size:10.5px;line-height:1.7">' +
      '链接核验日期 ' + VERIFIED_ON + '：指当日对平台与服务导图入口做过可达性实测，' +
      '<b>不代表</b>各院当日号源状态。数据快照中的电话字段（' +
      (r.phone ? esc(r.phone) : '本机构未收录') + '）同样来自公开数据，不做拨打核实。</div>';
    return h + '</div>';
  }

  function linkRow(C, title, desc, url) {
    return '<a class="evcard" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' +
      '<div class="lt">' + esc(title) + '</div><div class="ld">' + esc(desc) + '</div>' +
      '<div class="lu">' + esc(url) + '</div></a>';
  }

  // ---------------------------------------------------------------- 出发点与导航
  // 出发点选项：天安门 / 首都机场 / 大兴机场 / 我的位置 / 16 区人民政府（近似市中心）。
  // 区中心用各区政府驻地坐标，只作「从某个区出发」的合理近似，必须写明是近似。
  function originOptions(r) {
    var opts = [];
    if (window.__BASE_POINTS__) {
      Object.keys(window.__BASE_POINTS__).forEach(function (k) {
        var b = window.__BASE_POINTS__[k];
        if (!b || b.lng == null) return;
        opts.push({ k: b.name, name: b.name, lng: b.lng, lat: b.lat });
      });
    }
    return opts;
  }

  // 高德 URI 导航。coordinate=gaode 是关键：本项目坐标即 GCJ-02，不需要转换。
  function navUrl(fromLng, fromLat, fromName, r, mode) {
    if (r.lng == null || r.lat == null) return '';
    var to = r.lng + ',' + r.lat + ',' + (r.name || '医院');
    var u = 'https://uri.amap.com/navigation?to=' + encodeURIComponent(to) +
            '&mode=' + (mode || 'car') + '&coordinate=gaode&callnative=1&src=bj-hospital-dashboard';
    if (fromLng != null && fromLat != null) {
      u += '&from=' + encodeURIComponent(fromLng + ',' + fromLat + ',' + (fromName || '出发地'));
    }
    return u;
  }

  function navBlock(r, base, C) {
    if (r.lng == null || r.lat == null) {
      return '<div class="blk"><h4><span class="bar"></span>地图导航</h4>' +
        '<div class="mini" style="color:' + C.faint + ';font-size:11px">该机构无坐标，无法生成导航链接。</div></div>';
    }
    var h = '<div class="blk"><h4><span class="bar"></span>地图导航' +
      '<span class="r">坐标 GCJ-02 · 与高德同源无转换</span></h4>';

    h += '<div class="evorigin">' +
      '<label class="eok">出发点</label>' +
      '<select class="esel" id="ev_origin" data-ev-origin>' +
        originOptions(r).map(function (o, i) {
          var sel = (base && base.name === o.name) ? ' selected' : '';
          return '<option value="' + esc(o.k) + '"' + sel + '>' + esc(o.name) + '</option>';
        }).join('') +
        '<option value="__me"' + ((base && base.name === '我的位置') ? ' selected' : '') +
          (window.__BASE_NOW__ ? '' : ' disabled') + '>我的位置' + (window.__BASE_NOW__ ? '' : '（尚未定位）') + '</option>' +
      '</select></div>';

    h += '<div class="linklist" style="margin-top:8px">';
    NAV_MODES.forEach(function (m) {
      var u = navUrl(base && base.lng, base && base.lat, base && base.name, r, m.k);
      h += linkRow(C, '高德地图 · ' + m.label + '导航',
        '从「' + esc((base && base.name) || '天安门') + '」到 ' + esc(r.name || '该机构') +
        '（直线约 ' + kmText(base, r, C) + '）', u);
    });
    h += linkRow(C, '北京12345 服务导图（市卫健委）',
      '按机构名检索官方登记的执业地点与联系方式', OFFICIAL.govmap.url);
    h += '</div>';

    h += '<div class="mini" style="margin-top:9px;color:' + C.faint + ';font-size:10.5px;line-height:1.7">' +
      '导航链接为高德 URI，坐标体系 GCJ-02 —— 本项目坐标由高德开放平台地理编码取得，' +
      '与该体系一致，<b>不做任何转换</b>，因此不会出现按国内坐标系纠偏前的偏移。' +
      '上方距离为球面直线距离（非路网里程），实际路程以地图规划结果为准。</div>';
    return h + '</div>';
  }

  function kmText(base, r, C) {
    if (!base || base.lng == null || r.lng == null) return '—';
    var R = 6371, rad = Math.PI / 180;
    var dLat = (r.lat - base.lat) * rad, dLng = (r.lng - base.lng) * rad;
    var a = Math.pow(Math.sin(dLat / 2), 2) + Math.cos(base.lat * rad) * Math.cos(r.lat * rad) *
            Math.pow(Math.sin(dLng / 2), 2);
    return (2 * R * Math.asin(Math.sqrt(a))).toFixed(1) + ' km';
  }

  // ---------------------------------------------------------------- 对比表补充
  // 对比表新增三行：院区形态 / 挂牌名 / 科室证据来源。
  function campusCell(r) {
    var g = campusOf(r), al = aliasesOf(r);
    if (!g && !al) return { text: '无院区或挂牌记录', evidence: '—', pick: false };
    var parts = [];
    if (g) {
      var mine = g.members.filter(function (m) { return String(m.id) === String(r.id); })[0];
      parts.push(mine ? mine.campus : '院区');
      if (g.sibling_count > 1) parts.push('同主名下共 ' + g.sibling_count + ' 条院区建档');
    }
    if (al) parts.push(al.length + ' 个同编码挂牌名');
    return {
      text: parts.join(' · '),
      evidence: g ? ('判据：主名相同且括号内含院区/分院/总院') : (al ? '判据：同一执业编码' : '—'),
      pick: true,
    };
  }

  function deptEvidenceCell(r) {
    // dept_count_src 非空 = 在线逐家核实的真实值；否则是按「名称 / 机构类型职能」推导的值。
    // 两种口径不能并列成「科室多/少」，所以对比表里这一行给的是**证据强度**，不是数量高低。
    var src = String(r.dept_count_src || '');
    if (src) { var names={haodf_claim:'好大夫科室数量记录',haodf_list:'好大夫科室列表',baike_claim:'百科科室数量记录',baike_table:'百科科室表格'};return { text:'科室数量有来源记录',detail:'来源：'+(names[src]||'公开来源记录'),strong:true }; }
    if (Number(r.dept_count || 0) > 0) {
      return { text: '规则推导（未核实）', detail: '按「机构名称 / 机构类型职能」推导，不作为事实展示', strong: false };
    }
    return { text: '未收录', detail: '公开数据中无科室登记', strong: false };
  }

  return {
    load: load,
    data: data,
    VERIFIED_ON: VERIFIED_ON,
    OFFICIAL: OFFICIAL,
    NAV_MODES: NAV_MODES,
    campusBlock: campusBlock,
    bookingBlock: bookingBlock,
    navBlock: navBlock,
    navUrl: navUrl,
    originOptions: originOptions,
    campusCell: campusCell,
    deptEvidenceCell: deptEvidenceCell,
    kmText: kmText,
    esc: esc,
  };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = { EV: EV };