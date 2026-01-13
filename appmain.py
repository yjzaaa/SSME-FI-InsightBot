import os
import ssl
import boto3
from botocore.exceptions import ClientError
import json
import chainlit as cl
from datetime import datetime
import logging
import pyodbc
import asyncio
import uuid
from typing import List, Dict, Any, Optional
#from autogenstudio.teammanager import TeamManager
import re
from dotenv import load_dotenv
from modules.session_manager import SessionHistoryManager
from modules.bedrock_client import BedrockChatClient
from modules.autogen_manager import AutoGenTeamManager
from modules.login  import login
from utils.jsonhelp  import save_session_history_to_json
from autogen_agentchat.messages import TextMessage, ToolCallSummaryMessage
from autogen_core.models._types import SystemMessage, UserMessage, AssistantMessage
# 加载环境变量
load_dotenv()
import chainlit as cl
from chainlit.server import app          # 2.8.1 同样暴露 FastAPI 实例
from fastapi.responses import Response
from starlette.requests import Request

@app.middleware("http")
async def fix_cors(request: Request, call_next):
    origin = request.headers.get("origin")

    # 白名单按需写
    allow_list = {"http://shai535a.ad005.onehc.net:5173",
                  "http://localhost:5173"}

    # 预检请求先返回空体
    if request.method == "OPTIONS":
        response = Response(status_code=200)
    else:
        response = await call_next(request)

    # 统一加头
    if origin in allow_list:
        response.headers["Access-Control-Allow-Origin"]  = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        req_headers = request.headers.get("access-control-request-headers")
        if req_headers:
            # 去掉多余空格，防止浏览器严格校验失败
            response.headers["Access-Control-Allow-Headers"] = req_headers.strip()
        else:
            # 非预检兜底
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization, X-Requested-With, x-chat-id"
            )
    return response
# 禁用SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置SQLAlchemy Data Layer使用SQLite with aiosqlite

# 用户对象辅助函数 - 解决Chainlit框架中user对象格式不一致问题
def get_user_identifier(user):
    """获取用户标识符，兼容dict和object格式"""
    if user is None:
        return "anonymous"
    
    if isinstance(user, dict):
        return user.get('identifier', user.get('id', 'anonymous'))
    else:
        return getattr(user, 'identifier', getattr(user, 'id', 'anonymous'))

def get_user_metadata(user):
    """获取用户元数据，兼容dict和object格式"""
    if user is None:
        return {}
    
    if isinstance(user, dict):
        return user.get('metadata', {})
    else:
        return getattr(user, 'metadata', {})


# 初始化组件
autogen_manager = AutoGenTeamManager()
sessionHistoryManager= SessionHistoryManager()

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

# 暂时禁用SQLAlchemy数据层以避免SQL Server兼容性问题
# 配置SQLAlchemy Data Layer连接到本地SQL Server（使用异步驱动）
# SQL Server异步连接字符串格式：mssql+aioodbc://server/database?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes
# conninfo = "mssql+aioodbc://localhost/AITest?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"

# @cl.data_layer
# def get_data_layer():
#     """配置SQLAlchemy数据层"""
#     return SQLAlchemyDataLayer(conninfo=conninfo)

@cl.header_auth_callback
def header_auth_callback(headers: Dict) -> Optional[cl.User]:
    # 验证头部的令牌签名（例如JWT令牌）
    # 或检查值是否与数据库中的记录匹配
    if headers.get("gid"):
        # return cl.User(identifier="admin", metadata={"role": "admin", "provider": "header"})
        user_info = login.get_user_info(headers.get("gid"))
        return cl.User(
            identifier=user_info.get("true_name"),
            metadata={"role": "user", "provider": "header", "authenticated": True, "user_info": user_info}
        )
    else:
        return None
# 身份验证回调
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    username="123@11.com"
    password="123"
    # 简单验证 - 您可以根据需要修改验证逻辑
    if username == "123@11.com" and password == "123":
        return cl.User(
            identifier=username,
            metadata={"role": "user", "provider": "credentials", "authenticated": True}
        )
    # 使用自定义登录模块验证用户
    if login.verify_user(username, password):
        user_info = login.get_user_info(username)
        return cl.User(
            identifier=user_info.get("true_name"),
            metadata={"role": "user", "provider": "custom_db", "authenticated": True, "user_info": user_info}
        )

    return None

