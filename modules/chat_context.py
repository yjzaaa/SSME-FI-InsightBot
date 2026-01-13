import logging
import chainlit as cl

# 配置日志
logger = logging.getLogger(__name__)

def build_contextual_task(current_message: str, conversation_history: list) -> str:
    """
    构建包含上下文的任务描述，用于AutoGen工作流
    """
    try:
        # 获取最近的相关对话（最多查看最近5轮对话）
        relevant_context = []
        recent_messages = conversation_history[-10:] if conversation_history else []
        
        # 寻找包含工作流结果的历史消息
        for msg in recent_messages:
            if msg.get('role') == 'assistant':
                content = msg.get('content', '')
                # 检查是否包含数据分析结果或查询结果
                if any(indicator in content.lower() for indicator in [
                    '数据分析结果', '查询结果', '物料', 'ncm', '供应商', 
                    'defectivepartmaterialnumber', 'ncmcount', '次数', '统计'
                ]):
                    relevant_context.append(content)
                    break  # 只需要最近一次的工作流结果
        
        # 构建上下文任务
        if relevant_context:
            context_summary = relevant_context[0]
            # 截取重要信息，避免太长
            if len(context_summary) > 500:
                context_summary = context_summary[:500] + "..."
                
            contextual_task = f"""
基于之前的分析结果，用户现在有进一步的请求。

之前的分析结果概要：
{context_summary}

用户的新请求：
{current_message}

请基于之前的分析结果，针对用户的新请求提供相应的查询和分析。如果用户需要更详细的数据，请提供完整的查询结果。如果用户需要进一步分析，请基于现有数据进行深入分析。
"""
            return contextual_task
        else:
            # 如果没有相关上下文，返回原始消息
            return current_message
            
    except Exception as e:
        logger.warning(f"Failed to build contextual task: {e}")
        return current_message

async def rebuild_context_from_thread():
    """从当前线程重建对话上下文"""
    try:
        thread_id = cl.user_session.get("thread_id")
        user_id = cl.user_session.get("user_id")
        
        await cl.Message(
            content="🔄 正在分析历史对话并重建上下文...",
            author="System"
        ).send()
        
        # 重置对话历史，让AI依赖界面上可见的历史消息来理解上下文
        cl.user_session.set("conversation_history", [])
        cl.user_session.set("context_rebuilt", True)
        
        await cl.Message(
            content="✅ **上下文重建完成！**\n\n🧠 我现在处于**智能上下文模式**：\n- 我可以看到我们之前的所有对话记录\n- 我会根据历史对话来理解当前的语境\n- 请直接继续我们的对话，无需重复之前说过的内容\n\n💬 您可以问我：\"我们之前聊了什么？\" 或直接继续新的话题。",
            author="System"
        ).send()
        
        logger.info(f"Context rebuilt for thread {thread_id}")
        
    except Exception as e:
        logger.error(f"Error rebuilding context: {e}")
        await cl.Message(
            content="❌ 重建上下文时出现错误，但您仍然可以继续对话。AI会尽力根据可见的历史消息来理解上下文。",
            author="System"
        ).send()
