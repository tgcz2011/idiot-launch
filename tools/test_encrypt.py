import sys
sys.path.insert(0, r'D:\ID\idiot-launch\src')
from core import _encrypt_morning_password, _decrypt_morning_password, load_morning_config

pwd = 'admin11'
enc = _encrypt_morning_password(pwd)
dec = _decrypt_morning_password(enc)
print(f'原文: {pwd}')
print(f'加密: {enc}')
print(f'解密: {dec}')
print(f'一致: {pwd == dec}')
print(f'明文兼容: {_decrypt_morning_password("admin11") == "admin11"}')

cfg = load_morning_config()
print(f'当前配置密码(解密后): {cfg.get("password")}')
print(f'当前配置年级: {cfg.get("grade")}')
print(f'当前配置班级: {cfg.get("class_number")}')