@cl.on_chat_start
async def start():
    """聊天开始时的初始化"""
    user = cl.user_session.get("user")
    user_id = get_user_identifier(user)
    
    logger.info(f"Chat started for user: {user_id}")
    
    # 生成线程ID
    import uuid
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("user_id", user_id)
    
    # 初始化对话历史记录
    cl.user_session.set("conversation_history", [])
    
    # 发送欢迎消息
    # await cl.Message(
    #     content=f"欢迎使用 **对话系统**！\n\n",
    #     author="Assistant"
    # ).send()

@cl.on_chat_resume
async def resume_chat(thread: dict):
    """从历史对话恢复聊天时的处理"""
    user = cl.user_session.get("user")
    user_id = get_user_identifier(user)
    
    # 获取恢复的线程ID
    thread_id = thread.get("id")
    thread_name = thread.get("name", "历史对话")
    
    logger.info(f"Chat resumed for user: {user_id}, thread: {thread_id}")

    # logger.info(thread_data)
    # 设置线程信息
    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("user_id", user_id)
    
    # 重建对话历史上下文
    try:
        # 标记这是一个恢复的对话
        cl.user_session.set("chat_resumed", True)
        
        logger.info(f"Successfully resumed chat with thread {thread_id}")
        
    except Exception as e:
        logger.error(f"Error resuming chat: {e}")
        # 如果出现任何错误，仍然设置基本状态以保证可以继续对话
        cl.user_session.set("conversation_history", [])
        cl.user_session.set("chat_resumed", True)
        
        await cl.Message(
            content=f"🔄 **已恢复对话**: {thread_name}\n\n⚠️ 恢复过程中遇到一些问题，但您可以继续对话。\n\n如果需要回忆之前的内容，请告诉我您想了解什么。",
            author="System"
        ).send()

@cl.on_message
async def message_handler(message: cl.Message):
    """处理用户消息 - 支持智能意图识别和双模式调用"""
    user = cl.user_session.get("user")
    user_id = get_user_identifier(user)
    thread_id = cl.user_session.get("thread_id")
    user_message = message.content

    logger.info(f"Processing message from {user_id}: {user_message[:50]}...")
    
    # 特殊命令处理：重建上下文
    if user_message.strip().lower() in ["重建上下文", "rebuild context", "恢复记忆", "restore memory"]:
        await rebuild_context_from_thread()
        return
    
    # 使用 session_manager 管理会话历史
    messages = await sessionHistoryManager.chat_resumed(user_message, thread_id)

    # 意图识别 - 决定使用哪种处理方式，传递对话历史以支持上下文追问
    # session_history = cl.user_session.get("conversation_history", [])
    #intent = intent_classifier.classify_intent(user_message, conversation_history=session_history)
    #logger.info(f"Detected intent: {intent}")
    # save_session_history_to_json(session_history)
    # 创建助手消息
    assistant_message = cl.Message(content="", author="Assistant")
    await assistant_message.send()
    
     # 创建异步任务来处理动态loading效果
    try:
        # 🔧 使用AutoGen工作流处理
        await assistant_message.stream_token("**Generating anwer**\n\n")

       # 构建包含上下文的完整任务描述
        context_task = build_contextual_task(user_message, messages)
        workflow_result = await autogen_manager.run_team_workflow(context_task, messages)
        #workflow_result = "sdfsfdtestttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttt"
        
        # 清空loading内容，显示真正的答案
        assistant_message.content = ""
        await assistant_message.update()

        #await assistant_message.stream_token(workflow_result)
        # 🎯 使用新的图表处理功能
        await process_response_with_charts(workflow_result, assistant_message) 
        #full_response = f"🔍 **检测到数据查询/分析请求，正在启动专业团队工作流...**\n\n📊 **团队成员**: Manager → SQL专家 → 数据分析师\n\n✅ **工作流处理完成**\n\n📋 **分析结果**:\n{workflow_result}"
        
        # 完成响应
        await assistant_message.update()
        # 将助手回复添加到会话历史记录
        # try:
        #     # 使用 session_manager 记录助手回复
        #     # sessionHistoryManager.add_message("assistant", full_response)
        #     # 可选：持久化到 JSON 文件
        #     # save_session_history_to_json(sessionHistoryManager.get_messages())
        #     logger.info(f"Added assistant response to session history. Total messages: {len(sessionHistoryManager.get_messages())}")
        # except Exception as e:
        #     logger.warning(f"Failed to update session history via session_manager: {e}")
        
        # logger.info(f"Response completed for user {user_id} using workflow mode")
        
    except Exception as e:
        error_msg = f"❌ 处理消息时出错: {str(e)}"
        logger.error(error_msg)
        await assistant_message.stream_token(error_msg)
        await assistant_message.update()
        
        # 即使出错也要记录（用于上下文）
        # try:
        #     # 使用 sessionHistoryManager 记录助手错误回复
        #     sessionHistoryManager.add_message("assistant", error_msg)
        #     logger.info(f"Added assistant error response to session history. Total messages: {len(sessionHistoryManager.get_messages())}")
        # except Exception as ex:
        #     logger.warning(f"Failed to update session history via session_manager after error: {ex}")

