import base64

with open('case', 'r') as f:
    data = base64.b64decode(f.read().strip())
with open('case.rar', 'wb') as f:
    f.write(data)
print('已生成 case.rar，大小:', len(data), '字节')
