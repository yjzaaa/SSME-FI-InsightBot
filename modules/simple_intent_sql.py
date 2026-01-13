import asyncio
import os
import sys
import pandas as pd
from dotenv import load_dotenv
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.tools import FunctionTool
from autogen_core.models import ModelFamily

# 加载环境变量
load_dotenv()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

# 1. 配置模型客户端
model_client = OpenAIChatCompletionClient(
    model=os.getenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-R1"),
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    base_url=os.getenv("SILICONFLOW_BASE_URL"),
    temperature=0,
    model_info={
        "vision": False,
        "function_calling": True,
        "json_output": True,
        "family": ModelFamily.UNKNOWN,
    },
)


# 2. 定义工具 (Tools)
def get_business_context() -> str:
    """
    读取 'Data/Function cost allocation analysis to IT 20260104.xlsx' 文件。
    返回 '解释和逻辑' 和 '问题' 两个 Sheet 的内容，用于辅助生成 SQL。
    """
    file_path = "Data/Function cost allocation analysis to IT 20260104.xlsx"
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    try:
        context = []

        # 读取 '解释和逻辑' Sheet
        try:
            df_logic = pd.read_excel(file_path, sheet_name="解释和逻辑")
            context.append(
                "=== Sheet: 解释和逻辑 (Logic) ===\n"
                + df_logic.to_markdown(index=False)
            )
        except Exception as e:
            context.append(f"Warning: Could not read '解释和逻辑' sheet: {e}")

        # 读取 '问题' Sheet
        try:
            df_qa = pd.read_excel(file_path, sheet_name="问题")
            context.append(
                "\n=== Sheet: 问题 (Questions) ===\n" + df_qa.to_markdown(index=False)
            )
        except Exception as e:
            context.append(f"Warning: Could not read '问题' sheet: {e}")

        return "\n\n".join(context)

    except Exception as e:
        return f"Error reading excel file: {str(e)}"


# 3. 定义提示词 (Prompts)

# 意图识别 Agent 提示词
INTENT_PROMPT = """
你是意图分类专家。
任务：判断用户输入是否需要查询数据库生成 SQL。
输出规则：
- 如果涉及数据查询，输出 "NEXT: SQL_GEN"
- 如果无关，输出 "FINAL: 无法处理"
"""

# SQL 生成 Agent 提示词
SQL_GEN_PROMPT = """
你是 SQL 生成专家。
数据表结构：
- CostDataBase (Year, Function, "cost text", CC, Amount, Month, Key)
- 其他表请参考业务逻辑上下文。

任务：将自然语言转换为 SQLite 查询语句。
流程：
1. **必须首先调用** `get_business_context` 工具，获取业务逻辑和问题定义的上下文。
2. 分析上下文中的 "解释和逻辑" 了解分摊规则、字段映射关系。
3. 分析上下文中的 "问题" 了解常见问题的查询模式。
4. 基于上下文和用户输入生成 SQL。

规则：
1. 仅输出 SQL 语句，不要包含 markdown 标记或解释。
2. 字符串使用单引号。
3. Year 字段格式为 'FYxx' (如 'FY24', 'FY25')。
4. 结束时输出 "TERMINATE"。
"""

# 4. 创建 Agents

intent_agent = AssistantAgent(
    name="intent_classifier",
    system_message=INTENT_PROMPT,
    model_client=model_client,
)

sql_agent = AssistantAgent(
    name="sql_generator",
    system_message=SQL_GEN_PROMPT,
    model_client=model_client,
    tools=[
        FunctionTool(get_business_context, description="获取业务逻辑和问题定义的上下文")
    ],
)

# 5. 定义工作流选择逻辑 (Selector)


def selector_func(messages):
    last_msg = messages[-1]

    # 初始状态或用户输入后，交给意图识别
    if last_msg.source == "user":
        return "intent_classifier"

    # 意图识别后，根据输出决定
    if last_msg.source == "intent_classifier":
        if "NEXT: SQL_GEN" in last_msg.content:
            return "sql_generator"
        else:
            return None  # 结束

    # SQL生成后，结束
    if last_msg.source == "sql_generator":
        # 如果调用了工具，继续由 sql_generator 处理（接收工具结果）
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "sql_generator"
        # 否则结束
        return None

    return "intent_classifier"


# 6. 构建团队 (Team)


async def run_workflow(user_query: str):
    print(f"\n>>> 用户输入: {user_query}")

    team = SelectorGroupChat(
        participants=[intent_agent, sql_agent],
        model_client=model_client,
        selector_func=selector_func,
        termination_condition=TextMentionTermination("TERMINATE"),
    )

    # 运行工作流
    async for msg in team.run_stream(task=user_query):
        if hasattr(msg, "content") and msg.content:
            print(f"\n[{msg.source}]: {msg.content}")


if __name__ == "__main__":
    # 示例测试
    query = "25财年实际分摊给CT的IT费用是多少？"
    asyncio.run(run_workflow(query))
