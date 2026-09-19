// ============================================================================
//  就医决策主线 —— 单文件形态的离线复算引擎
// ----------------------------------------------------------------------------
//  为什么需要这个文件：
//    单文件大屏原本只有「查阅」能力，主线（说需求 → 分诊 → 对比 → 出方案）要连后端
//    /api/plan 才能跑。分享出去（GitHub Pages）点「就医决策」只能掉进 404。
//    这里把后端 api_plan 的**判科 + 打分 + 排序**原样搬到前端，用内嵌的
//    offline_plan_data.json（科室实力指数 + 疾病知识库 + 常量）本地复算，
//    于是单文件同时具备查阅与办事两种形态，且不依赖任何服务。
//
//  一致性纪律（改动前必读）：
//    本文件的每个公式都与 web/app.py 的 api_plan() 一一对应，包括
//      · 知识库命中的「最高权重优先」与「科室族 0.9 倍展开」
//      · 人群词 ×1.6 加权（PLAN_CROWD_BOOST）
//      · 未设基准点时把距离权重按比例并入实力与等级
//      · **先四舍五入到 4 位再排序**（后端就是这么排的，顺序敏感）
//      · 排序兜底链：评分 → 实力分 → 科室数 → 名称
//    任何一处偏差都会让离线结果与在线接口不一致，改完请跑
//      python etl/verify_offline_plan.py
//    用同一批输入逐项比对两边的判科、候选顺序与匹配度。
// ============================================================================
'use strict';

