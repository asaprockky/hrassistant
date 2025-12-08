from enum import Enum

class Role(Str, Enum):
    USER = "user"
    ADMIN = "admin"
    
    