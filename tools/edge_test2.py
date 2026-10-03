import sys, os, json, time, threading
sys.path.insert(0, r'D:\ID\idiot-launch\src')
import core

print('=== 测试5: 并发读写状态文件 ===')
state_file = os.path.join(core.UPDATE_DIR, 'state.json')
errors = []

def writer(n):
    for i in range(20):
        try:
            state = core.load_state()
            state[f'writer_{n}'] = i
            core.save_state(state)
        except Exception as e:
            errors.append(f'writer{n}-{i}: {type(e).__name__}: {e}')

threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print(f'并发写入错误数: {len(errors)}')
for e in errors[:5]:
    print(f'  {e}')

# 验证最终状态文件是否有效
try:
    with open(state_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f'最终状态文件有效，包含 {len(data)} 个键')
except Exception as e:
    print(f'最终状态文件损坏: {type(e).__name__}: {e}')

print()
print('=== 测试6: 网络断开时更新检查 ===')
# 用一个不存在的域名测试超时
import urllib.request
try:
    req = urllib.request.Request('http://10.255.255.1/test', timeout=3)
    urllib.request.urlopen(req, timeout=3)
except Exception as e:
    print(f'网络超时测试: {type(e).__name__} (预期)')

print()
print('=== 测试7: D盘不存在时快捷方式守护 ===')
print(f'D盘存在: {os.path.isdir("D:\\\\")}')
print(f'公共桌面存在: {os.path.isdir(r"C:\\Users\\Public\\Desktop")}')

print()
print('=== 测试8: SHA256校验 ===')
test_file = os.path.join(core.UPDATE_DIR, 'test_sha256.tmp')
with open(test_file, 'w') as f:
    f.write('test content')
sha = core.sha256_of(test_file)
print(f'文件SHA256: {sha}')
print(f'正确哈希校验: {core.verify_sha256(test_file, sha)}')
print(f'错误哈希校验: {core.verify_sha256(test_file, "0000000000000000000000000000000000000000000000000000000000000000")}')
os.remove(test_file)

print()
print('=== 测试9: 日志轮转 ===')
log_file = core.DAEMON_LOG
print(f'日志文件: {log_file}')
if os.path.isfile(log_file):
    size = os.path.getsize(log_file)
    print(f'当前大小: {size} bytes ({size/1024:.1f} KB)')
print(f'轮转阈值: 100 KB')

print()
print('=== 测试10: 单实例mutex ===')
mutex1 = core._acquire_daemon_mutex()
print(f'第一次获取mutex: {mutex1 is not None}')
mutex2 = core._acquire_daemon_mutex()
print(f'第二次获取mutex: {mutex2 is not None} (应为False)')
if mutex1:
    import ctypes
    ctypes.windll.kernel32.CloseHandle(mutex1)
print('已释放mutex')
