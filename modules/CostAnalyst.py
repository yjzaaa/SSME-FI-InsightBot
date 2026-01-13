import os
import asyncio
import sqlparse
import re
from typing import List, Any, Type, Annotated
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_ext.models.openai import (
    AzureOpenAIChatCompletionClient,
    OpenAIChatCompletionClient,
)
from autogen_core.tools import FunctionTool
from autogen_core.models import ModelFamily
from sqlalchemy import create_engine, text
from sqlparse.sql import IdentifierList, Identifier, Function
from sqlparse.tokens import Keyword, DML
from pandasql import sqldf
import pandas as pd
import sys
import logging
from datetime import datetime
from autogen_agentchat import EVENT_LOGGER_NAME, TRACE_LOGGER_NAME
from dotenv import load_dotenv
import os
from modules.tools.chart_tools import chart_tool

load_dotenv()
logging.basicConfig(level=logging.DEBUG)

trace_logger = logging.getLogger(TRACE_LOGGER_NAME)
trace_logger.addHandler(logging.StreamHandler())
trace_logger.setLevel(logging.DEBUG)

event_logger = logging.getLogger(EVENT_LOGGER_NAME)
event_logger.addHandler(logging.StreamHandler())
event_logger.setLevel(logging.DEBUG)

today = datetime.now().strftime("%Y%m%d")
log_filename = f"log/sop_flow_{today}.log"

