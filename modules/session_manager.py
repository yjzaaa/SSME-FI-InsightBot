import logging
import chainlit as cl
from utils.jsonhelp  import save_session_history_to_json
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

logger = logging.getLogger(__name__)
@cl.data_layer
def init_data_layer():
    """配置SQLAlchemy数据层使用SQLite异步驱动"""
    data_layer = SQLAlchemyDataLayer(conninfo="sqlite+aiosqlite:///./chainlit.db")
    return data_layer

class SessionHistoryManager:
    def __init__(self, max_messages=10, max_message_length=2048):
        """
        初始化SessionHistoryManager。

        :param max_messages: 最大消息存储数量，默认30条。
        :param max_message_length: 单条消息最大长度，默认2048字符。
        """
        self.max_messages = max_messages
        self.max_message_length = max_message_length

    async def load_from_thread_id(self, thread_id):
        """
        从线程数据中加载历史消息。

        :param thread_id: 当前线程的ID。
        """
        data_layer = init_data_layer()
        thread_data = await data_layer.get_thread(thread_id)

        messages = []
        for step in thread_data.get("steps", []):
            role = "user" if step["type"] == "user_message" else "assistant"
            content = step.get("input") or step.get("output")

            if content:  # 仅在内容非空时添加
                # content = self.truncate_content(content)
                messages.append({
                    "role": role,
                    "content": content
                })
        # messages = self.truncate_messages(messages)
        
        # 截断消息到最大数量
        return messages
    async def chat_resumed(self,user_message, thread_id):
    
        messages =[]
        chat_resumed = cl.user_session.get("chat_resumed", False)
        context_rebuilt = cl.user_session.get("context_rebuilt", False)

        try:
            # 获取当前会话历史（通过 session_manager）
            session_history = await self.load_from_thread_id(thread_id)
            # # 只保留最近10轮对话（20条消息）
            for msg in session_history[-20:]:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    # if msg["role"] in ["user", "assistant"]:
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })

            # 添加当前用户消息
            if chat_resumed and len(messages) == 0:
                context_hint = f"(这是一个恢复的历史对话，我会根据可见的对话记录来理解上下文) {user_message}"
                current_user_msg = {"role": "user", "content": context_hint}
            else:
                current_user_msg = {"role": "user", "content": user_message}
            messages.append(current_user_msg)
            # save_session_history_to_json(thread_id,messages)
            logger.info(f"Using {len(messages)} messages for context (including current message)")

        except Exception as e:
            logger.warning(f"Failed to load conversation history from session_manager: {e}, using current message only")
            messages = [{"role": "user", "content": user_message}]

        return messages

    def truncate_messages(self, messages):
        """
        截断消息列表到最大数量。
        """
        if len(messages) > self.max_messages:
            return messages[-self.max_messages:]
        return messages

    def truncate_content(self, content):
        """
        截断单条消息内容到最大长度。
        """
        if isinstance(content, str) and len(content) > self.max_message_length:
            return content[:self.max_message_length]
        return content
