# Welcome to Chainlit! 🚀🤖

Hi there, Developer! 👋 We're excited to have you on board. Chainlit is a powerful tool designed to help you prototype, debug and share applications built on top of LLMs.

## Useful Links 🔗

- **Documentation:** Get started with our comprehensive [Chainlit Documentation](https://docs.chainlit.io) 📚
- **Discord Community:** Join our friendly [Chainlit Discord](https://discord.gg/k73SQ3FyUh) to ask questions, share your projects, and connect with other developers! 💬

We can't wait to see what you create with Chainlit! Happy coding! 💻😊

## 头认证方式
头认证是通过请求头进行用户验证的简单方式，通常用于将认证委托给反向代理。

`header_auth_callback` 函数会接收请求头作为参数。如果用户认证成功应返回User对象，否则返回None。回调函数（由用户定义）需负责管理认证逻辑。

示例代码：

```python
from typing import Optional
import chainlit as cl

@cl.header_auth_callback
def header_auth_callback(headers: Dict) -> Optional[cl.User]:
    # 验证头部的令牌签名（例如JWT令牌）
    # 或检查值是否与数据库中的记录匹配
    if headers.get("test-header") == "test-value":
        return cl.User(identifier="admin", metadata={"role": "admin", "provider": "header"})
    else:
        return None
```
使用此代码时，除非在请求头中设置test-header为test-value，否则将无法访问应用。

## Welcome screen

To modify the welcome screen, edit the `chainlit.md` file at the root of your project. If you do not want a welcome screen, just leave this file empty.
