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
