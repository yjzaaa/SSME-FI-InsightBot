import os
import boto3
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BedrockChatClient:
    def __init__(self):
        # 检查AWS凭证
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        
        if not access_key or not secret_key:
            logger.warning("AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env file")
            self.bedrock_client = None
            return
        
        try:
            # 使用Session方式创建客户端，跳过SSL验证
            session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region
            )
            
            # 创建Bedrock runtime客户端，禁用SSL验证
            self.bedrock_client = session.client('bedrock-runtime', verify=False)
            logger.info("AWS Bedrock client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize AWS Bedrock client: {e}")
            self.bedrock_client = None
        
        # 对于requests库，设置环境变量忽略SSL
        os.environ['PYTHONHTTPSVERIFY'] = '0'
        
    async def stream_chat(self, messages, model_id="arn:aws:bedrock:us-east-1:014498637974:inference-profile/us.deepseek.r1-v1:0"):
        if not self.bedrock_client:
            logger.error("AWS Bedrock client not available")
            yield "❌ AWS Bedrock服务未配置。请检查AWS凭证配置。\n\n请在.env文件中设置：\n- AWS_ACCESS_KEY_ID\n- AWS_SECRET_ACCESS_KEY\n- AWS_DEFAULT_REGION"
            return
            
        try:
            # 转换消息格式为Bedrock converse API格式
            conversation = []
            for msg in messages:
                conversation.append({
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}]
                })
            
            # 调用Bedrock converse API
            response = self.bedrock_client.converse(
                modelId=model_id,
                messages=conversation,
                inferenceConfig={"maxTokens": 2000}
            )
            
            # 提取响应文本
            response_text = response["output"]["message"]["content"][0]["text"]
            yield response_text
                        
        except Exception as e:
            logger.error(f"Bedrock API error: {e}")
            yield f"❌ AI服务调用失败: {str(e)}\n\n请检查：\n1. AWS凭证是否正确\n2. 网络连接是否正常\n3. Bedrock服务是否可用"
