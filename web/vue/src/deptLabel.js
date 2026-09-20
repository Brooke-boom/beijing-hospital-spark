// 科室数的展示口径（与单文件形态 web/app.js 里的 deptLabel 保持同一套判据）。
//
// dept_count 由三种**不可比**的口径拼成，表格里直接甩一个数字会误导：
//   ① 在线核实（dept_count_src）：机构官网 / 百科词条自述，最接近真实；
//   ② 登记诊疗科目（specialty / key_depts）：来自医疗机构登记的诊疗科目；
//   ③ 规则推导（rule_dept_count）：源数据未收录时，按「机构等级 × 类型」套的一份
//      通用清单（如三级医院 19 个），**不是**这家机构真实的科室构成。
//
// 另有一批头部医院在源数据里只登记到 1~5 个科室（宣武医院只登记了「神经内科」一条
// 国家级重点专科），把收录条数当科室数展示反而误导，统一显示为「待补全」。

export function deptKind(r) {
  const n = Number(r.dept_count || 0)
  if (!n) return 'none'
  if (String(r.dept_count_src || '')) return 'online'
  if (Number(r.rule_dept_count || 0) >= n) return 'rule'
  if ((r.level === '三级' || r.level === '二级') && n <= 5) return 'pending'
  return 'record'
}

export function deptText(r) {
  const n = Number(r.dept_count || 0)
  if (!n) return '—'
  return deptKind(r) === 'pending' ? '待补全' : String(n)
}

export function deptTip(r) {
  const n = Number(r.dept_count || 0)
  switch (deptKind(r)) {
    case 'none':
      return '源数据未收录该机构的科室信息'
    case 'online':
      return '在线核实：来自机构官网 / 百科词条的科室设置，共 ' + n + ' 个'
    case 'rule':
      return '源数据未收录该机构的科室设置，当前数量按「' + (r.level || '同类型') +
        '」通用科室清单推导，仅供筛选参考，不代表真实科室构成'
    case 'pending':
      return '源数据仅收录到 ' + n + ' 个科室，与该院实际规模不符，故不展示具体数字'
    default:
      return '来自医疗机构登记的诊疗科目，共 ' + n + ' 个'
  }
}

// 科室数字后面的口径后缀（表格里空间紧，用极短的词）
export function deptSuffix(r) {
  const k = deptKind(r)
  if (k === 'online') return '在线'
  if (k === 'rule') return '推导'
  return ''
}

// 详情抽屉里的完整口径说明
export function deptExplain(r) {
  const n = Number(r.dept_count || 0)
  switch (deptKind(r)) {
    case 'none':
      return '源数据未收录该机构的科室信息。'
    case 'online':
      return '在线核实口径：机构官网 / 百科词条自述的科室设置，共 ' + n + ' 个。'
    case 'rule':
      return '通用清单口径：源数据未收录该机构的科室设置，当前数量按「' +
        (r.level || '同类型') + '」的标准科室集推导，不代表该机构的真实科室构成。'
    case 'pending':
      return '收录不全：源数据仅登记到 ' + n + ' 个科室，与该院实际规模不符，故不展示具体数量。'
    default:
      return '登记口径：来自医疗机构登记的诊疗科目，共 ' + n + ' 个。'
  }
}
