# AI Agent Coding

基于 FastAPI + qwen3-32b 的智能租房助手 Agent，通过 LLM Tool Calling 实现房源搜索、地标查询和租赁操作。

## 启动服务

```powershell
$env:USER_ID = "<你的工号>"; uvicorn main:app --host 0.0.0.0 --port 8191
```

## e2e测试

```
.\run_e2e.ps1 -UserId "EMP001" -SimAll
http://localhost:8877/ 
```

## Smoke Test

```powershell
# 聊天类（response 应为自然语言字符串）
Invoke-RestMethod -Method POST -Uri http://localhost:8191/api/v1/chat `
  -ContentType "application/json" `
  -Body '{"model_ip":"<模型IP>","session_id":"test-chat","message":"你好"}'

# 房源查询类（response 应为合法 JSON 字符串）
Invoke-RestMethod -Method POST -Uri http://localhost:8191/api/v1/chat `
  -ContentType "application/json" `
  -Body '{"model_ip":"<模型IP>","session_id":"test-search","message":"找海淀区两居室"}'
```
