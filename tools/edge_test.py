import sys, os, json
sys.path.insert(0, r'D:\ID\idiot-launch\src')
import core

print('=== 测试1: 状态文件损坏 ===')
state_file = os.path.join(core.UPDATE_DIR, 'state.json')
print(f'状态文件: {state_file}')
print(f'存在: {os.path.isfile(state_file)}')

if os.path.isfile(state_file):
    with open(state_file, 'r', encoding='utf-8') as f:
        original = f.read()
    with open(state_file, 'w', encoding='utf-8') as f:
        f.write('{invalid json!!!')
    try:
        state = core.load_state()
        print(f'损坏文件加载结果: {type(state).__name__}, 内容: {str(state)[:100]}')
    except Exception as e:
        print(f'加载异常: {type(e).__name__}: {e}')
    with open(state_file, 'w', encoding='utf-8') as f:
        f.write(original)
    print('已恢复原文件')

print()
print('=== 测试2: 版本比较边界 ===')
test_cases = [
    ('3.0.0.0-beta18', '3.0.0.0-beta19'),
    ('3.0.0.0-beta19', '3.0.0.0'),
    ('3.0.0.0', '3.0.0.1'),
    ('2.9.9.9', '3.0.0.0'),
    ('3.0.0.0-beta1', '3.0.0.0-beta10'),
    ('3.0.0.0-beta10', '3.0.0.0-beta9'),
    ('3.0.0.0-beta19', '3.0.0.0-beta19'),
]
for v1, v2 in test_cases:
    result = core.compare_versions(v1, v2)
    symbol = '<' if result < 0 else '>' if result > 0 else '='
    print(f'  {v1} vs {v2}: {result} ({symbol})')

print()
print('=== 测试3: 空闲检测 ===')
idle = core.get_idle_seconds()
print(f'当前空闲秒数: {idle}')

print()
print('=== 测试4: 常量检查 ===')
print(f'CHECK_INTERVAL: {core.CHECK_INTERVAL} ({core.CHECK_INTERVAL/60}分钟)')
print(f'IDLE_THRESHOLD: {core.IDLE_THRESHOLD} ({core.IDLE_THRESHOLD/60}分钟)')
print(f'LAUNCHER_INSTALL_EXE: {core.LAUNCHER_INSTALL_EXE}')
print(f'UPDATE_DIR: {core.UPDATE_DIR}')
print(f'LAUNCHER_MIN_SIZE: {core.LAUNCHER_MIN_SIZE}')
