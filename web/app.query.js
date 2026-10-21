/* Shared predicates for the lookup list AND its counterfactual explanations. */
(function (root) {
  'use strict';
  var fields = [
    ['kw', '关键词', 'f_kw'], ['district', '行政区', 'f_district'],
    ['level', '等级', 'f_level'], ['category', '机构类型', 'f_cat'],
    ['dept', '科室', 'f_dept'], ['network', '协作网络', 'f_net'],
    ['level_sub', '等级等次', 'f_level_sub'], ['dept_evidence', '科室证据', 'f_evidence'],
    ['radius', '直线半径', 'f_radius']
  ];
  function validate(c) {
    if (c.radius !== '' && c.radius != null &&
        (!Number.isFinite(Number(c.radius)) || Number(c.radius) <= 0 || Number(c.radius) > 200)) {
      throw new Error('距离半径应大于 0 且不超过 200 km');
    }
  }
  function matches(row, c, base, nlq) {
    validate(c);
    var standard = {};
    ['district', 'level', 'category'].forEach(function (k) { if (c[k]) standard[k] = [c[k]]; });
    ['dept', 'dept_evidence'].forEach(function (k) { if (c[k]) standard[k] = c[k]; });
    if (c.radius !== '' && c.radius != null) standard.radius = Number(c.radius);
    if (c.dept_evidence === 'recorded' && !Object.prototype.hasOwnProperty.call(row, 'recorded_depts')) {
      throw new Error('快照缺少科室来源证据，请带数据库重新构建快照');
    }
    if (!nlq.matches(row, standard, base)) return false;
    if (c.kw && [row.name, row.addr, row.district].join(' ').toLowerCase().indexOf(c.kw.toLowerCase()) < 0) return false;
    if (c.level_sub && String(row.level_sub || '').charAt(0) !== c.level_sub.charAt(0)) return false;
    if (c.network === 'ped_core' && row.net_pediatric !== '核心') return false;
    if (c.network === 'ped_member' && row.net_pediatric !== '成员') return false;
    if (c.network === 'stroke' && String(row.net_stroke) !== '1') return false;
    if (c.network === 'neonatal' && row.net_neonatal !== '市级') return false;
    if (c.network === 'maternal' && row.net_maternal !== '市级') return false;
    return true;
  }
  function explain(rows, c, base, nlq, total) {
    validate(c);
    var active = fields.filter(function (f) { return c[f[0]] !== '' && c[f[0]] != null; });
    var count = function (cond) { return rows.reduce(function (n, r) { return n + Number(matches(r, cond, base, nlq)); }, 0); };
    var items = active.map(function (f) {
      var only = {}, without = Object.assign({}, c);
      only[f[0]] = c[f[0]]; delete without[f[0]];
      var keep = count(without);
      return { key: f[0], label: f[1], control: f[2], value: c[f[0]],
        alone_n: count(only), keep_n: keep, drop_n: keep - total };
    });
    return { total: total, items: items,
      suggestions: items.filter(function (x) { return x.keep_n > total; })
        .sort(function (a, b) { return a.drop_n - b.drop_n; }) };
  }
  var api = { fields: fields, matches: matches, validate: validate, explain: explain };
  root.QueryAudit = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
