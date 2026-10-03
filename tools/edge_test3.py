import sys, os, json, threading
sys.path.insert(0, r'D:\ID\idiot-launch\src')
import core

print('=== 测试5: 并发读写状态文件 ===')
state_file = os.path.join(core.UPDATE_DIR, 'state.json')
errors = []

def writer(n):
    for i in range(10):
        try:
            state = core.load_state()
            state[f'writer_{n}'] = i
            core.save_state(state)
        except Exception as e:
            errors.append(f'writer{n}-{i}: {type(e).__name__}')

threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print(f'并发写入错误数: {len(errors)}')
for e in errors[:3]:
    print(f'  {e}')

try:
    with open(state_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f'最终状态文件有效，包含 {len(data)} 个键')
except Exception as e:
    print(f'最终状态文件损坏: {type(e).__name__}: {e}')

print()
print('=== 测试6: SHA256校验 ===')
test_file = os.path.join(core.UPDATE_DIR, 'test_sha256.tmp')
with open(test_file, 'w') as f:
    f.write('test content')
sha = core.sha256_of(test_file)
print(f'正确哈希校验: {core.verify_sha256(test_file, sha)}')
print(f'错误哈希校验: {core.verify_sha256(test_file, "0"*64)}')
os.remove(test_file)

print()
print('=== 测试7: 单实例mutex ===')
mutex1 = core._acquire_daemon_mutex()
print(f'第一次获取mutex: {mutex1 is not None}')
mutex2 = core._acquire_daemon_mutex()
print(f'第二次获取mutex: {mutex2 is not None} (应为False)')
if mutex1:
    import ctypes
    ctypes.windll.kernel32.CloseHandle(mutex1)
print('已释放mutex')

print()
print('=== 测试8: 快捷方式目标 ===')
target = core.LAUNCHER_INSTALL_EXE if os.path.isfile(core.LAUNCHER_INSTALL_EXE) else sys.executable
print(f'快捷方式目标: {target}')
print(f'目标存在: {os.path.isfile(target)}')

print()
print('=== 测试9: 日志文件 ===')
log_file = core.DAEMON_LOG
print(f'日志文件: {log_file}')
print(f'存在: {os.path.isfile(log_file)}')
if os.path.isfile(log_file):
    print(f'大小: {os.path.getsize(log_file)} bytes')

print()
print('=== 测试10: 早读配置 ===')
cfg = core.load_morning_config()
print(f'早读配置: {cfg}')
print(f'已登录: {core.is_morning_logged_in()}')
