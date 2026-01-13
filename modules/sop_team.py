import os
import asyncio
from typing import List
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination,MaxMessageTermination
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from autogen_core.tools import FunctionTool
from sqlalchemy import create_engine, text
import pandas as pd
import sys
import logging
from datetime import datetime
from autogen_agentchat import EVENT_LOGGER_NAME, TRACE_LOGGER_NAME
from dotenv import load_dotenv
import os
from modules.tools.report_analyst_tools import sdq_tool, downtime_tool, total_score_tool, supplier_scoring_tool
from modules.tools.chart_tools import chart_tool
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)

logging.basicConfig(level=logging.DEBUG)

# For trace logging - 记录调试信息和执行流程
trace_logger = logging.getLogger(TRACE_LOGGER_NAME)
trace_logger.addHandler(logging.StreamHandler())
trace_logger.setLevel(logging.DEBUG)

# For structured message logging, such as low-level messages between agents.
event_logger = logging.getLogger(EVENT_LOGGER_NAME)
event_logger.addHandler(logging.StreamHandler())
event_logger.setLevel(logging.DEBUG)


today = datetime.now().strftime("%Y%m%d")
log_filename = f"log/sop_flow_{today}.log"

# 为 trace_logger 和 event_logger 都添加文件处理器
file_handler_trace = logging.FileHandler(log_filename, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
file_handler_trace.setFormatter(formatter)
trace_logger.addHandler(file_handler_trace)

file_handler_event = logging.FileHandler(log_filename, encoding="utf-8")
file_handler_event.setFormatter(formatter)
event_logger.addHandler(file_handler_event)


sop_logger = logging.getLogger(f"{TRACE_LOGGER_NAME}.sop_team")
sop_logger.setLevel(logging.INFO)  

# ---------- 1.  模型客户端 ----------

model_client = AzureOpenAIChatCompletionClient(
    azure_deployment=os.getenv('AZURE_OPENAI_DEPLOYMENT'),
    model=os.getenv('AZURE_OPENAI_DEPLOYMENT'),
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
    api_version=os.getenv('AZURE_OPENAI_API_VERSION'),
    api_key=os.getenv('AZURE_OPENAI_API_KEY'),  
    temperature=0,
)

def sqlQuery(connection_string: str, query: str) -> str:
    """
    执行SQL查询并返回结果
    
    Args:
        connection_string: 数据库连接字符串
        query: SQL查询语句
        
    Returns:
        查询结果的字符串表示
    """
    try:
        # 安全检查
        query_upper = query.strip().upper()
       # if not query_upper.startswith('SELECT'):
        #    return "错误：只允许执行SELECT查询语句"
            
        dangerous_patterns = [
            'DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER', 
            'EXEC', 'TRUNCATE', 'MERGE', 'REPLACE'
        ]
        for pattern in dangerous_patterns:
            if pattern in query_upper :
                return f"错误：查询中包含不允许的操作: {pattern}"
        
        # 执行查询
        engine = create_engine(connection_string)
        with engine.connect() as conn:
            df = pd.read_sql_query(text(query), conn)
        
        if df.empty:
            return "查询成功，但结果为空"
        else:
            return f"查询成功，返回 {len(df)} 行数据:\n" + df.to_string()
            
    except Exception as e:
        return f"查询过程中出现错误: {str(e)}"
    

def dbConnect(connection_string: str) -> str:
    """
    连接到数据库并测试连接
    
    Args:
        connection_string: 数据库连接字符串
        
    Returns:
        连接成功或失败的消息
    """
    try:
        engine = create_engine(connection_string)
        # 测试连接
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "数据库连接成功"
    except Exception as e:
        return f"数据库连接失败: {str(e)}"
    


sql_query =FunctionTool(sqlQuery,description="执行任意 SELECT SQL，返回结果前 100 行")
db_connect =FunctionTool(dbConnect,description="验证联通性")
# 为 SQL Specialist 增加财年解析工具
sql_tools = [sql_query, db_connect]

class EfficientAssistantAgent(AssistantAgent):
    def __init__(self, name, system_message, model_client, tools=None):
        super().__init__(name=name, system_message=system_message, model_client=model_client, tools=tools)
        self.system_message_sent = False

    async def send(self, message, context=None):
        if not self.system_message_sent:
            full_message = f"{self.system_message}\n{message}"
            self.system_message_sent = True
        else:
            full_message = message
        return await super().send(full_message, context=context)

# ---------- 2.  定义 Agent ----------
with open('prompt/Intention_Analyst_prompt.txt', 'r',encoding='utf-8') as file:
    Intention_Analyst_prompt = file.read()
with open('prompt/Data_Analyst_prompt.txt', 'r',encoding='utf-8') as file:
    Data_Analyst_prompt = file.read()
with open('prompt/Report_Analyst_prompt.txt', 'r',encoding='utf-8') as file:
    Report_Analyst_prompt = file.read()
with open('prompt/Sql_Specialist_prompt.txt', 'r',encoding='utf-8') as file:
    Sql_Specialist_prompt = file.read()
with open('prompt/multi_domain_analyst.txt', 'r',encoding='utf-8') as file:
    multi_domain_analyst_prompt = file.read()
with open('prompt/Manager_prompt.txt', 'r',encoding='utf-8') as file:
    Manager_prompt = file.read()

intention_analyst = EfficientAssistantAgent(
    name="intention_analyst",
    system_message=f"""{Intention_Analyst_prompt}""",
    model_client=model_client,
)

sql_specialist = EfficientAssistantAgent(
    name="sql_specialist",
    system_message=f"""{Sql_Specialist_prompt}""",
    model_client=model_client,
    tools=sql_tools,
)

data_analyst = EfficientAssistantAgent(
    name="data_analyst",
    system_message=f"""{Data_Analyst_prompt}""",
    model_client=model_client,
    tools=[chart_tool]
)


report_analyst = EfficientAssistantAgent(
    name="report_analyst",
    system_message=f"""{Report_Analyst_prompt}""",
    model_client=model_client,
    tools=[supplier_scoring_tool, sdq_tool, downtime_tool, total_score_tool]
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


# ---------- 3.  SelectorGroupChat 实现 SOP 流程 ----------
from typing import Sequence
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage

def sop_selector_func(messages: Sequence[BaseAgentEvent | BaseChatMessage]) -> str | None:
    if not messages:
        sop_logger.info("SOP流程开始 - 第一个消息，选择Manager")
        return "Manager"
    
    last_message = messages[-1]
    last_speaker = last_message.source
    content = last_message.content if hasattr(last_message, 'content') else str(last_message)
    
    sop_logger.info(f"SOP流程控制 - 发言者: {last_speaker}")
    sop_logger.info(f"发言内容: {content}")
    
    # 用户提问后 → Manager
    if last_speaker == "user":
        sop_logger.info("用户消息 → 选择Manager处理")
        return "Manager"
    
    # Manager的流程分发
    if last_speaker == "Manager":
        if "转交给 intention_analyst" in content or "转交给 **intention_analyst**" in content:
            sop_logger.info("Manager → intention_analyst (意图分析)")
            return "intention_analyst"
        elif "转交给 sql_specialist" in content or "转交给 **sql_specialist**" in content:
            sop_logger.info("Manager → sql_specialist (数据查询)")
            return "sql_specialist"
        elif "转交给 multi_domain_analyst" in content or "转交给 **multi_domain_analyst**" in content:
            sop_logger.info("Manager → multi_domain_analyst (多领域分析)")
            return "multi_domain_analyst"
        elif "转交给 data_analyst" in content or "转交给 **data_analyst**" in content:
            sop_logger.info("Manager → data_analyst (数据分析)")
            return "data_analyst"
        elif "转交给 report_analyst" in content or "转交给 **report_analyst**" in content:
            sop_logger.info("Manager → report_analyst (报告分析)")
            return "report_analyst"
        elif "FINAL:RETURN" in content:
            sop_logger.info("Manager发出FINAL:RETURN - 流程结束")
            return None  # 结束对话
    
    # intention_analyst 完成后 → Manager
    elif last_speaker == "intention_analyst":
        if "CATEGORY:" in content:
            sop_logger.info("intention_analyst完成分类 → 返回Manager")
            return "Manager"
    
    # sql_specialist 完成后 → Manager
    elif last_speaker == "sql_specialist":
        if "SQL_DONE" in content:
            sop_logger.info("sql_specialist完成查询 → 返回Manager")
            return "Manager"
    
    # report_analyst 完成后 → Manager (Manager会判断是否需要继续data_analyst)
    elif last_speaker == "report_analyst":
        if "SCORING_DONE" in content:
            sop_logger.info("report_analyst完成打分 → 返回Manager")
            return "Manager"
        elif "需要补充" in content and ("数据" in content or "信息" in content):
            sop_logger.info("report_analyst需要补充数据 → 转交Manager协调")
            return "Manager"
    
    # data_analyst 完成后 → Manager
    elif last_speaker == "data_analyst":
        if "ANALYSIS_DONE" in content:
            sop_logger.info("data_analyst完成分析 → 返回Manager")
            return "Manager"
        elif "需要补充数据" in content or "所需补充数据" in content:
            sop_logger.info("data_analyst需要补充数据 → 转交Manager协调")
            return "Manager"
    
    # multi_domain_analyst 完成后 → Manager
    elif last_speaker == "multi_domain_analyst":
        if "CONSULTATION_DONE" in content:
            sop_logger.info("multi_domain_analyst完成咨询 → 返回Manager")
            return "Manager"
    
    # 默认返回None，让模型选择
    sop_logger.warning(f"未匹配到明确流程规则，当前发言者: {last_speaker}")
    return None

class SOPTeam(SelectorGroupChat):
    def __init__(self, participants: List[AssistantAgent]):
        
        text_mention_termination = TextMentionTermination("TERMINATE")
        max_messages_termination = MaxMessageTermination(max_messages=25)
        
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
            selector_func=sop_selector_func,  # 使用自定义流程控制
            termination_condition=text_mention_termination | max_messages_termination
        )
        sop_logger.info("SOPTeam初始化完成")


# ---------- 5.  启动 ----------
def extract_final_answer(messages):
    """
    从消息流中提取最终需要返回给用户的答案
    """
    sop_logger.info("🔍 开始提取最终答案...")
    final_answer = ""
    
    # 查找包含FINAL:RETURN的Manager消息
    for msg in reversed(messages):
        if (hasattr(msg, 'source') and msg.source == "Manager" and 
            hasattr(msg, 'content') and "FINAL:RETURN" in msg.content):
            sop_logger.info("找到Manager的FINAL:RETURN消息")
            content = msg.content
            # 截取 FINAL:RETURN 与 TERMINATE 之间的全部内容（如果存在 TERMINATE）
            start_index = content.find("FINAL:RETURN") + len("FINAL:RETURN")
            end_index = content.find("TERMINATE") if "TERMINATE" in content else len(content)
            raw_segment = content[start_index:end_index].strip()
            # 移除技术标识符
            raw_segment = raw_segment.replace("ANALYSIS_DONE", "").replace("SCORING_DONE", "").replace("CONSULTATION_DONE", "")
            final_answer = raw_segment.strip()
            sop_logger.info(f"从FINAL:RETURN提取答案，长度: {len(final_answer)}")
            break
    
    # 如果没找到FINAL:RETURN，查找最后一个有实质内容的专家回复
    if not final_answer:
        sop_logger.warning("未找到FINAL:RETURN，尝试从专家回复中提取...")
        for msg in reversed(messages):
            if (hasattr(msg, 'source') and msg.source in 
                ["data_analyst", "report_analyst", "multi_domain_analyst"] and
                hasattr(msg, 'content')):
                
                content = msg.content
                # 移除技术标识符
                content = content.replace("ANALYSIS_DONE", "").replace("SCORING_DONE", "").replace("CONSULTATION_DONE", "")
                content = content.strip()
                
                if content and len(content) > 50:  # 确保有实质内容
                    final_answer = content
                    sop_logger.info(f"从{msg.source}提取答案，长度: {len(final_answer)}")
                    break
    
    # 清理内容，移除 TERMINATE 标记
    final_answer = final_answer.replace("TERMINATE", "").strip()
                            
    # 处理转义字符
    final_answer = final_answer.replace("\\n", "\n").replace("\\'", "'")
    
    result = final_answer if final_answer else "未能获取到最终答案"
    # 去除日志中的省略号，避免给人截断错觉
    sop_logger.info(f"最终答案提取完成: {result}")
    return result


async def run_sop_team(taskstr: str) -> str:
    team = SOPTeam([manager, intention_analyst, sql_specialist, data_analyst, report_analyst, multi_domain_analyst])
    
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

#测试代码
async def main() -> None:
    team = SOPTeam([manager, intention_analyst, sql_specialist, data_analyst, report_analyst, multi_domain_analyst])
    result = await team.run(task="9400054在2025年7月的分数是多少？")
    #result = await team.run(task="9400054在2025年7月份的NCM数量是多少")
    # 显示完整对话流程
    print("=== 完整对话流程 ===")
    for msg in result.messages:
        print(f"{msg.source:>20} → {msg.content}")
    
    # 提取并显示最终答案
    final_answer = extract_final_answer(result.messages)
    print("\n" + "="*50)
    print("最终返回给用户的答案:")
    print("="*50)
    print(final_answer)
    print("="*50)
    
    return final_answer


if __name__ == "__main__":
    asyncio.run(main())