@cl.action_callback("clear_history")
async def clear_history():
    """清除当前线程历史"""
    user = cl.user_session.get("user")
    user_id = get_user_identifier(user)
    thread_id = cl.user_session.get("thread_id")
    
    # 清除会话级别的对话历史
    cl.user_session.set("conversation_history", [])
    
    # 开始新的线程
    import uuid
    new_thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", new_thread_id)
    
    await cl.Message(content="✅ 已开始新的对话线程，对话历史已清除。之前的对话记录已保存在侧边栏中。").send()


# 可选：添加命令处理
@cl.action_callback("clear_history")
async def clear_history():
    """清除聊天历史"""
    user = cl.user_session.get("user")
    user_id = get_user_identifier(user)
    
    # 清除当前会话的历史
    cl.user_session.set("chat_history", [])
    
    await cl.Message(
        content="✅ 聊天历史已清除！",
        author="System"
    ).send()

if __name__ == "__main__":
    # 注意：使用 chainlit run main.py 命令启动应用
    # 不需要调用 cl.run()，因为 chainlit 命令会自动处理
    pass

# ===============================
# 🎨 图表处理功能
# ===============================

async def process_response_with_charts(response_text: str, assistant_message: cl.Message):
    
    # 🔍 调试信息
    print(f"\n=== 图表处理调试信息 ===")
    print(f"Response length: {len(response_text)}")
    print(f"Response preview: {response_text[:300]}...")
    
    # 查找所有图表
    chart_pattern = r'\[CHART_START\](.*?)\[CHART_END\]'
    charts = re.findall(chart_pattern, response_text, re.DOTALL)
    
    print(f"Found {len(charts)} charts")
    
    if not charts:
        # 没有图表，尝试从纯文本自动解析生成一个简单柱状图
        print("No charts found, attempting auto chart generation from text")
        auto_cfg = attempt_auto_chart_from_text(response_text)
        if auto_cfg:
            fig = convert_echarts_to_plotly(auto_cfg)
            if fig:
                await cl.Message(content=" ", elements=[cl.Plotly(figure=fig, display="inline")]).send()
                print("Auto-generated chart sent")
        else:
            print("Auto chart generation failed or no suitable data")
        # 正常流式输出原文本
        for ch in response_text:
            await assistant_message.stream_token(ch)
            await asyncio.sleep(0.005)
        return
    
    # 🔧 手动分割处理图表和文本
    chart_matches = list(re.finditer(chart_pattern, response_text, re.DOTALL))
    current_pos = 0
    chart_index = 0
    
    print(f"Found {len(chart_matches)} chart matches")
    
    for match in chart_matches:
        # 处理匹配前的文本
        if match.start() > current_pos:
            text_part = response_text[current_pos:match.start()]
            if text_part.strip():
                print(f"Processing text part: {len(text_part)} chars")
                # 流式输出文本
                for ch in text_part:
                    await assistant_message.stream_token(ch)
                    await asyncio.sleep(0.005)
        
        # 处理图表部分
        chart_data = match.group(1)
        print(f"Processing chart {chart_index + 1}")
        try:
            # 解析图表配置
            chart_config = json.loads(chart_data.strip())
            print(f"Chart config parsed successfully: {list(chart_config.keys())}")
            
            # 转换为Plotly格式 (Chainlit原生支持)
            plotly_fig = convert_echarts_to_plotly(chart_config)
            
            if plotly_fig:
                # 使用有内容的Message避免Raw code占位符
                chart_element = cl.Plotly(figure=plotly_fig, display="inline")
                await cl.Message(content=" ", elements=[chart_element]).send()
                print(f"Chart {chart_index + 1} sent as Plotly")
            else:
                # 如果转换失败，显示错误信息
                error_msg = f"Chart format is not supported\n"
                await assistant_message.stream_token(error_msg)
                print(f"Chart {chart_index + 1} conversion failed")
            
            chart_index += 1
            
        except json.JSONDecodeError as e:
            # 图表解析失败，显示错误信息
            error_msg = f"\nChart JSON decode error: {str(e)}\n"
            await assistant_message.stream_token(error_msg)
            print(f"Chart JSON decode error: {e}")
        except Exception as e:
            # 其他错误
            error_msg = f"\Chart display error: {str(e)}\n"
            await assistant_message.stream_token(error_msg)
            print(f"Chart display error: {e}")
        
        current_pos = match.end()
    
    # 处理最后的文本部分
    if current_pos < len(response_text):
        text_part = response_text[current_pos:]
        if text_part.strip():
            print(f"Processing final text part: {len(text_part)} chars")
            for ch in text_part:
                await assistant_message.stream_token(ch)
                await asyncio.sleep(0.005)
    
    print("=== 图表处理完成 ===\n")

