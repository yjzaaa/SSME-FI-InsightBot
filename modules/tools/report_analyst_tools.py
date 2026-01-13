from autogen_core.tools import FunctionTool
from typing import Dict, Any, Optional
# 供应商评分工具函数
def calculate_sdq_score(consumption: int, defect_count: int, ncm_count: int) -> int:
    """计算供应商SDQ得分"""
    if consumption == 0:
        return 30 if ncm_count == 0 else 10
    
    sdq = (1 - defect_count / consumption) * 100
    if consumption < 200:
        if sdq >= 97: return 30
        return 20 if 90 < sdq < 97 else 10
    elif 200 <= consumption <= 500:
        if sdq >= 98: return 30
        return 20 if 95 < sdq < 98 else 10
    else:
        if sdq >= 99: return 30
        return 20 if 97 < sdq < 99 else 10

def calculate_downtime_score(actual: float, target: float) -> int:
    """计算停线时间得分"""
    ratio = actual / target
    if ratio < 0.5: return 25
    if ratio < 1: return 20
    if ratio < 2: return 10
    if ratio < 3: return 5
    return 0

def calculate_total_score(sdq: int, downtime: int, delivery: int = 25, quality: int = 20) -> int:
    """计算供应商总分（0-100分）
    参数：
    - sdq: SDQ质量得分（0-30）
    - downtime: 停线时间得分（0-25）
    - delivery: 交付及时率得分（默认25，0-25）
    - quality: 来料合格率得分（默认20，0-25）
    """
    # 验证输入分数范围
    if not (0 <= sdq <= 30):
        raise ValueError("SDQ得分需在0-30之间")
    if not (0 <= downtime <= 25):
        raise ValueError("停线时间得分需在0-25之间")
    if not (0 <= delivery <= 25):
        raise ValueError("交付得分需在0-25之间") 
    if not (0 <= quality <= 25):
        raise ValueError("质量得分需在0-25之间")
    
    total = sdq + downtime + delivery + quality
    return min(total, 100)  # 确保总分不超过100

def calculate_supplier_scores(consumption: int, defect_count: int, ncm_count: int, actual_downtime: float, target_downtime: float) -> Dict[str, Any]:
    """综合计算供应商各项得分与指标，返回结构化字典。

    参数:
        consumption: 物料消耗量 (件)
        defect_count: 出问题物料数量 (件)
        ncm_count: NCM记录数量 (条)
        actual_downtime: 实际停线时间 (小时)
        target_downtime: 目标停线时间 (小时，需>0)

    返回:
        {
          'sdq_rate': float,           # SDQ百分比值
          'sdq_score': int,            # SDQ得分(0-30)
          'downtime_ratio': float,     # 停线时间占比 actual/target
          'downtime_score': int,       # 停线时间得分(0-25)
          'total_score_55': int,       # 总分(满分55 = SDQ+Downtime)
          'inputs': {...},             # 原始输入回显
          'rules_applied': [str,...],  # 套用的规则说明
          'notes': [str,...]           # 额外说明
        }
    """
    notes = []
    if consumption < 0 or defect_count < 0 or ncm_count < 0:
        raise ValueError("输入数量不能为负数")
    if target_downtime <= 0:
        raise ValueError("目标停线时间必须>0")
    if actual_downtime < 0:
        raise ValueError("实际停线时间不能为负数")

    # SDQ率计算
    if consumption == 0:
        sdq_rate = 100.0 if ncm_count == 0 else 0.0
        notes.append("消耗量为0，使用特殊SDQ逻辑")
    else:
        sdq_rate = max(0.0, (1 - defect_count / consumption) * 100)

    sdq_score = calculate_sdq_score(consumption, defect_count, ncm_count)
    downtime_score = calculate_downtime_score(actual_downtime, target_downtime)

    downtime_ratio = actual_downtime / target_downtime if target_downtime else 0.0

    total_score_55 = sdq_score + downtime_score  # 按当前规则满分55分

    # 规则说明收集
    rules = []
    # SDQ规则匹配描述
    if consumption == 0:
        rules.append("消耗量=0 → NCM=0 得30分, 否则10分")
    elif consumption < 200:
        rules.append("消耗<200: SDQ≥97→30; 90~97→20; ≤90→10")
    elif consumption <= 500:
        rules.append("200-500: SDQ≥98→30; 95~98→20; ≤95→10")
    else:
        rules.append(">500: SDQ≥99→30; 97~99→20; ≤97→10")

    # 停线时间规则描述
    rules.append("停线时间得分: <0.5x→25; 0.5~1x→20; 1~2x→10; 2~3x→5; ≥3x→0")

    return {
        'sdq_rate': round(sdq_rate, 4),
        'sdq_score': sdq_score,
        'downtime_ratio': round(downtime_ratio, 4),
        'downtime_score': downtime_score,
        'total_score_55': total_score_55,
        'inputs': {
            'consumption': consumption,
            'defect_count': defect_count,
            'ncm_count': ncm_count,
            'actual_downtime': actual_downtime,
            'target_downtime': target_downtime
        },
        'rules_applied': rules,
        'notes': notes
    }

# 注册评分工具
sdq_tool = FunctionTool(
    calculate_sdq_score,
    description="""计算供应商SDQ质量得分(0-30分)，参数：
    - consumption: 物料消耗量(整数，单位：件)
    - defect_count: 质量问题数量(整数)
    - ncm_count: NCM不合格记录数(整数)
    评分规则：
    - 消耗量＜200件：SDQ≥97%得30分，90-97%得20分，＜90%得10分
    - 200-500件：SDQ≥98%得30分，95-98%得20分，＜95%得10分 
    - ＞500件：SDQ≥99%得30分，97-99%得20分，＜97%得10分
    示例：calculate_sdq_score(150, 3, 0) → 根据150件消耗量计算得分"""
)

