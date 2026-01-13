 
import pyodbc
import logging
import requests
import uuid
logger = logging.getLogger(__name__)

DB_CONNECTION_STRING = "Driver={ODBC Driver 17 for SQL Server};Server=shai438a;Database=SmartMES;Trusted_Connection=yes;TrustServerCertificate=yes;Connection Timeout=500;"

class login:
    def __init__(self):
        pass
    @staticmethod
    def verify_user(username, password):
        """使用远程api验证用户
           示例 请求网址
            https://smesapi.ssme.net.cn/api/user/login
            请求方法
            POST
            状态代码
            200 OK
            远程地址
            139.24.205.137:443
            引荐来源网址政策
            strict-origin-when-cross-origin

            {"userName":"z004zjsw","passWord":"123456","UUID":"7165791e-2e83-4b56-8533-5292b027708d"}
            Response status code: 200
            2025-09-09 16:06:12 - Response content: {"status":true,"code":"310","message":"登陆成功","data":{"token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI3ODY4IiwiaWF0IjoiMTc1NzQwNTE5MiIsIm5iZiI6IjE3NTc0MDUxOTIiLCJleHAiOiIxNzU3NDU5MTkyIiwiaXNzIjoidm9sLmNvcmUub3duZXIiLCJhdWQiOiJ2b2wuY29yZSJ9.2FFxotCO5LmDTyMGU4LOCXGLOAI4u5uvP3FfeKB1DT0","userId":7868,"userName":"Yin, Jia Zhen (ext)","img":null,"address":null,"roleName":["Admin","XP","超级管理员","XP_Admin"],"deptName":null,"user_Id":7868}}
        """
        logger.info(f"Verifying user {username}...")
        try:
            response = requests.post("https://smesapi.ssme.net.cn/api/user/login", json={
                "userName": username,
                "passWord": password,
                "UUID": str(uuid.uuid4())
            })
            # logger.info(f"Response status code: {response.status_code}")
            

            if response.status_code == 200:
                data = response.json()
                # logger.info(f"Response content: {data}")
                return data
            return False
        except Exception as e:
            logger.error(f"Error verifying user {username}: {e}")
            return False

    
    @staticmethod
    def get_user_id(username):
        """获取用户ID"""
        try:
            with pyodbc.connect(DB_CONNECTION_STRING) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT UserID FROM [SmartMES].[dbo].[Sys_User] WHERE UserName = ?", (username,))
                row = cursor.fetchone()
                if row:
                    return row[0]
                else:
                    return None
        except Exception as e:
            logger.error(f"Error fetching user ID for {username}: {e}")
            return None
    @staticmethod
    def get_user_info(user_id):
        """获取用户信息"""
        try:
            with pyodbc.connect(DB_CONNECTION_STRING) as conn:
                cursor = conn.cursor()
                
                # 获取基础用户信息
                cursor.execute(
                    "SELECT [User_Id],[Gid],[UserName],[UserTrueName],[DeptName],[Email],[Mobile] FROM [SmartMES].[dbo].[Sys_User] WHERE USERNAME = ?", 
                    (user_id,))
                user_row = cursor.fetchone()
                if not user_row:
                    return None

                user_data = {
                    "user_id": user_row[0],
                    "gid": user_row[1],
                    "username": user_row[2],
                    "true_name": user_row[3],
                    "dept_name": user_row[4],
                    "email": user_row[5],
                    "mobile": user_row[6]
                }

                # 获取角色ID列表
                cursor.execute(
                    "SELECT RoleId FROM [SmartMES].[dbo].[Sys_UserRole] WHERE UserId = ? and Enable ='1'",
                    (user_row[0],))  
                role_ids = [str(row[0]) for row in cursor.fetchall()]

                # 获取角色名称
                if role_ids:
                    cursor.execute(
                        f"SELECT RoleName FROM [SmartMES].[dbo].[Sys_Role] WHERE Role_Id IN ({','.join(['?']*len(role_ids))})",
                        role_ids)
                    user_data["role_names"] = [row[0] for row in cursor.fetchall()]
                else:
                    user_data["role_names"] = []

                return user_data

        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None
