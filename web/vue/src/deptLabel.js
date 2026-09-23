// 科室数的展示口径（与单文件形态 web/app.js 的 deptLabel / deptText 保持同一套判据）
//
// dept_count 字面是 hospital_depts.csv 中该机构的行数，但该表绝大多数行是推导出来的：
//   source='rule'      9,855 行 —— 按「机构等级 × 类型」套的通用清单
//   source='name'      3,800 行 —— 按机构名推导（「中医医院」→ 中医内科、针灸推拿科）
//   source='online'    2,620 行 —— 好大夫在线逐家核实的真实科室（2026-09-22 新增）
//   source='key_depts'   459 行 + 'specialty' 159 行 —— 源数据登记的真实科室
//
// 结论一：**唯一可对外的数字只有在线的核实值**（dept_count_src 非空，实测 301 家）。
// 推导出的科室名仍参与科室维度检索与排序，但不作为事实展示。
//
// 结论二（2026-09-22 修订）：**「科室资料待补全」这句话本身用错了一大片。**
// 9,684 家里有 8,279 家（85.5%）是诊所 / 村卫生室 / 门诊部 / 社区卫生服务站 /
// 医务室 / 护理站 —— 这些类型的机构按各自的《基本标准》**以「诊疗科目」核准执业，
// 不做科室建制**。对它们显示"资料待补全"是把"不适用"说成"我们没查到"，
// 一次误报 8,279 家，把真正缺数据的约 1,200 家淹没了。
// → 这类机构改为如实说明「不设科室分科」。
//
// 判据用 category_fine（主表细粒度类型：医务室 / 护理站 不在 10 类粗口径里），
// 回落 category（category_norm 的 10 类）。

export const DEPT_PENDING = '科室资料待补全'
export const DEPT_NOT_APPLICABLE = '不设科室分科'

export const NO_DEPT_CAT = {
  '诊所': '按《诊所基本标准》以诊疗科目核准执业，不设科室分科',
  '村卫生室': '按《村卫生室管理办法》提供基本医疗与公共卫生服务，不设科室分科',
  '门诊部': '按《门诊部基本标准》以诊疗科目设置，不设临床科室建制',
  '社区卫生服务站': '按《城市社区卫生服务站基本标准》设置全科诊室等，不设科室分科',
  '医务室': '单位内部医疗机构，按诊疗科目核准执业，不设科室分科',
  '护理站': '按《护理站基本标准》提供居家护理服务，不设科室分科',
}

function catFine(r) {
  return r.category_fine || r.category || ''
}

// 'online' 有在线核实值 ｜ 'nodept' 该类型本就不设科室 ｜ 'pending' 应当收录但未取得
//
// 判定**类型优先**：基层六类先落 'nodept'，再谈有没有在线核实值。
// 好大夫在线的目录里也有 21 家诊所 / 门诊部 / 社区卫生服务站（多为院内门诊部），
// 它们页面上的"科室"其实是《基本标准》意义上的**诊疗科目**。若按"有核实值就显数字"，
// 同一家机构会在列表里写"N 个科室"、在类型说明里写"不设科室建制"，自相矛盾。
// 机构类型是事实属性，优先于某一家网站某一页的栏目数量。
export function deptKind(r) {
  if (NO_DEPT_CAT[catFine(r)]) return 'nodept'
  return String(r.dept_count_src || '') ? 'online' : 'pending'
}

export function deptText(r) {
  const k = deptKind(r)
  if (k === 'online') return String(Number(r.dept_count || 0))
  return k === 'nodept' ? DEPT_NOT_APPLICABLE : DEPT_PENDING
}

export function deptTip(r) {
  const k = deptKind(r)
  if (k === 'online') {
    return '在线核实：来自机构官网 / 百科词条 / 好大夫在线的科室设置，共 ' +
      Number(r.dept_count || 0) + ' 个'
  }
  if (k === 'nodept') {
    return NO_DEPT_CAT[catFine(r)] + '。这不是资料缺失 —— 该类机构本就没有科室建制，' +
      '执业范围以「诊疗科目」形式登记。'
  }
  return '该机构应当收录科室设置，但源数据与在线核实均未取得。' +
    '检索用的科室清单系按机构等级与名称推导，仅用于科室维度筛选，不代表真实科室构成。'
}

// 数字后面的口径后缀：留下「在线」二字，读者才明白为什么只有少数行有数字
export function deptSuffix(r) {
  return deptKind(r) === 'online' ? '在线' : ''
}

// 详情抽屉里的完整口径说明
export function deptExplain(r) {
  const k = deptKind(r)
  if (k === 'online') {
    return '在线核实口径：机构官网 / 百科词条 / 好大夫在线自述的科室设置，共 ' +
      Number(r.dept_count || 0) + ' 个。'
  }
  if (k === 'nodept') return NO_DEPT_CAT[catFine(r)] + '，因此没有"科室设置"这项资料。'
  return '该机构应当收录科室设置，但源数据与在线核实均未取得。筛选用的科室清单系按机构等级与名称推导，' +
    '仅用于科室维度检索，不代表该院真实科室构成。'
}

// 科室明细列表的来源标注（'online' | 'nodept' | 'derived'），供详情抽屉决定用哪种措辞
export function deptListKind(r) {
  const k = deptKind(r)
  return k === 'online' ? 'online' : k
}