downtime_tool = FunctionTool(
    calculate_downtime_score,
    description="""计算停线时间得分(0-25分)，参数：
    - actual: 实际停线时间(小时，浮点数)
    - target: 目标停线时间(小时，浮点数)
    评分规则：
    - 实际/目标＜0.5 → 25分
    - 0.5-1 → 20分
    - 1-2 → 10分
    - 2-3 → 5分
    - ≥3 → 0分
    示例：calculate_downtime_score(1.2, 1.0) → 实际是目标的1.2倍，得10分"""
)

total_score_tool = FunctionTool(
    calculate_total_score,
    description="""计算供应商总分（0-100分），参数：
    - sdq: SDQ质量得分（0-30）
    - downtime: 停线时间得分（0-25）
    - delivery: 交付及时率得分（可选，默认25，0-25）
    - quality: 来料合格率得分（可选，默认20，0-25）
    计算规则：总分 = SDQ + 停线 + 交付 + 质量，最高100分
    示例：calculate_total_score(25, 20, 22, 18) → 85分"""
)

def _score_and_format(
    consumption: int,
    defect_count: int,
    ncm_count: int,
    actual_downtime: float,
    target_downtime: float,
    supplier_name: str,
    supplier_code: Optional[str] = "",
    report_title: Optional[str] = "供应商打分"
) -> str:
    """合并评分与格式化，一次返回最终报告(含SCORING_DONE)。"""
    try:
        scoring = calculate_supplier_scores(
            consumption=consumption,
            defect_count=defect_count,
            ncm_count=ncm_count,
            actual_downtime=actual_downtime,
            target_downtime=target_downtime,
        )
    except Exception as e:
        return f"输入数据不合法：{e}。请更正后重试。SCORING_DONE"
    return format_supplier_score(report_title, supplier_name, supplier_code or "", scoring)

supplier_scoring_tool = FunctionTool(
    _score_and_format,
    description="一站式评分报告: 输入消费/缺陷/NCM/实际停线/目标停线/名称(+代码,标题可选)。返回已格式化文本+SCORING_DONE。"
)

def format_supplier_score(report_title: str, supplier_name: str, supplier_code: str, scoring: Dict[str, Any]) -> str:
    """根据 scoring 结果字典生成标准报告文本。

    scoring 字典需来自 calculate_supplier_scores。
    输出包含：核心指标、评分结果、规则说明、计算过程、末尾 SCORING_DONE。
    防止原始 dict 直接输出，确保结构化可读性。
    """
    required_keys = [
        'sdq_rate','sdq_score','downtime_ratio','downtime_score','total_score_55','inputs','rules_applied'
    ]
    missing = [k for k in required_keys if k not in scoring]
    if missing:
        return f"格式化失败：缺少关键字段 {missing}，请先调用supplier_scoring_tool获取完整数据。SCORING_DONE"

    inp = scoring['inputs']
    lines = []
    lines.append(f"供应商打分报告 - {report_title}")
    lines.append("")
    lines.append("**供应商信息：**")
    lines.append(f"- 供应商代码：{supplier_code}")
    lines.append(f"- 供应商名称：{supplier_name}")
    lines.append("")
    lines.append("**核心指标：**")
    lines.append(f"- 物料消耗数量：{inp['consumption']} 件")
    lines.append(f"- 出问题物料数量：{inp['defect_count']} 件")
    lines.append(f"- NCM记录数量：{inp['ncm_count']} 条")
    lines.append(f"- 实际停线时间：{inp['actual_downtime']} 小时")
    lines.append(f"- 目标停线时间：{inp['target_downtime']} 小时")
    lines.append("")
    lines.append("**评分结果：**")
    lines.append(f"- SDQ值：{scoring['sdq_rate']:.2f}%")
    lines.append(f"- SDQ得分：{scoring['sdq_score']}分 (满分30分)")
    lines.append(f"- 停线时间占比：{scoring['downtime_ratio']:.2f}x 目标")
    lines.append(f"- 停线时间得分：{scoring['downtime_score']}分 (满分25分)")
    lines.append(f"- **总分：{scoring['total_score_55']}分 (满分55分)**")
    lines.append("")
    # 计算过程与规则
    lines.append("**规则说明：**")
    for r in scoring['rules_applied']:
        lines.append(f"- {r}")
    if scoring.get('notes'):
        lines.append("")
        lines.append("**特殊说明：**")
        for n in scoring['notes']:
            lines.append(f"- {n}")
    lines.append("")
    lines.append("**计算过程摘要：**")
    if inp['consumption'] == 0:
        lines.append("- 消耗量为0，直接应用特殊SDQ逻辑：无NCM=30分，否则10分。")
    else:
        lines.append(f"- SDQ = (1 - 缺陷物料数量/消耗数量) × 100% = (1 - {inp['defect_count']}/{inp['consumption']}) × 100% = {scoring['sdq_rate']:.2f}%")
        lines.append(f"- 停线时间占比 = 实际/目标 = {inp['actual_downtime']}/{inp['target_downtime']} = {scoring['downtime_ratio']:.2f}x")
    lines.append("- 总分 = SDQ得分 + 停线时间得分 = "
                 f"{scoring['sdq_score']} + {scoring['downtime_score']} = {scoring['total_score_55']}")
    lines.append("")
    lines.append("SCORING_DONE")
    return "\n".join(lines)

## 已合并：原 supplier_score_format_tool 与 supplier_score_report_tool 功能并入 supplier_scoring_tool
