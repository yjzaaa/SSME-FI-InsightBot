import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from dotenv import load_dotenv

# 直接复用 CostAnalyst 中已定义的两个 Agent：意图识别与 SQL 生成
from modules.CostAnalyst import intention_analyst, excel_sql_specialist_agent

load_dotenv(__file__)
import unittest
from modules.CostAnalyst import generate_cost_rate_sql


async def run_intent_and_sql_test():
    # 可修改为你的自然语言需求
    user_input = (
        "请给出 FY24 IT 部门费用的分摊比例 SQL，不要执行查询，只输出 SQL 语句。"
    )

    print("\n" + "=" * 50)
    print(" 意图识别测试 ")
    print("=" * 50)

    # 运行意图识别，仅获取 CATEGORY:xxx
    intent_messages = []
    try:
        async for chunk in intention_analyst.run_stream(task=user_input):
            intent_messages.append(str(chunk))
    except Exception as e:
        print(f"意图识别运行失败: {e}")
        return

    intent_output = "".join(intent_messages)
    print("意图识别输出:")
    print(intent_output)

    # 简单提取 CATEGORY:xxx（若存在）
    category = None
    for line in intent_output.splitlines():
        line = line.strip()
        if line.startswith("CATEGORY:"):
            category = line
            break
    print("提取到的类别:", category or "<未找到CATEGORY>")

    print("\n" + "=" * 50)
    print(" SQL 生成测试（仅生成 SQL，不执行查询） ")
    print("=" * 50)

    # 强化指令：只生成 SQL，不调用工具，不执行查询
    sql_task = (
        "只生成 SQL，不调用任何工具，不执行查询。严格输出一条 SELECT SQL。\n"
        + user_input
    )

    sql_messages = []
    try:
        async for chunk in excel_sql_specialist_agent.run_stream(task=sql_task):
            sql_messages.append(str(chunk))
    except Exception as e:
        print(f"SQL 生成运行失败: {e}")
        return

    sql_output = "".join(sql_messages)
    print("SQL 生成输出:")
    print(sql_output)


if __name__ == "__main__":
    asyncio.run(run_intent_and_sql_test())
