"""Model Proxy FastAPI 应用 — 转发 LLM 请求并截取 token 统计"""
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from config import SimulatorConfig, TokenCounter

# TODO: Story 5.2 实现 create_model_proxy_app()
