from typing import List, Dict, Any
from autogen_core.tools import FunctionTool
import math

from typing import List, Dict, Any, Optional
from autogen_core.tools import FunctionTool
import json

REQUIRED_FIELDS = {
    "pie": ["labels", "values"],  # 占位，仅用于存在性快速判断；实际逻辑在后续单独处理
    "bar": ["labels", "values"],
    "line": ["labels", "values"],
    "stacked_bar": ["labels", "series"],
    "grouped_bar": ["labels", "series"],
    "bar_line": ["labels", "bar_data", "line_data", "bar_name", "line_name"],
    "histogram": ["values", "bins"],
}

def _err(msg: str, chart_type: str) -> Dict[str, Any]:
    return {"error": msg, "chart_type": chart_type}

def build_chart(
    chart_type: str,
    title: str,
    labels: Optional[List[str]] = None,
    values: Optional[List[float]] = None,
    series: Optional[List[Dict[str, Any]]] = None,
    bar_data: Optional[List[float]] = None,
    line_data: Optional[List[float]] = None,
    bar_name: Optional[str] = None,
    line_name: Optional[str] = None,
    bins: Optional[int] = None,
) -> str | Dict[str, Any]:
    """构建规范格式的图表片段，返回包含 [CHART_START] 和 [CHART_END] 的 JSON 字符串。字段规则与 prompt 中示例完全一致。错误返回 dict。"""
    chart_type = chart_type.strip()
    if chart_type not in REQUIRED_FIELDS:
        return _err(f"不支持的图表类型: {chart_type}", chart_type)

    # 具体类型验证与健壮性增强
    if chart_type in ("bar", "line", "pie"):
        if not labels or not values:
            return _err("缺少labels或values", chart_type)
        if len(labels) != len(values):
            return _err("labels与values长度不一致", chart_type)
    elif chart_type in ("stacked_bar", "grouped_bar"):
        if not isinstance(series, list) or any("name" not in s or "values" not in s for s in series):
            return _err("series需为包含name与values的对象列表", chart_type)
        for s in series:
            if len(s["values"]) != len(labels):
                return _err(f"系列 {s.get('name')} 的values长度与labels不一致", chart_type)
    elif chart_type == "bar_line":
        if len(labels) != len(bar_data) or len(labels) != len(line_data):
            return _err("bar_line的labels, bar_data, line_data长度必须一致", chart_type)
    elif chart_type == "histogram":
        if not isinstance(bins, int) or bins <= 0:
            return _err("histogram的bins必须为正整数", chart_type)
        if not all(isinstance(v, (int, float)) for v in values):
            return _err("histogram的values必须为数值列表", chart_type)

    # 组装结构
    if chart_type == "bar" or chart_type == "line" or chart_type == "pie":
        structure = {"type": chart_type, "title": title, "labels": labels, "values": values}
    elif chart_type in ("stacked_bar", "grouped_bar"):
        structure = {"type": chart_type, "title": title, "labels": labels, "series": series}
    elif chart_type == "bar_line":
        structure = {"type": "bar_line", "title": title, "labels": labels, "bar_data": bar_data, "line_data": line_data, "bar_name": bar_name, "line_name": line_name}
    elif chart_type == "histogram":
        structure = {"type": "histogram", "title": title, "values": values, "bins": bins}
    else:
        return _err("未知图表类型", chart_type)

    json_str = json.dumps(structure, ensure_ascii=False, indent=2)
    return f"[CHART_START]\n{json_str}\n[CHART_END]"


def build_chart_from_type(
    type: str,
    title: str,
    labels: Optional[List[str]] = None,
    values: Optional[List[float]] = None,
    series: Optional[List[Dict[str, Any]]] = None,
    bar_data: Optional[List[float]] = None,
    line_data: Optional[List[float]] = None,
    bar_name: Optional[str] = None,
    line_name: Optional[str] = None,
    bins: Optional[int] = None,
) -> str | Dict[str, Any]:
    """与构建参数保持一致，但使用 'type' 作为入参名称以匹配调用方习惯。"""
    return build_chart(
        chart_type=type,
        title=title,
        labels=labels,
        values=values,
        series=series,
        bar_data=bar_data,
        line_data=line_data,
        bar_name=bar_name,
        line_name=line_name,
        bins=bins,
    )

# 将工具改为接受 'type' 参数，避免使用者误传 'chart_type'
chart_tool = FunctionTool(
    build_chart_from_type,
    description="生成规范图表片段。使用参数: type(图表类型), title, 以及对应所需字段。支持: pie, bar, line, stacked_bar, grouped_bar, bar_line, histogram。返回带[CHART_START]/[CHART_END]包装的JSON字符串。错误时返回包含error的dict。务必始终返回一个包装JSON。"
)

__all__ = [
    "chart_tool",
    "build_chart",
    "build_chart_from_type",
]

