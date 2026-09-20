// 科室数的展示口径（与单文件形态 web/app.js 的 deptLabel / deptText 保持同一套判据）
//
// dept_count 字面是 hospital_depts.csv 中该机构的行数，但该表 97% 的行是推导出来的：
//   source='rule'      11,840 行 —— 按「机构等级 × 类型」套的通用清单（三级 19 / 二级 13 / 一级 6、7）
//   source='name'       3,900 行 —— 按机构名推导（「中医医院」→ 中医内科、针灸推拿科）
//   source='key_depts'    488 行 + source='specialty' 23 行 —— 源数据登记的真实科室，仅占 3%
//
// 实测：9,755 家没有在线核实值，其中 1,805 家会重复显示同一个模板数字
// （2→1,107 / 7→295 / 6→226 / 19→91 / 13→86）；另有 468 家只登记到 1 条，
// 含东直门医院、东方医院等三甲中医医院——显示「1 个科室」比 59 更荒谬。
//
// 结论：**唯一可对外的数字只有在线的核实值**（dept_count_src 非空，实测 34 家），
// 其余一律「科室资料待补全」。推导出的科室名仍参与科室维度检索与排序，但不作为事实展示。

export const DEPT_PENDING = '科室资料待补全'

export function deptKind(r) {
  return String(r.dept_count_src || '') ? 'online' : 'pending'
}

export function deptText(r) {
  return deptKind(r) === 'online' ? String(Number(r.dept_count || 0)) : DEPT_PENDING
}

export function deptTip(r) {
  if (deptKind(r) === 'online') {
    return '在线核实：来自机构官网 / 百科词条的科室设置，共 ' + Number(r.dept_count || 0) + ' 个'
  }
  return '源数据未收录该机构的科室设置。检索用的科室清单系按机构等级与名称推导，' +
    '仅用于科室维度筛选，不代表真实科室构成。'
}

// 数字后面的口径后缀：留下「在线」二字，读者才明白为什么只有少数行有数字
export function deptSuffix(r) {
  return deptKind(r) === 'online' ? '在线' : ''
}

// 详情抽屉里的完整口径说明
export function deptExplain(r) {
  if (deptKind(r) === 'online') {
    return '在线核实口径：机构官网 / 百科词条自述的科室设置，共 ' + Number(r.dept_count || 0) + ' 个。'
  }
  return '源数据未收录该机构的科室设置。筛选用的科室清单系按机构等级与名称推导，' +
    '仅用于科室维度检索，不代表该院真实科室构成。'
}

// 科室明细列表的来源标注（'online' | 'derived'），供详情抽屉决定用哪种措辞
export function deptListKind(r) {
  return deptKind(r) === 'online' ? 'online' : 'derived'
}
