import random
import string


def generate_short_code(length: int = 6) -> str:
    """
    Генерация случайного короткого кода
    
    Args:
        length: длина кода (по умолчанию 6)
        
    Returns:
        str: случайный буквенно-цифровой код
    """
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=length))


def is_valid_short_code(code: str) -> bool:
    """
    Проверка валидности короткого кода
    
    Args:
        code: код для проверки
        
    Returns:
        bool: True если код валиден
    """
    if not code:
        return False
    
    if len(code) < 3 or len(code) > 20:
        return False
    
    # Разрешены буквы, цифры, дефисы и подчеркивания
    return code.replace('-', '').replace('_', '').isalnum()
