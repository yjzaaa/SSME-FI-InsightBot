import logging

# from autogenstudio.teammanager import TeamManager
# from modules.sop_team import run_sop_team
from modules.CostAnalyst import run_Cost_sop_team
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# AutoGen Studio团队管理器
class AutoGenTeamManager:
    # def __init__(self):
    # try:
    # self.team_manager = TeamManager()
    # self.team_config_path = "team-config-cn1.1.json"
    # logger.info("AutoGen Studio TeamManager initialized with English config")
    # except Exception as e:
    # logger.error(f"Failed to initialize TeamManager: {e}")
    # self.team_manager = None

    async def run_team_workflow(self, task: str, context_messages: list = None) -> str:
        """运行AutoGen团队工作流"""
        try:
            logger.info(f"Running AutoGen team workflow for task: {task[:50]}...")

            # 检查team_manager是否初始化成功
            # if not hasattr(self, 'team_manager') or self.team_manager is None:
            #    return "❌ AutoGen工作流未初始化，请检查配置。可能原因：\n1. TeamManager导入失败\n2. 配置文件缺失\n3. 依赖包未安装"

            # 构建包含上下文的任务描述
            if context_messages and len(context_messages) > 1:
                last_user_msg = None
                for msg in reversed(context_messages[:-1]):
                    if msg.get("role") == "user":
                        last_user_msg = msg.get("content", "")[:100]
                        break

                if last_user_msg:
                    full_task = (
                        f"基于上一轮对话: {last_user_msg}...\n\n当前任务: {task}"
                    )
                else:
                    full_task = task
            else:
                full_task = task

            # 运行工作流
            # result = await self.team_manager.run(
            #     task=full_task,
            #     team_config=self.team_config_path
            # )
            # 提取最终答案
            # final_answer = self.extract_final_answer(str(result))
            final_answer = await run_Cost_sop_team(full_task)

            return final_answer

        except Exception as e:
            logger.error(f"AutoGen workflow error: {e}")
            return f"❌ 工作流执行失败: {str(e)}\n\n建议：\n1. 检查网络连接\n2. 稍后重试\n3. 简化查询内容"

    # def extract_final_answer(self, workflow_result):
    #     """
    #     从工作流结果中提取最终答案
    #     """
    #     try:
    #         # 查找 Manager_agent 的最后一条消息，这通常包含最终分析结果
    #         if "source='Manager_agent'" in workflow_result:
    #             # 分割消息来找到所有 Manager_agent 的消息
    #             parts = workflow_result.split("source='Manager_agent'")

    #             if len(parts) > 1:
    #                 # 获取最后一个 Manager_agent 消息
    #                 last_analyst_message = parts[-1]

    #                 # 提取 content 字段的内容
    #                 if "content='" in last_analyst_message:
    #                     content_start = last_analyst_message.find("content='") + len("content='")
    #                     content_end = last_analyst_message.find("', type='TextMessage'")

    #                     if content_end == -1:
    #                         # 尝试其他结束模式
    #                         content_end = last_analyst_message.find("')", content_start)
    #                         if content_end == -1:
    #                             content_end = last_analyst_message.find("', metadata=", content_start)

    #                     if content_end > content_start:
    #                         final_content = last_analyst_message[content_start:content_end]
    #                         # 清理内容，移除 TERMINATE 标记
    #                         final_content = final_content.replace("TERMINATE", "").strip()

    #                         # 处理转义字符
    #                         final_content = final_content.replace("\\n", "\n").replace("\\'", "'")

    #                         if final_content:
    #                             return f"📊 **数据分析结果**\n\n{final_content}"

    #         # 如果没有找到 Manager_agent 消消息，尝试查找其他有用的消息
    #         if "ToolCallSummaryMessage" in workflow_result and "Query successful" in workflow_result:
    #             # 查找查询结果摘要
    #             if "content='" in workflow_result:
    #                 content_parts = workflow_result.split("content='")
    #                 for part in content_parts:
    #                     if "Query successful" in part:
    #                         content_end = part.find("', type='ToolCallSummaryMessage'")
    #                         if content_end > 0:
    #                             query_result = part[:content_end]
    #                             query_result = query_result.replace("\\n", "\n").replace("\\'", "'")
    #                             return f"📋 **查询结果**\n\n{query_result}"

    #         # 如果以上都没找到，返回简化的结果
    #         return f"✅ **工作流执行完成**\n\n工作流已成功执行，但结果格式需要进一步解析。原始结果：\n\n{workflow_result[:500]}{'...' if len(workflow_result) > 500 else ''}"

    #     except Exception as e:
    #         logger.error(f"Error extracting final answer: {e}")
    #         return f"⚠️ **结果解析异常**\n\n工作流执行成功，但无法解析最终结果。\n错误: {str(e)}\n\n原始结果：\n{workflow_result[:300]}{'...' if len(workflow_result) > 300 else ''}"
