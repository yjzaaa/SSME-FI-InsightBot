import json,datetime
import logging
import os

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
def save_session_history_to_json(thread_id, session_history):
    """按thread_id更新会话历史到JSON文件，保留其他thread数据"""
    try:
        logger.info(f"Saving session history for thread {thread_id}...")
        # 确保目录存在
        os.makedirs('json', exist_ok=True)
        filename = os.path.join('json', "session_history.json")
        
        # 读取现有数据
        existing_data = {}
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        
        # 更新指定thread_id的数据
        existing_data[str(thread_id)] = session_history
        
        # 写入更新后的数据
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)
            
        logger.info(f"Updated session history for thread {thread_id} in {filename}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
    except Exception as e:
        logger.error(f"保存会话历史失败: {e}")
