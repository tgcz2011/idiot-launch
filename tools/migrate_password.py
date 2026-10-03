import sys
sys.path.insert(0, r'D:\ID\idiot-launch\src')
from core import load_morning_config, _encrypt_morning_password
import json, os

# 加载配置（密码已解密）
cfg = load_morning_config()
print(f'加载配置: grade={cfg.get("grade")}, class={cfg.get("class_number")}')

# 加密密码后重新保存
if cfg.get('password'):
    cfg['password'] = _encrypt_morning_password(cfg['password'])
    path = r'D:\IdiotLaunch\data\morning_config.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f'已加密保存到 {path}')

    # 验证
    with open(path, 'r', encoding='utf-8') as f:
        saved = json.load(f)
    print(f'文件中密码(加密后): {saved.get("password")}')
    print(f'文件中密码以enc:开头: {saved.get("password", "").startswith("enc:")}')