def convert_echarts_to_plotly(chart_config):
    """将简化的图表配置转换为Plotly格式"""
    try:
        import plotly.graph_objects as go
        import plotly.express as px
        
        # 简化的图表格式处理
        chart_type = chart_config.get("type", "")
        title = chart_config.get("title", "")
        data = chart_config.get("data", [])
        
        print(f"Converting chart: type={chart_type}, title={title}, data_count={len(data)}")
        
        # 饼图转换 - 支持简化格式
        if chart_type == "pie":
            labels = chart_config.get("labels", [])
            values = chart_config.get("values", [])

            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                textinfo='label+percent',
                textposition='auto'
            )])
            
            if title:
                fig.update_layout(title_text=title, title_x=0.5)
                
            return fig
        
        # 柱状图转换 - 支持简化格式
        elif chart_type == "bar":
            labels = chart_config.get("labels", [])
            values = chart_config.get("values", [])
            
            if not labels or not values:
                print("Bar chart missing labels or values")
                return None
            
            fig = go.Figure(data=[go.Bar(
                x=labels,
                y=values,
                text=values,
                textposition='auto'
            )])
            
            if title:
                fig.update_layout(title_text=title, title_x=0.5)
                
            return fig
        
        # 线图转换 - 支持简化格式
        elif chart_type == "line":
            x_data = chart_config.get("labels", [])
            y_data = chart_config.get("values", [])
            
            if not x_data or not y_data:
                print("Line chart missing x or y data")
                return None
            
            fig = go.Figure(data=[go.Scatter(
                x=x_data,
                y=y_data,
                mode='lines+markers',
                line=dict(width=2),
                marker=dict(size=6)
            )])
            
            if title:
                fig.update_layout(title_text=title, title_x=0.5)
                
            return fig
        
        # 堆叠柱状图转换 - 多系列数据
        elif chart_type == "stacked_bar":
            labels = chart_config.get("labels", [])
            series = chart_config.get("series", [])
            
            if not labels or not series:
                print("Stacked bar chart missing labels or series")
                return None
            
            fig = go.Figure()
            
            for serie in series:
                name = serie.get("name", "")
                values = serie.get("values", [])
                if len(values) ==0:
                    values = serie.get("data", [])
                fig.add_trace(go.Bar(
                    x=labels,
                    y=values,
                    name=name,
                    text=values,
                    textposition='inside'
                ))
            
            fig.update_layout(
                barmode='stack',
                title_text=title,
                title_x=0.5,
                xaxis_title="类别",
                yaxis_title="数值"
            )
            
            return fig
        
        #分组柱状图转换 - 多系列并排显示
        elif chart_type == "grouped_bar":
            labels = chart_config.get("labels", [])
            series = chart_config.get("series", [])
            
            if not labels or not series:
                print("Grouped bar chart missing labels or series")
                return None
            
            fig = go.Figure()
            
            for serie in series:
                name = serie.get("name", "")
                values = serie.get("values", [])
                if len(values) ==0:
                    values = serie.get("data", [])
                fig.add_trace(go.Bar(
                    x=labels,
                    y=values,
                    name=name,
                    text=values,
                    textposition='outside'
                ))
            
            fig.update_layout(
                barmode='group',
                title_text=title,
                title_x=0.5,
                xaxis_title="类别",
                yaxis_title="数值"
            )
            
            return fig
        
        # 柱状图+折线图组合
        elif chart_type == "bar_line" or chart_type == "bar+line" or chart_type == "line_bar":
            labels = chart_config.get("labels", [])
            bar_data = chart_config.get("bar_data", [])
            line_data = chart_config.get("line_data", [])
            bar_name = chart_config.get("bar_name", "柱状数据")
            line_name = chart_config.get("line_name", "折线数据")
            
            if not labels or not bar_data or not line_data:
                print("Bar+line chart missing required data")
                return None
            
            # 创建双Y轴图表
            fig = go.Figure()
            
            # 添加柱状图
            fig.add_trace(go.Bar(
                x=labels,
                y=bar_data,
                name=bar_name,
                text=bar_data,
                textposition='outside',
                yaxis='y'
            ))
            
            # 添加折线图
            fig.add_trace(go.Scatter(
                x=labels,
                y=line_data,
                mode='lines+markers',
                name=line_name,
                yaxis='y2',
                line=dict(color='red', width=3),
                marker=dict(size=8)
            ))
            
            # 设置双Y轴布局
            fig.update_layout(
                title_text=title,
                title_x=0.5,
                xaxis_title="类别",
                yaxis=dict(title=bar_name, side='left'),
                yaxis2=dict(title=line_name, side='right', overlaying='y'),
                legend=dict(x=0.01, y=0.99)
            )
            
            return fig
        
        # 直方图转换 - 频率分布
        elif chart_type == "histogram":
            values = chart_config.get("values", [])
            bins = chart_config.get("bins", 10)  # 默认10个区间
            
            if not values:
                print("Histogram missing values")
                return None
            
            fig = go.Figure(data=[go.Histogram(
                x=values,
                nbinsx=bins,
                name="频率",
                marker_color='skyblue',
                marker_line=dict(width=1, color='black')
            )])
            
            fig.update_layout(
                title_text=title,
                title_x=0.5,
                xaxis_title="数值区间",
                yaxis_title="频率",
                bargap=0.05
            )
            
            return fig
        
        # 其他类型暂不支持
        else:
            print(f"Unsupported chart type: {chart_type}")
            return None
            
    except ImportError as e:
        print(f"Plotly not installed: {e}")
        return None
    except Exception as e:
        print(f"Error converting chart: {e}")
        return None

def attempt_auto_chart_from_text(text: str) -> Optional[Dict[str, Any]]:
    """从普通文本中提取 类似 '标签: 数值' 结构生成简单柱状图配置。至少需要3个有效数据点。"""
    import re
    pairs = re.findall(r"([\w\u4e00-\u9fa5\-_/（）()]+)[：:]\s*(\d+(?:\.\d+)?)", text)
    # 去重并限制最大数量以防过长
    cleaned = []
    seen = set()
    for label, val in pairs:
        if label in seen:
            continue
        seen.add(label)
        cleaned.append((label.strip(), float(val)))
        if len(cleaned) >= 12:  # 防止过多点影响阅读
            break
    if len(cleaned) < 3:
        return None
    labels = [l for l, _ in cleaned]
    values = [v for _, v in cleaned]
    return {"type": "bar", "title": "自动提取的关键指标", "labels": labels, "values": values}


