"""Mock 租房 API FastAPI 应用 — 提供 15 个租房 API 端点的 Mock/透传服务"""
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from config import SimulatorConfig, MockRule

# TODO: Story 5.2 实现 create_mock_rental_app()
