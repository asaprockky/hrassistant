from passlib.context import CryptContext

# Initialize the hashing system (same as in your main.py)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 1. The password you want
password_to_hash = "1234"

# 2. Generate the hash
hashed_password = pwd_context.hash(password_to_hash)

# 3. Print it out so you can copy it
print(f"Password: {password_to_hash}")
print(f"Hash to put in DB: {hashed_password}")