file_handler_trace = logging.FileHandler(log_filename, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
file_handler_trace.setFormatter(formatter)
trace_logger.addHandler(file_handler_trace)

file_handler_event = logging.FileHandler(log_filename, encoding="utf-8")
file_handler_event.setFormatter(formatter)
event_logger.addHandler(file_handler_event)

sop_logger = logging.getLogger(f"{TRACE_LOGGER_NAME}.Cost_sop_team")
sop_logger.setLevel(logging.INFO)

# 使用 OpenAIChatCompletionClient，以类 LangChain 的连接方式（兼容第三方供应商）
sf_model = os.getenv("SILICONFLOW_MODEL")
sf_api_key = os.getenv("SILICONFLOW_API_KEY")
sf_base_url = os.getenv("SILICONFLOW_BASE_URL")

# 规范化与校验 SiliconFlow 基础配置，避免 401（末尾确保 /v1；去除空格与末尾斜杠）
if sf_base_url:
    sf_base_url = sf_base_url.strip()
    if sf_base_url.endswith("/"):
        sf_base_url = sf_base_url[:-1]
    if not sf_base_url.endswith("/v1"):
        sf_base_url = sf_base_url + "/v1"

if not sf_api_key or not sf_base_url or not sf_model:
    raise RuntimeError(
        "SiliconFlow 配置缺失：请在 .env 中设置 SILICONFLOW_API_KEY、SILICONFLOW_BASE_URL (建议 https://api.siliconflow.cn/v1) 和 SILICONFLOW_MODEL"
    )

# 输出安全的启动日志（不泄露密钥）
logging.info(
    f"[SiliconFlow] model={sf_model}, base_url={sf_base_url}, api_key_set={bool(sf_api_key)}"
)

temperature = float(os.getenv("TEMPERATURE", "0"))
max_tokens = int(os.getenv("MAX_TOKENS", "4096"))
timeout = int(os.getenv("TIMEOUT", "60"))

model_client = OpenAIChatCompletionClient(
    model=sf_model,
    api_key=sf_api_key,
    base_url=sf_base_url,
    temperature=temperature,
    max_tokens=max_tokens,
    timeout=timeout,
    # 对非官方 OpenAI 模型提供基本的 model_info 以通过能力校验
    model_info={
        "vision": False,
        "function_calling": True,
        "json_output": True,
        "family": ModelFamily.UNKNOWN,
        "structured_output": False,
        "multiple_system_messages": True,
    },
)


# ------------------------------------Data Query Tools------------------------------------#
def read_excel(file_path: str, sheet_name: str) -> pd.DataFrame:
    try:
        return pd.read_excel(file_path, sheet_name=sheet_name)
    except Exception as e:
        raise ValueError(f"读取Excel文件失败: {str(e)}")


def extract_table_name(query: str) -> list:
    """
    辅助函数：提取SQL查询中的所有表名（简化实现，适配常规SELECT查询）
    注：如需更精准的表名提取，可引入SQL解析库（如sqlparse）
    """
    query_upper = query.strip().upper()
    # 移除SELECT ... FROM 前缀，提取表名相关部分
    from_index = query_upper.find("FROM")
    if from_index == -1:
        return []
    from_content = query_upper[from_index + 4 :]

    # 移除WHERE/GROUP BY/ORDER BY等后续子句
    for keyword in ["WHERE", "GROUP BY", "ORDER BY", "JOIN", "LEFT JOIN", "RIGHT JOIN"]:
        kw_index = from_content.find(keyword)
        if kw_index != -1:
            from_content = from_content[:kw_index]

    # 提取表名（去重、去除空值和多余空格）
    table_names = [tbl.strip() for tbl in from_content.split(",") if tbl.strip()]
    return list(dict.fromkeys(table_names))  # 去重并保留原有顺序


def sqlQuery(file_path: str, query: str, sql_table_names: list) -> str:
    """
    执行SQL多表联合查询并返回结果（动态识别表名，支持多工作表映射，取消sheet_name参数）
    args:
    file_path (str): Excel文件路径（包含所有待查询工作表，工作表名需与SQL中的表名一致）
    query (str): SQL查询语句（支持多表联合查询，表名需与Excel工作表名一一对应）
    sql_table_names (list): SQL查询中涉及的所有表名列表
    returns: str: 查询结果或错误信息
    """
    try:
        # 1. 危险操作校验：禁止破坏性SQL操作
        query_upper = query.strip().upper()
        dangerous_patterns = [
            "DROP",
            "DELETE",
            "INSERT",
            "UPDATE",
            "ALTER",
            "EXEC",
            "TRUNCATE",
            "MERGE",
            "REPLACE",
        ]
        for pattern in dangerous_patterns:
            if pattern in query_upper:
                return f"错误：查询中包含不允许的操作: {pattern}"

        # 2. 提取SQL中的所有表名（支持多表）
        # sql_table_names = extract_table_name(query)
        # if not sql_table_names:
        #     return "错误：未从SQL查询中提取到有效表名"
        # logging.debug(f"从SQL中提取到的表名列表: {sql_table_names}")

        # 3. 读取Excel中所有对应工作表，构建表名->DataFrame映射
        query_env = {}
        for table_name in sql_table_names:
            try:
                # 关键：工作表名 = SQL中的表名，直接读取对应工作表
                df = pd.read_excel(file_path, sheet_name=table_name)
                query_env[table_name] = df
                logging.debug(
                    f"成功加载工作表 {table_name} 为DataFrame，数据行数：{len(df)}"
                )
            except Exception as sheet_e:
                return (
                    f"错误：无法读取Excel中的工作表 {table_name}，详情：{str(sheet_e)}"
                )

        # 4. 执行多表SQL查询（传入包含所有数据表的自定义环境）
        result_df = sqldf(query, query_env)

        # 5. 结果格式化返回
        if result_df.empty:
            return "查询成功，但结果为空"
        else:
            return f"查询成功，返回 {len(result_df)} 行数据:\n" + result_df.to_string()

    except Exception as e:
        error_msg = f"查询过程中出现错误: {str(e)}"
        logging.error(f"调试信息：{error_msg}")
        return error_msg


validate_field_range_list = [
    {
        "field_name": "cc",
        "target_sheet": "CC Mapping",
        "target_field": "CostCenterNumber",
    },
    {
        "field_name": "key",
        "target_sheet": "CostDataBase",
        "target_field": "Key",
    },
    {
        "field_name": "func",
        "target_sheet": "CostDataBase",
        "target_field": "Function",
    },
]


def validate_field_range(
    field_value: str, target_sheet: str, target_field: str
) -> bool:
    """校验字段值是否在指定范围内"""
    try:
        df = pd.read_excel(
            "Data/Function cost allocation analysis to IT 20260104.xlsx",
            sheet_name=target_sheet,
        )
        range_list = df[target_field].dropna().astype(str).tolist()
        return str(field_value) in range_list
    except Exception as e:
        logging.error(f"校验字段范围时出错: {str(e)}")
        return False


def generate_cost_rate_sql(
    year: Annotated[str, "年份条件（如 'FY25'、'FY26'）"],
    scenario: Annotated[str, "场景条件（如 'Actual'、'Budget1'）"],
    cost_db_table: Annotated[str, "主表名，默认 'CostDataBase'"] = "CostDataBase",
    table7: Annotated[str, "关联表名，默认 'Table7'"] = "Table7",
    func: Annotated[str, "Function筛选条件，默认 ''"] = "",
    key: Annotated[str, "Key筛选条件，默认 ''"] = "",
    cc: Annotated[str, "CC筛选条件，默认 ''"] = "",
    bl: Annotated[str, "BL筛选条件，默认 ''"] = "",
) -> str:
    """
    动态生成成本费率查询SQL语句，提取核心可变参数，支持默认值简化调用
    cc字段必须是CC Mapping表中的成本中心编码/名称 如果不是则需要先查询CC Mapping表获取对应的编码/名称再传入该函数
    key字段必须是CostDataBase表中的Key值 如果不是则需要先查询CostDataBase表获取对应的Key值再传入该函数
    不得忽略传的空值参数
    Args:
        year (str): 年份条件（如 'FY25'、'FY26'）
        scenario (str): 场景条件（如 'Actual'、'Budget1'）
        cost_db_table (str, optional): 主表名，默认 "CostDataBase"
        table7 (str, optional): 关联表名，默认 "Table7"
        func (str, optional): Function筛选条件，默认 ""
        key (str, optional): Key筛选条件，默认 ""
        cc (str, optional): CC筛选条件，默认 ""
        bl (str, optional): BL筛选条件，默认 ""
    Returns:
        str: 生成的完整SQL查询字符串（直接可执行，无参数元组）
    """
    # 1. 构建待校验字段清单（字段名: 字段值），统一处理
    field_validate_map = [("cc", cc), ("key", key), ("func", func)]

    # 2. 循环遍历执行校验，消除重复代码
    for field_name, field_value in field_validate_map:
        if not field_value:
            continue  # 跳过空值，无需校验
        # 查找对应配置
        field_config = [
            item
            for item in validate_field_range_list
            if item["field_name"] == field_name
        ]
        if not field_config:
            return f"错误：未找到{field_name}字段的校验配置"
        # 提取配置参数
        target_sheet = field_config[0]["target_sheet"]
        target_field = field_config[0]["target_field"]
        # 执行校验并返回错误
        if not validate_field_range(field_value, target_sheet, target_field):
            return f"错误：{field_name}字段值 '{field_value}' 不在允许范围内，请重新解析用户输入生成新的sql语句后再调用本函数"

    # 3. 关键修复：安全嵌入参数，避免语法错误（解决no such column问题）
    # 步骤1：对字符串参数进行单引号转义（防止参数内的单引号闭合SQL字符串）
    def escape_single_quote(s: str) -> str:
        return str(s).replace("'", "''")  # SQLite3中用两个单引号转义一个单引号

    # 转义所有需要嵌入SQL的字符串参数
    escaped_year = escape_single_quote(year)
    escaped_scenario = escape_single_quote(scenario)
    escaped_func = escape_single_quote(func)
    escaped_key = escape_single_quote(key)
    escaped_cc = escape_single_quote(cc)
    escaped_cost_db_table = escape_single_quote(cost_db_table)
    escaped_table7 = escape_single_quote(table7)
    escaped_bl = escape_single_quote(bl)
    # 3. 核心修改：动态构建WHERE子句（仅拼接非空字段的条件）
    # 步骤3.1：初始化条件列表（存储合法的查询条件）
    where_conditions = []

    # 步骤3.2：逐个判断字段值是否存在，存在则添加对应条件
    # 规则：字段值非空（非None、非空字符串）才拼接
    if escaped_year:
        where_conditions.append(f"cdb.\"Year\" = '{escaped_year}'")
    if escaped_scenario:
        where_conditions.append(f"cdb.\"Scenario\" = '{escaped_scenario}'")
    if escaped_func:
        where_conditions.append(f"cdb.\"Function\" = '{escaped_func}'")
    if escaped_key:
        where_conditions.append(f"cdb.\"Key\" = '{escaped_key}'")
    if escaped_cc:
        where_conditions.append(f"t7.\"cc\" = '{escaped_cc}'")
    if escaped_bl:
        where_conditions.append(f"t7.\"bl\" = '{escaped_bl}'")

    # 步骤3.3：拼接WHERE子句（无合法条件时，不添加WHERE关键字）
    where_clause = ""
    if where_conditions:
        # 用" AND "连接所有条件，组成完整WHERE子句
        where_clause = "WHERE " + " AND ".join(where_conditions)

    # 4. 拼接完整SQL语句（嵌入动态生成的WHERE子句）
    sql = f"""
    SELECT
        cdb.`Month`,
        SUM(COALESCE(t7.`RateNo`, 0)) AS `rate`,
        cdb.`Amount` AS `amount`
    FROM
        {escaped_cost_db_table} cdb  
    LEFT JOIN
        {escaped_table7} t7  
    ON
        cdb.`Month` = t7.`Month`
        AND cdb.`Year` = t7.`Year`
        AND cdb.`Scenario` = t7.`Scenario`
        AND cdb.`Key` = t7.`Key`
    {where_clause}
    GROUP BY
        cdb.`Month`,
        cdb.`Amount`
    ORDER BY
        cdb.`Month`;
    """

    # 4. 返回格式化后的完整SQL字符串（去除多余空白，直接可执行）
    return sql.strip()


def calculate_monthly_cost_table(df: Any) -> Any:
    """
    批量计算整张数据表的每月费用（入参和返回值均为Any，内部完成类型转换与校验）
    Args:
        df (Any): 输入数据（支持DataFrame、字典、Excel/CSV文件路径）
    Returns:
        Any: 计算结果（成功返回带monthly_cost列的DataFrame，失败返回对应错误信息/空DataFrame）
    """
    # 第一步：内部类型转换与校验，将任意输入转为合法的pandas DataFrame
    try:
        # 分支1：输入已是DataFrame，直接使用（先复制避免修改原数据）
        if isinstance(df, pd.DataFrame):
            df_input = df.copy()
            logging.info("输入数据为DataFrame类型，直接复制使用")

        # 分支2：输入是字典（符合DataFrame构造格式），转为DataFrame
        elif isinstance(df, dict):
            df_input = pd.DataFrame(df)
            logging.info("输入数据为字典类型，已转换为DataFrame")

        # 分支3：输入是字符串（判断为文件路径，支持Excel/CSV）
        elif isinstance(df, str):
            if df.endswith((".xlsx", ".xls")):
                df_input = pd.read_excel(df)
                logging.info(f"输入数据为Excel文件路径，已读取：{df}")
            elif df.endswith(".csv"):
                df_input = pd.read_csv(df, encoding="utf-8")
                logging.info(f"输入数据为CSV文件路径，已读取：{df}")
            else:
                raise ValueError("字符串输入非支持的文件格式（仅支持.xlsx/.xls/.csv）")

        # 分支4：不支持的输入类型，抛出异常
        else:
            raise TypeError(
                f"不支持的输入类型：{type(df).__name__}，支持类型：pd.DataFrame、dict、Excel/CSV文件路径字符串"
            )

    except Exception as e:
        error_msg = f"类型转换失败：{str(e)}"
        logging.error(error_msg)
        # 返回统一格式的空DataFrame，保证后续处理兼容性
        return pd.DataFrame(columns=["month", "amount", "rate", "monthly_cost"])
    df_input.columns = [col.lower() for col in df_input.columns]

    # 第二步：校验DataFrame是否包含必要列
    required_columns = ["month", "amount", "rate"]
    if not all(col in df_input.columns for col in required_columns):
        missing_cols = [col for col in required_columns if col not in df_input.columns]
        error_msg = f"输入数据缺少必要列：{', '.join(missing_cols)}，必须包含 {', '.join(required_columns)}"
        logging.error(error_msg)
        # 补充缺失列并设为NaN，返回完整结构的DataFrame
        for col in missing_cols:
            df_input[col] = pd.NA
        df_input["monthly_cost"] = pd.NA
        return df_input

    # 第三步：批量计算每月费用（包含数值类型转换，保证计算准确性）
    sop_logger.info(f"开始批量计算每月费用{df_input}")
    try:
        # 转换金额和分摊比例为数值类型，非数值数据自动转为NaN
        df_input["amount"] = pd.to_numeric(df_input["amount"], errors="coerce")
        df_input["rate"] = pd.to_numeric(df_input["rate"], errors="coerce")

        # 计算每月费用，保留2位小数（与原函数逻辑一致）
        df_input["monthly_cost"] = (df_input["amount"] * df_input["rate"]).round(2)

        logging.info("整张表每月费用计算完成")
        return df_input

    except Exception as e:
        error_msg = f"批量计算每月费用时出错：{str(e)}"
        logging.error(error_msg)
        # 异常时返回包含原始数据且monthly_cost列为NaN的DataFrame，保证格式统一
        df_input["monthly_cost"] = pd.NA
        return df_input


def caculate_yearly_cost(df: Any) -> float:
    """
    计算年度费用总额
    Args:
        df (Any): 包含monthly_cost列的DataFrame
    Returns:
        float: 年度费用总额
    """
    try:
        yearly_cost = df["monthly_cost"].sum()
        return yearly_cost
    except Exception as e:
        logging.error(f"计算年度费用总额时出错: {str(e)}")
        return 0.0


def dbConnect(file_path: str) -> str:
    try:
        if not os.path.exists(file_path):
            return f"错误：文件 {file_path} 不存在"

        if not file_path.lower().endswith((".xls", ".xlsx")):
            return "错误：仅支持Excel文件（.xls, .xlsx）"

        with open(file_path, "rb") as f:
            f.read(4)

        return "Excel文件验证成功"
    except Exception as e:
        return f"文件验证失败: {str(e)}"


sql_query = FunctionTool(sqlQuery, description="执行任意 SELECT SQL，返回结果前 100 行")
db_connect = FunctionTool(dbConnect, description="验证联通性")
calculate_monthly_cost_table = FunctionTool(
    calculate_monthly_cost_table, description="计算每月费用"
)
caculate_yearly_cost = FunctionTool(
    caculate_yearly_cost, description="计算年度费用总额"
)
generate_cost_rate_sql = FunctionTool(
    generate_cost_rate_sql,
    description="根据用户需求，生成用于获取金额以及分摊比例的SQL查询语句",
)
sql_tools = [sql_query, db_connect]
excel_tools = [db_connect, generate_cost_rate_sql, sql_query]
data_analyst_tools = [chart_tool, calculate_monthly_cost_table, caculate_yearly_cost]


class EfficientAssistantAgent(AssistantAgent):
    def __init__(self, name, system_message, model_client, tools=None):
        super().__init__(
            name=name,
            system_message=system_message,
            model_client=model_client,
            tools=tools,
        )
        self.system_message_sent = False

    async def send(self, message, context=None):
        if not self.system_message_sent:
            full_message = f"{self.system_message}\n{message}"
            self.system_message_sent = True
        else:
            full_message = message
        return await super().send(full_message, context=context)


Intention_Analyst_prompt = """
你是意图分类器。仅输出一行：CATEGORY:<类别>。

可选类别：
- CATEGORY:财年-需数据
- CATEGORY:成本分析-需数据
- CATEGORY:其他领域-无需数据
- CATEGORY:不清

规则：
- 只返回“CATEGORY:xxx”，不加解释与附加内容。
- 出现成本相关关键词（如 IT费用、HR费用、采购、分摊键、FY25/FY26、BGT、Actual）则归为“CATEGORY:成本分析-需数据”。
"""

Data_Analyst_prompt = """
你是数据分析专家，必须通过工具完成分析。

规则：
- 每月费用 = amount * rate；年度费用 = 各月费用求和。
- 必须使用 calculate_monthly_cost_table 计算每月费用；必要时使用 caculate_yearly_cost 汇总；可用 chart_tool 输出图表。
- 不得臆造数据，所有数据均来源于上游查询结果与工具输出。

输出格式：
ANALYSIS_DONE
<图表链接或嵌入代码>
<简要洞察>
"""

excel_sql_specialist_prompt = """
你是 Excel-SQL 专家。任务：把自然语言转成严格的 SELECT SQL，并用工具执行返回结果。

数据文件：Data/Function cost allocation analysis to IT 20260104.xlsx
工作表：CostDataBase（主）、Table7、CC Mapping、Cost Text Mapping
核心字段：Year、Function、`cost text`、CC、Amount、Month、Key

规范：
- 只允许 SELECT；禁止 DROP/DELETE/INSERT/UPDATE。
- 值使用单引号；条件用 AND；优先查询 CostDataBase，必要时再关联其他表。
- 输出仅为纯 SQL，无解释。

工具流程：
1) 先调用 db_connect 验证路径可访问；
2) 涉及分摊/Allocation 时先调用 generate_cost_rate_sql 生成 SQL；
3) 校验 SQL 中表名/字段存在；
4) 调用 sqlQuery 执行，并返回结果。

强制：generate_cost_rate_sql 成功返回后，必须随后调用 sqlQuery 执行。
输出格式：
SQL_DONE\n<查询结果>
"""

# 精简版报告/多领域/管理提示，避免冗长内容并约束仅做组织/总结，不进行计算
Report_Analyst_prompt = """
你是报告分析师。整理各工具与分析结果，输出精炼结论、关键数据点与建议。不得进行计算，所有数字均来自工具/上游结果。
输出：
REPORT_DONE\n<关键结论3-5条>\n<改进建议1-3条>
"""

multi_domain_analyst_prompt = """
你是多领域分析师。跨 IT/HR/Finance 等方面整合已得结果，提炼共性问题与差异。不得进行计算，仅基于现有结果给出洞察。
输出：
MULTI_ANALYSIS_DONE\n<共性问题>\n<关键差异>
"""

Manager_prompt = """
你是团队经理。只做任务编排与结果检查：
- 各角色须通过工具完成计算与查询；
- 汇总结果与结论，确保输出统一、简洁、可用；
- 不进行任何计算或虚构数据。
输出：
MANAGE_DONE\n<任务完成度>\n<需要补充的项(如果有)>
"""
intention_analyst = EfficientAssistantAgent(
    name="intention_analyst",
    system_message=f"""{Intention_Analyst_prompt}""",
    model_client=model_client,
    tools=[],
)
excel_sql_specialist = EfficientAssistantAgent(
    name="excel_sql_specialist",
    system_message=f"""{excel_sql_specialist_prompt}""",
    model_client=model_client,
    tools=excel_tools,
)
excel_sql_specialist_agent = AssistantAgent(
    name="excel_sql_specialist",
    system_message=f"""{excel_sql_specialist_prompt}""",
    model_client=model_client,
    tools=excel_tools,
)

data_analyst = EfficientAssistantAgent(
    name="data_analyst",
    system_message=f"""{Data_Analyst_prompt}""",
    model_client=model_client,
    tools=data_analyst_tools,
)

report_analyst = EfficientAssistantAgent(
    name="report_analyst",
    system_message=f"""{Report_Analyst_prompt}""",
    model_client=model_client,
    # tools=[sdq_tool, downtime_tool]
)

multi_domain_analyst = EfficientAssistantAgent(
    name="multi_domain_analyst",
    system_message=f"""{multi_domain_analyst_prompt}""",
    model_client=model_client,
)

manager = EfficientAssistantAgent(
    name="Manager",
    system_message=f"""{Manager_prompt}""",
    model_client=model_client,
)

from typing import Sequence
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage


def sop_selector_func(
    messages: Sequence[BaseAgentEvent | BaseChatMessage],
) -> str | None:
    if not messages:
        sop_logger.info("SOP流程开始 - 第一个消息，选择Manager")
        return "Manager"

    last_message = messages[-1]
    last_speaker = last_message.source
    content = (
        last_message.content if hasattr(last_message, "content") else str(last_message)
    )

    sop_logger.info(f"SOP流程控制 - 发言者: {last_speaker}")
    sop_logger.info(f"发言内容: {content}")

    if last_speaker == "user":
        sop_logger.info("用户消息 → 选择Manager处理")
        return "Manager"

    # Manager 的流程分发（仅保留 intention_analyst 与 excel_sql_specialist）
    if last_speaker == "Manager":
        if (
            "转交给 intention_analyst" in content
            or "转交给 **intention_analyst**" in content
        ):
            sop_logger.info("Manager → intention_analyst (意图分析)")
            return "intention_analyst"
        elif (
            "转交给 excel_sql_specialist" in content
            or "转交给 **excel_sql_specialist**" in content
        ):
            sop_logger.info("Manager → excel_sql_specialist (数据查询)")
            return "excel_sql_specialist"
        elif (
            "转交给 multi_domain_analyst" in content
            or "转交给 **multi_domain_analyst**" in content
        ):
            sop_logger.info("Manager → multi_domain_analyst (多领域分析)")
            return "multi_domain_analyst"
        elif "转交给 data_analyst" in content or "转交给 **data_analyst**" in content:
            sop_logger.info("Manager → data_analyst (数据分析)")
            return "data_analyst"
        elif "FINAL:RETURN" in content:
            sop_logger.info("Manager发出FINAL:RETURN - 流程结束")
            return None

    # intention_analyst 完成后，根据分类结果进入 excel_sql_specialist
    elif last_speaker == "intention_analyst":
        if "CATEGORY:成本分析-需数据" in content:
            sop_logger.info(
                "意图识别为成本分析需数据 → 进入 excel_sql_specialist 生成并执行SQL"
            )
            return "excel_sql_specialist"
        else:
            sop_logger.info("意图识别非成本数据分析或不清 → 返回Manager处理")
            return "Manager"

    # excel_sql_specialist 完成后：
    # - 若查询报错或结果为空 → 回到 excel_sql_specialist 重试
    # - 若查询成功且有数据 → 返回 Manager
    elif last_speaker == "excel_sql_specialist":
        lower = content.lower()
        has_success = ("SQL_DONE" in content) or ("查询成功" in content)
        has_error = (
            ("错误" in content)
            or ("error" in lower)
            or ("查询过程中出现错误" in content)
        )
        is_empty = ("结果为空" in content) or ("返回 0 行" in content)

        if has_success and not has_error and not is_empty:
            sop_logger.info("excel_sql_specialist查询成功且有数据 → 返回Manager")
            return "Manager"
        else:
            sop_logger.info("excel_sql_specialist查询失败或无结果 → 重新尝试生成SQL")
            return "excel_sql_specialist"

    sop_logger.warning(f"未匹配到明确流程规则，当前发言者: {last_speaker}")
    return None


class SOPTeam(SelectorGroupChat):
    def __init__(self, participants: List[AssistantAgent]):
        text_mention_termination = TextMentionTermination("TERMINATE")
        max_messages_termination = MaxMessageTermination(max_messages=20)

        selector_prompt = """Select the next speaker based on the conversation flow.

{roles}

Current conversation:
{history}

Select the most appropriate agent from {participants} to continue the task.
Follow the SOP workflow sequence strictly."""

        super().__init__(
            participants=participants,
            model_client=model_client,
            selector_prompt=selector_prompt,
            selector_func=sop_selector_func,
            termination_condition=text_mention_termination | max_messages_termination,
        )
        sop_logger.info("SOPTeam初始化完成")


def extract_final_answer(messages):
    sop_logger.info("🔍 开始提取最终答案...")
    final_answer = ""

    for msg in reversed(messages):
        if (
            hasattr(msg, "source")
            and msg.source == "Manager"
            and hasattr(msg, "content")
            and "FINAL:RETURN" in msg.content
        ):
            sop_logger.info("找到Manager的FINAL:RETURN消息")
            content = msg.content
            start_index = content.find("FINAL:RETURN") + len("FINAL:RETURN")
            end_index = (
                content.find("TERMINATE") if "TERMINATE" in content else len(content)
            )
            raw_segment = content[start_index:end_index].strip()
            raw_segment = (
                raw_segment.replace("ANALYSIS_DONE", "")
                .replace("SCORING_DONE", "")
                .replace("CONSULTATION_DONE", "")
                .replace("DATA_ANALYSIS_DONE", "")
            )
            final_answer = raw_segment.strip()
            sop_logger.info(f"从FINAL:RETURN提取答案，长度: {len(final_answer)}")
            break

    if not final_answer:
        sop_logger.warning("未找到FINAL:RETURN，尝试从专家回复中提取...")
        for msg in reversed(messages):
            if (
                hasattr(msg, "source")
                and msg.source in ["data_analyst", "multi_domain_analyst"]
                and hasattr(msg, "content")
            ):

                content = msg.content
                content = (
                    content.replace("ANALYSIS_DONE", "")
                    .replace("SCORING_DONE", "")
                    .replace("CONSULTATION_DONE", "")
                    .replace("DATA_ANALYSIS_DONE", "")
                )
                content = content.strip()

                if content and len(content) > 50:
                    final_answer = content
                    sop_logger.info(
                        f"从{msg.source}提取答案，长度: {len(final_answer)}"
                    )
                    break

    final_answer = final_answer.replace("TERMINATE", "").strip()
    final_answer = final_answer.replace("\\n", "\n").replace("\\'", "'")

    result = final_answer if final_answer else "未能获取到最终答案"
    sop_logger.info(f"最终答案提取完成: {result}")
    return result


async def run_Cost_sop_team(taskstr: str) -> str:
    team = SOPTeam(
        [
            manager,
            intention_analyst,
            excel_sql_specialist,
            # data_analyst,
            # multi_domain_analyst,
        ]
    )

    try:
        sop_logger.info("启动团队对话流程...")
        result = await team.run(task=taskstr)
        sop_logger.info(f"团队对话完成，共 {len(result.messages)} 条消息")
        final_answer = extract_final_answer(result.messages)
        sop_logger.info(f"提取最终答案完成，长度: {len(final_answer)} 字符")

        return final_answer

    except Exception as e:
        sop_logger.error(f"SOP团队执行失败: {str(e)}")
        raise


async def main() -> None:
    team = SOPTeam(
        [
            manager,
            intention_analyst,
            excel_sql_specialist,
            # data_analyst,
            # multi_domain_analyst,
        ]
    )
    result = await team.run(task="24财年IT费用包括？")
    print("=== 完整对话流程 ===")
    for msg in result.messages:
        print(f"{msg.source:>20} → {msg.content}")

    final_answer = extract_final_answer(result.messages)
    print("\n" + "=" * 50)
    print("最终返回给用户的答案:")
    print("=" * 50)
    print(final_answer)
    print("=" * 50)

    return final_answer


async def test_sqlQuery():
    """交互式SQL测试工具"""
    print("\n" + "=" * 50)
    print("  SQL测试交互工具")
    print("=" * 50)

    total = 0
    passed = 0

    while True:
        try:
            print("\n" + "-" * 50)
            file_path = input("请输入Excel文件路径（输入q退出）: ").strip()
            if file_path.lower() == "q":
                break

            sheet_name = input("请输入工作表名称: ").strip()
            query = input("请输入SQL查询语句: ").strip()

            # 安全检查确认
            print("\n[安全确认]")
            print(f"即将执行查询:\n{query}")
            confirm = input("确认执行？(y/n): ").strip().lower()
            if confirm != "y":
                print("已取消本次查询")
                continue

            total += 1
            print("\n" + "=" * 50)
            print(f" 开始测试 #{total} ".center(50, "="))

            # 执行测试
            messages = []
            async for chunk in excel_sql_specialist_agent.run_stream(
                task=f"执行sqlQuery：{{'file_path': '{file_path}', 'query': '{query}', 'sheet_name': '{sheet_name}'}}"
            ):
                messages.append(str(chunk))

            final_answer = extract_final_answer(
                [{"content": "".join(messages), "source": "sqlQuery"}]
            )

            # 显示结果
            print("\n测试结果:")
            print("-" * 50)
            print(final_answer)
            print("-" * 50)

            # 结果验证
            if "错误" in final_answer:
                raise AssertionError("查询包含错误")
            elif "成功" in final_answer:
                passed += 1
                print("✓ 测试通过")
            else:
                print("! 结果未明确")

        except Exception as e:
            print(f"× 测试失败: {str(e)}")
        finally:
            print(f"\n当前统计: 通过 {passed}/{total} ({(passed/total)*100:.1f}%)")

    print("\n" + "=" * 50)
    print(f" 最终测试结果: 通过 {passed}/{total} ({(passed/total)*100:.1f}%) ")
    print("=" * 50)


async def test_excel_sql_specialist_agent():
    """Excel SQL专家交互测试工具"""
    print("\n" + "=" * 50)
    print("  Excel SQL专家交互测试 ".center(50, "="))
    print("输入 'exit' 退出测试\n")

    loop = asyncio.get_running_loop()

    while True:
        try:
            # 使用异步方式获取用户输入
            user_input = await loop.run_in_executor(
                None, lambda: input("用户问题> ").strip()
            )
            if user_input.lower() in ["exit", "quit"]:
                break

            # 运行agent
            messages = []
            async for chunk in excel_sql_specialist_agent.run_stream(task=user_input):
                messages.append(str(chunk))

            # 显示结果
            print("\nAgent响应:")
            print("-" * 50)
            print("".join(messages))
            print("-" * 50)

        except KeyboardInterrupt:
            print("\n检测到中断信号，正在退出...")
            break
        except Exception as e:
            print(f"测试出错: {str(e)}")

    print("\n测试结束，感谢使用！")


async def test_excel_sql_specialist_agent_headless():
    """Excel SQL专家自动化测试工具 (非交互式)"""
    print("\n" + "=" * 50)
    print("  Excel SQL专家自动化测试 ".center(50, "="))

    user_input = "CostDataBase表中IT部门FY24年的成本是多少？"
    print(f"测试问题: {user_input}")

    try:
        # 运行agent
        messages = []
        async for chunk in excel_sql_specialist_agent.run_stream(task=user_input):
            messages.append(str(chunk))

        # 显示结果
        print("\nAgent响应:")
        print("-" * 50)
        print("".join(messages))
        print("-" * 50)
    except Exception as e:
        print(f"测试出错: {str(e)}")

    print("\n测试结束")


async def test_excel_query():
    file_path = "Data/Function cost allocation analysis to IT 20260104.xlsx"
    # 依据 sqlQuery 的签名，传入 SQL 涉及的工作表名列表
    sql_table_names = ["CostDataBase"]
    # 使用正确的表名构造查询
    query = "SELECT * FROM CostDataBase WHERE Year = 'FY24' AND Function = 'IT'"

    result = sqlQuery(file_path, query, sql_table_names)
    print("=== SQL查询结果 ===")
    print(result)


if __name__ == "__main__":
    # 自动测试（无头模式）
    # asyncio.run(test_excel_sql_specialist_agent_headless())

    # 交互式测试
    asyncio.run(test_excel_sql_specialist_agent())

    # 旧测试函数
    # asyncio.run(test_excel_query())