var PlanEngine = (function () {
  // ---------- 与后端同源的小工具 ----------

  // 保留 n 位小数。后端用的是 Python round（银行家舍入），这里用四舍五入，
  // 差异只可能出现在恰好 x.xxx5 的边界上，对排序的实际影响可忽略；
  // 若验证脚本报出顺序不一致，优先怀疑这里。
  function roundN(x, n) {
    const f = Math.pow(10, n);
    return Math.round(x * f) / f;
  }

  // 两点间距离（km）——与 app.py 的 haversine()、app.js 的同名实现一致
  function planHaversine(lng1, lat1, lng2, lat2) {
    const rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad, dLng = (lng2 - lng1) * rad;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * 6371.0 * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  // ---------- difflib.SequenceMatcher.ratio 的等价实现 ----------
  // 后端用 difflib.get_close_matches 做区名错别字纠正（如「朝羊区」→「朝阳区」），
  // 相似度用的是 2M/(la+lb)，M 为所有匹配块长度之和，故此处照搬该算法。
  // 区名都很短（<8 字），difflib 的 autojunk 对 200 元素以下的序列不生效，无需模拟。
  function longestMatch(a, alo, ahi, b, blo, bhi) {
    let besti = alo, bestj = blo, bestsize = 0;
    let j2len = new Map();
    for (let i = alo; i < ahi; i++) {
      const next = new Map();
      for (let j = blo; j < bhi; j++) {
        if (a[i] !== b[j]) continue;
        const k = (j2len.get(j - 1) || 0) + 1;
        next.set(j, k);
        if (k > bestsize) { besti = i - k + 1; bestj = j - k + 1; bestsize = k; }
      }
      j2len = next;
    }
    return [besti, bestj, bestsize];
  }

  function ratio(a, b) {
    if (!a.length && !b.length) return 1;
    let total = 0;
    const queue = [[0, a.length, 0, b.length]];
    while (queue.length) {
      const seg = queue.pop();
      const [i, j, k] = longestMatch(a, seg[0], seg[1], b, seg[2], seg[3]);
      if (!k) continue;
      total += k;
      if (seg[0] < i && seg[2] < j) queue.push([seg[0], i, seg[2], j]);
      if (i + k < seg[1] && j + k < seg[3]) queue.push([i + k, seg[1], j + k, seg[3]]);
    }
    return 2 * total / (a.length + b.length);
  }

  // ---------- 引擎实例 ----------
  // payload    = window.__PLAN_DATA__（etl/export_offline_plan_data.py 产出）
  // institutions = 快照里的 9789 家机构（window.__SNAPSHOT__.institutions）
  function create(payload, institutions) {
    if (!payload || !payload.strength) throw new Error('离线主线数据包缺失');
    const C = payload.const;
    const DEPTS = payload.depts;
    const TIER_LABEL = payload.tier_label;

    // 机构索引：id → 机构记录
    const instById = new Map();
    for (const r of institutions) instById.set(String(r.id), r);

    // 科室倒排：deptIdx → 该科室的行下标数组（避免每次查询全表扫 1.6 万行）
    const byDept = new Map();
    payload.strength.forEach(function (row, i) {
      let arr = byDept.get(row[1]);
      if (!arr) { arr = []; byDept.set(row[1], arr); }
      arr.push(i);
    });

    const deptIdxOf = new Map();
    DEPTS.forEach(function (d, i) { deptIdxOf.set(d, i); });

    // 别名按长度降序替换（长别名先替换，避免「心脏外科」被「外科」截胡）——
    // 与 app.py 的 _norm_depts() 同一策略；同长度保持声明序（JS 的 sort 自 ES2019 稳定）
    const ALIAS_KEYS = Object.keys(C.DEPT_ALIAS).sort(function (a, b) { return b.length - a.length; });

    function normDepts(text) {
      for (const alias of ALIAS_KEYS) {
        if (text.indexOf(alias) >= 0) text = text.split(alias).join(C.DEPT_ALIAS[alias]);
      }
      return text;
    }

    // 区名错别字纠正：只对「以区结尾的 2~4 字片段」做模糊匹配，避免把普通词误判成区名
    function correctDistrict(q) {
      if (!q) return null;
      const cands = q.match(/[\u4e00-\u9fa5]{2,4}区/g) || [];
      for (const cand of cands) {
        if (C.BJ_DISTRICTS.indexOf(cand) >= 0) continue;
        let best = null, bestR = 0.6;         // cutoff=0.6，与 get_close_matches 一致
        for (const dz of C.BJ_DISTRICTS) {
          const r = ratio(cand, dz);
          if (r > bestR) { bestR = r; best = dz; }
        }
        if (best) return { from: cand, to: best };
      }
      return null;
    }

    // 症状文本 → 目标科室。返回 {matched: Map<科室,{w,emg,kw}>, district, correction}
    function matchDepts(q, extra, forcedDept) {
      const correction = q ? correctDistrict(q) : null;
      const qNorm = correction ? q.split(correction.from).join(correction.to) : (q || '');

      let district = '';
      for (const dz of C.BJ_DISTRICTS) { if (qNorm.indexOf(dz) >= 0) { district = dz; break; } }
      if (!district && correction) district = correction.to;

      const matched = new Map();
      if (forcedDept) {
        matched.set(forcedDept, { w: 1.0, emg: forcedDept === '急诊科', kw: '手动选择科室' });
        return { matched, district, correction };
      }

      const matchText = normDepts(qNorm + (extra ? ' ' + extra : ''));
      // ① 知识库关键词命中，同科室取权重最高的一条
      for (const item of payload.kb) {
        const kw = item[0], dept = DEPTS[item[1]];
        if (kw && matchText.indexOf(kw) >= 0) {
          const old = matched.get(dept);
          if (!old || item[2] > old.w) matched.set(dept, { w: item[2], emg: !!item[3], kw: kw });
        }
      }
      // ② 直接说科室名也能命中
      for (const item of payload.kb) {
        const dept = DEPTS[item[1]];
        if (matchText.indexOf(dept) >= 0 && !matched.has(dept)) {
          matched.set(dept, { w: item[2], emg: !!item[3], kw: '科室名' });
        }
      }
      // ③ 人群词加权（孩子 / 老人 / 孕妇）
      for (const dept of Object.keys(C.PLAN_CROWD_BOOST)) {
        if (!matched.has(dept)) continue;
        const words = C.PLAN_CROWD_BOOST[dept];
        if (!words.some(function (x) { return matchText.indexOf(x) >= 0; })) continue;
        const m = matched.get(dept);
        matched.set(dept, { w: roundN(m.w * C.PLAN_CROWD_FACTOR, 3), emg: m.emg, kw: m.kw });
      }
      // ④ 科室族展开（妇产科↔妇科↔产科、耳鼻咽喉科↔耳鼻喉科），0.9 倍权重。
      //    ⚠️ 必须遍历 key 的快照：族展开新增的兄弟科室不再二次展开（后端同此语义）
      for (const dept of Array.from(matched.keys())) {
        const m = matched.get(dept);
        const sibs = C.PLAN_DEPT_FAMILY[dept] || [];
        for (const sib of sibs) {
          const w1 = roundN(m.w * 0.9, 3);
          const cur = matched.get(sib);
          if (!cur || w1 > cur.w) matched.set(sib, { w: w1, emg: m.emg, kw: m.kw + '·同类科室' });
        }
      }
      return { matched, district, correction };
    }

    // 机构名规范化（判同院用）：去掉括号后缀 + 截断到第一个机构类型词。
    // 库里同一家医院可能以多个名条各存一份，不合并会让推荐位被同一家占满。
    function normHospName(name) {
      const s = String(name || '').replace(/[（(][^）)]*[）)]/g, '').trim();
      const m = s.match(/^(.*?(?:医院|门诊部|卫生院|卫生服务中心|疗养院|诊所))/);
      return m ? m[1] : s;
    }

    // 同院多科室 / 多名条时挑选「代表记录」的确定序，与 app.py 的 _best_row_key() 同序：
    // 实力分高者优先，同分比科室名，再比机构 id。少了后两级，结果就会随遍历顺序漂移。
    function bestRowKey(row, deptName) {
      return [-(row[3] || 0), deptName || '', String(row[0])];
    }
    function cmpKey(a, b) {
      for (let i = 0; i < a.length; i++) {
        if (a[i] < b[i]) return -1;
        if (a[i] > b[i]) return 1;
      }
      return 0;
    }

    // 科室大类（与 Spark 侧 dept_dict.DEPT_CATEGORY、app.py 的 _dept_category_of 同源）
    const CATEGORY_OF = [
      ['内科', ['心血管内科', '呼吸内科', '消化内科', '神经内科', '内分泌科', '肾病科',
        '风湿免疫科', '血液内科', '感染科', '肝病科', '老年病科', '普内科', '变态反应科']],
      ['外科', ['普通外科', '骨科', '泌尿外科', '神经外科', '胸外科', '心脏大血管外科',
        '整形外科', '乳腺外科', '肛肠外科']],
      ['妇儿', ['妇产科', '妇科', '产科', '儿科', '生殖医学科']],
      ['中医', ['中医科', '中医内科', '中医骨伤科', '针灸推拿科', '中西医结合科']],
      ['急诊', ['急诊科', '重症医学科']],
      ['全科', ['全科医疗科']],
    ];
    function deptCategoryOf(dept) {
      for (const pair of CATEGORY_OF) {
        if (pair[1].indexOf(dept) >= 0) return pair[0];
      }
      return '专科';
    }

    // 候选打分 + 排序（对应 app.py 中 api_plan 的候选构造与 sort）
    // ⚠️ 入参字段名与后端 /api/plan 的 JSON 契约**完全一致**（snake_case）：
    //    q / dept / extra / district / level / public_only / prefer / max_km /
    //    top_n / lng / lat / base_name
    //    刻意不做 camelCase 转换 —— 曾经用 publicOnly 这类名字，结果调用方传 public_only
    //    时过滤条件被静默忽略（离线池比 SQL 直查还多），这类错不会报错、只会给出错结果。
    function run(opts) {
      opts = opts || {};
      const q = (opts.q || '').trim();
      const forcedDept = (opts.dept || '').trim();
      const extra = (opts.extra || '').trim();
      if (!q && !forcedDept) {
        return { ok: false, reason: 'empty', hint: '请描述症状（如「心慌」「骨折」），或直接选择科室' };
      }

      const located = opts.lng != null && opts.lat != null;
      const ulng = located ? Number(opts.lng) : 116.397428;   // 天安门（与后端 DEFAULT_LNG/LAT 一致）
      const ulat = located ? Number(opts.lat) : 39.909230;
      const baseName = (opts.base_name || '').trim();

      const prefer = Object.prototype.hasOwnProperty.call(C.PLAN_PREFER, opts.prefer)
        ? opts.prefer : 'specialty';
      const wt = C.PLAN_PREFER[prefer];
      const topN = Math.max(1, Math.min(20, parseInt(opts.top_n, 10) || 6));
      const maxKm = parseFloat(opts.max_km) || 0;
      const publicOnly = !!opts.public_only;
      const levelFilter = (opts.level || '').trim();

      const mres = matchDepts(q, extra, forcedDept);
      const matched = mres.matched;
      const district = (opts.district || '').trim() || mres.district;
      if (!matched.size) {
        return {
          ok: false, reason: 'no_match',
          hint: '没能从描述里识别出科室，换个说法或补充更具体的症状试试',
          examples: ['头痛', '心慌', '骨折', '高血压', '儿童发烧', '孕检', '牙痛'],
        };
      }

      const deptList = Array.from(matched.keys());
      const emergency = deptList.some(function (d) { return matched.get(d).emg; });

      // 拉候选：走科室倒排索引，再按区域 / 等级 / 办别过滤（与后端 SQL 的 WHERE 等价）
      const byHosp = new Map();
      for (const d of deptList) {
        const di = deptIdxOf.get(d);
        if (di === undefined) continue;
        const rowIdxs = byDept.get(di) || [];
        for (const ri of rowIdxs) {
          const row = payload.strength[ri];
          const inst = instById.get(row[0]);
          if (!inst) continue;
          if (district && inst.district !== district) continue;
          if (levelFilter && inst.level !== levelFilter) continue;
          if (publicOnly && inst.ownership !== '公立') continue;
          let rec = byHosp.get(row[0]);
          if (!rec) { rec = { row: row, inst: inst, depts: [], dept: d }; byHosp.set(row[0], rec); }
          rec.depts.push(d);
          // 同院命中多科室：取「代表记录」（确定序，见 bestRowKey）
          if (cmpKey(bestRowKey(row, d), bestRowKey(rec.row, rec.dept)) < 0) { rec.row = row; rec.dept = d; }
        }
      }
      if (!byHosp.size) {
        return {
          ok: false, reason: 'no_candidate',
          hint: '条件下没有匹配到机构，试着放宽区域或等级限制',
          triage: { target_depts: deptList, district: district },
        };
      }

      // 同院多名称合并
      const merged = new Map();
      for (const rec of byHosp.values()) {
        const key = normHospName(rec.inst.name);
        const m = merged.get(key);
        if (!m) { rec.alias = []; merged.set(key, rec); continue; }
        m.depts = Array.from(new Set(m.depts.concat(rec.depts)));
        m.alias.push(rec.inst.name);
        if (cmpKey(bestRowKey(rec.row, rec.dept), bestRowKey(m.row, m.dept)) < 0) {
          const keepDepts = m.depts, keepAlias = m.alias;
          m.row = rec.row; m.inst = rec.inst; m.dept = rec.dept;
          m.depts = keepDepts; m.alias = keepAlias;
        }
      }
      const totalCandidates = merged.size;

      const maxW = Math.max.apply(null, deptList.map(function (d) { return matched.get(d).w; })) || 1.0;
      const candidates = [];
      for (const rec of merged.values()) {
        const row = rec.row, inst = rec.inst;
        const deptName = DEPTS[row[1]];
        let dist = null;
        const dlng = parseFloat(inst.lng), dlat = parseFloat(inst.lat);
        if (dlng && dlat) dist = planHaversine(ulng, ulat, dlng, dlat);
        if (maxKm && (dist === null || dist > maxKm)) continue;

        const strengthN = (row[3] || 0) / 100.0;
        const levelN = (C.LEVEL_SCORE[inst.level] !== undefined ? C.LEVEL_SCORE[inst.level] : 0.5) / 3.0;
        const netN = row[5] ? 1.0 : 0.0;
        const deptN = matched.get(deptName).w / maxW;

        let parts;
        if (located && dist !== null) {
          parts = {
            strength: wt.strength * strengthN,
            distance: wt.dist * (1.0 / (1.0 + dist / 5.0)),
            level: wt.level * levelN,
            network: wt.net * netN,
            dept: wt.dept * deptN,
          };
        } else {
          // 未设基准点：距离项无处可算，权重按比例并入实力与等级，保证总分可比
          const wd = wt.dist, baseW = wt.strength + wt.level;
          parts = {
            strength: (wt.strength + wd * wt.strength / baseW) * strengthN,
            distance: 0.0,
            level: (wt.level + wd * wt.level / baseW) * levelN,
            network: wt.net * netN,
            dept: wt.dept * deptN,
          };
        }
        const score = parts.strength + parts.distance + parts.level + parts.network + parts.dept;

        // ---- 推荐依据：与后端逐条同序 ----
        const tier = row[2];
        const reasons = [];
        if (tier === 4) reasons.push(deptName + '为国家临床重点专科');
        else if (tier === 3) reasons.push(deptName + '为市级重点专科');
        else if (tier === 2) reasons.push(deptName + '为官网公示重点科室');
        else if (tier === 1) reasons.push(deptName + '为登记重点专科');
        else reasons.push('已开设' + deptName);

        const nets = [];
        for (const k of Object.keys(C.PLAN_NET_LABEL)) {
          if (inst[k] && (C.PLAN_NET_DEPT[k] || []).indexOf(deptName) >= 0) nets.push(C.PLAN_NET_LABEL[k]);
        }
        if (nets.length) reasons.push('本市' + nets.join('、') + '协作网络成员');

        const conc = row[4] || 0;
        if (conc >= 0.4) {
          reasons.push(deptName + '方向专科机构（重点专科有 ' + Math.round(conc * 100) + '% 集中在本专科）');
        }
        if (inst.level) reasons.push('机构等级 ' + inst.level);
        if (dist !== null) reasons.push('距' + (baseName || '基准点') + ' ' + dist.toFixed(1) + ' 公里');

        candidates.push({
          id: row[0], name: inst.name, district: inst.district,
          addr: inst.addr, phone: inst.phone,
          lng: inst.lng, lat: inst.lat,
          level: inst.level, level_norm: inst.level,
          ownership: inst.ownership, ownership_src: inst.ownership_src,
          distance_km: dist !== null ? roundN(dist, 1) : null,
          dept_name: deptName, dept_category: deptCategoryOf(deptName),
          matched_depts: Array.from(new Set(rec.depts)).sort(),
          alias_count: (rec.alias || []).length,
          tier: tier, tier_label: TIER_LABEL[String(tier)] || TIER_LABEL[tier],
          strength: row[3],
          concentration: conc,
          is_network: !!row[5],
          dept_count: inst.dept_count,
          // ⚠️ 先舍入到 4 位再排序 —— 后端就是这么排的，这里必须同序，否则边界上会错位
          match_score: roundN(Math.min(1.0, score), 4),
          score_break: {
            strength: roundN(parts.strength, 3), distance: roundN(parts.distance, 3),
            level: roundN(parts.level, 3), network: roundN(parts.network, 3),
            dept: roundN(parts.dept, 3),
          },
          reasons: reasons,
        });
      }

      if (!candidates.length) {
        return {
          ok: false, reason: 'filtered_out',
          hint: '符合科室条件的机构都不满足距离或等级限制，试着放宽条件',
          triage: { target_depts: deptList, district: district },
          stats: { candidate_total: totalCandidates, returned: 0 },
        };
      }

      // 排序兜底链：评分 → 实力分 → 开设科室数 → 名称。
      // 少了后面两级，同分机构会退化成按机构名拼音排，出现「专科医院排在综合医院后面」的怪结果。
      candidates.sort(function (a, b) {
        if (a.match_score !== b.match_score) return b.match_score - a.match_score;
        if ((a.strength || 0) !== (b.strength || 0)) return (b.strength || 0) - (a.strength || 0);
        if ((a.dept_count || 0) !== (b.dept_count || 0)) return (b.dept_count || 0) - (a.dept_count || 0);
        return a.name < b.name ? -1 : (a.name > b.name ? 1 : 0);
      });

      return {
        ok: true,
        generated_at: (function () {
          const d = new Date(), p = function (n) { return String(n).padStart(2, '0'); };
          return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
            ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
        })(),
        input: {
          q: q, extra: extra, forced_dept: forcedDept,
          district: district, located: located, base_name: baseName,
          prefer: prefer, prefer_label: C.PLAN_PREFER_LABEL[prefer],
          weights: wt, max_km: maxKm, public_only: publicOnly,
          level: levelFilter, top_n: topN,
        },
        triage: {
          target_depts: deptList.slice().sort(function (a, b) { return matched.get(b).w - matched.get(a).w; })
            .map(function (d) {
              return {
                name: d, category: deptCategoryOf(d), weight: matched.get(d).w,
                matched_by: matched.get(d).kw, is_emergency: !!matched.get(d).emg,
              };
            }),
          emergency: emergency,
          corrected_district: mres.correction,
          engine: 'offline',
        },
        stats: { candidate_total: totalCandidates, returned: candidates.length },
        candidates: candidates.slice(0, topN),
      };
    }

    return {
      run: run,
      matchDepts: matchDepts,
      correctDistrict: correctDistrict,
      normDepts: normDepts,
      normHospName: normHospName,
      deptCategoryOf: deptCategoryOf,
      deptCount: DEPTS.length,
      rowCount: payload.strength.length,
    };
  }

  return { create: create, ratio: ratio, planHaversine: planHaversine };
})();

// Node 环境下导出，便于 etl/verify_offline_plan.py 做双端一致性比对
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { PlanEngine: PlanEngine };
}
