#!/usr/bin/env python3
"""
tools.py 接口单独调测脚本

根据 session.log 中的错误日志生成，用于：
1. 复现 search_houses 中文参数导致的 ASCII 编码错误
2. 验证 tools.py 各函数对真实 API 的调用正确性

运行前请设置环境变量 USER_ID，例如：
  PowerShell: $env:USER_ID = "test123"; python test_tools_standalone.py
  CMD:        set USER_ID=test123 && python test_tools_standalone.py
  Bash:       USER_ID=test123 python test_tools_standalone.py
"""
import asyncio
import os
import sys

# 必须在导入 tools 之前设置 USER_ID，避免 KeyError
if "USER_ID" not in os.environ:
    os.environ.setdefault("USER_ID", "test-debug-user")

import httpx
from tools import (
    RENTAL_API_BASE,
    search_houses,
    get_house_detail,
    search_landmark,
    search_nearby_landmark,
    get_nearby_amenities,
    execute_action,
    init_houses,
)


async def run_all_tests(client: httpx.AsyncClient) -> dict:
    """执行所有工具函数的调用测试，返回 {test_name: result}"""
    results = {}

    # ── 1. init_houses（可选，用于初始化数据） ──
    print("\n[1/8] init_houses ...")
    try:
        r = await init_houses(client)
        results["init_houses"] = {"ok": "error" not in r, "result": r}
        print(f"       -> {'OK' if 'error' not in r else 'FAIL'}: {str(r)[:120]}...")
    except Exception as e:
        results["init_houses"] = {"ok": False, "error": str(e)}
        print(f"       -> EXCEPTION: {e}")

    # ── 2. search_houses：日志中的失败用例（中文参数） ──
    print("\n[2/8] search_houses (district=大兴, room_type=两居室, max_price=4000) [复现日志错误] ...")
    try:
        r = await search_houses(
            client,
            district="大兴",
            room_type="两居室",
            max_price=4000,
        )
        results["search_houses_chinese"] = {"ok": "error" not in r, "result": r}
        if "error" in r:
            print(f"       -> FAIL: {r['error']}")
        else:
            total = r.get("total", 0)
            items = r.get("items", [])
            print(f"       -> OK: total={total}, items={len(items)}")
    except Exception as e:
        results["search_houses_chinese"] = {"ok": False, "error": str(e)}
        print(f"       -> EXCEPTION: {e}")

    # ── 3. search_houses：英文/数字参数（对照） ──
    print("\n[3/8] search_houses (district=海淀, max_price=5000) ...")
    try:
        r = await search_houses(client, district="海淀", max_price=5000)
        results["search_houses_mixed"] = {"ok": "error" not in r, "result": r}
        if "error" in r:
            print(f"       -> FAIL: {r['error']}")
        else:
            print(f"       -> OK: total={r.get('total',0)}, items={len(r.get('items',[]))}")
    except Exception as e:
        results["search_houses_mixed"] = {"ok": False, "error": str(e)}
        print(f"       -> EXCEPTION: {e}")

    # ── 4. search_landmark（中文关键词） ──
    print("\n[4/8] search_landmark (query=西二旗) ...")
    try:
        r = await search_landmark(client, query="西二旗")
        results["search_landmark"] = {"ok": "error" not in r, "result": r}
        if "error" in r:
            print(f"       -> FAIL: {r['error']}")
        else:
            landmarks = r.get("landmarks", r.get("items", []))
            print(f"       -> OK: landmarks={len(landmarks) if isinstance(landmarks, list) else 'N/A'}")
    except Exception as e:
        results["search_landmark"] = {"ok": False, "error": str(e)}
        print(f"       -> EXCEPTION: {e}")

    # ── 5. get_house_detail ──
    print("\n[5/8] get_house_detail (house_id=HF_1) ...")
    try:
        r = await get_house_detail(client, house_id="HF_1")
        results["get_house_detail"] = {"ok": "error" not in r, "result": r}
        if "error" in r:
            print(f"       -> FAIL: {r['error']}")
        else:
            print(f"       -> OK: id={r.get('id','?')}")
    except Exception as e:
        results["get_house_detail"] = {"ok": False, "error": str(e)}
        print(f"       -> EXCEPTION: {e}")

    # ── 6. search_nearby_landmark（需先有 landmark_id） ──
    landmark_id = None
    if results.get("search_landmark", {}).get("ok") and "result" in results["search_landmark"]:
        lm_res = results["search_landmark"]["result"]
        items = lm_res.get("landmarks", lm_res.get("items", []))
        if items and isinstance(items, list) and len(items) > 0:
            landmark_id = items[0].get("id") if isinstance(items[0], dict) else None

    print("\n[6/8] search_nearby_landmark ...")
    if landmark_id:
        try:
            r = await search_nearby_landmark(client, landmark_id=landmark_id, max_distance=2000)
            results["search_nearby_landmark"] = {"ok": "error" not in r, "result": r}
            if "error" in r:
                print(f"       -> FAIL: {r['error']}")
            else:
                items = r.get("items", [])
                print(f"       -> OK: items={len(items)}")
        except Exception as e:
            results["search_nearby_landmark"] = {"ok": False, "error": str(e)}
            print(f"       -> EXCEPTION: {e}")
    else:
        print("       -> SKIP (无 landmark_id，先执行 search_landmark)")
        results["search_nearby_landmark"] = {"ok": None, "skip": "no landmark_id"}

    # ── 7. get_nearby_amenities ──
    print("\n[7/8] get_nearby_amenities (house_id=HF_1) ...")
    try:
        r = await get_nearby_amenities(client, house_id="HF_1")
        results["get_nearby_amenities"] = {"ok": "error" not in r, "result": r}
        if "error" in r:
            print(f"       -> FAIL: {r['error']}")
        else:
            amenities = r.get("amenities", r.get("items", []))
            print(f"       -> OK: amenities={len(amenities) if isinstance(amenities, list) else 'N/A'}")
    except Exception as e:
        results["get_nearby_amenities"] = {"ok": False, "error": str(e)}
        print(f"       -> EXCEPTION: {e}")

    # ── 8. execute_action（仅验证调用格式，不实际执行 rent/terminate/offline 以免影响数据） ──
    print("\n[8/8] execute_action - 仅测试 invalid action 返回 error dict ...")
    try:
        r = await execute_action(client, action="invalid_action", house_id="HF_1", listing_platform="安居客")
        # 无效 action 应返回 error dict，不发 HTTP 请求
        ok = "error" in r and "invalid_action" in r.get("error", "")
        results["execute_action_invalid"] = {"ok": ok, "result": r}
        print(f"       -> {'OK' if ok else 'FAIL'}: {r}")
    except Exception as e:
        results["execute_action_invalid"] = {"ok": False, "error": str(e)}
        print(f"       -> EXCEPTION: {e}")

    return results


def main():
    print("=" * 60)
    print("tools.py 接口单独调测")
    print("=" * 60)
    print(f"RENTAL_API_BASE: {RENTAL_API_BASE}")
    print(f"USER_ID:         {os.environ.get('USER_ID', '?')}")
    print("=" * 60)

    async def _main():
        async with httpx.AsyncClient(
            base_url=RENTAL_API_BASE,
            timeout=30.0,
            trust_env=False,
        ) as client:
            results = await run_all_tests(client)

        # 汇总
        ok_count = sum(1 for v in results.values() if v.get("ok") is True)
        fail_count = sum(1 for v in results.values() if v.get("ok") is False)
        skip_count = sum(1 for v in results.values() if v.get("ok") is None)

        print("\n" + "=" * 60)
        print(f"汇总: OK={ok_count}, FAIL={fail_count}, SKIP={skip_count}")
        print("=" * 60)

        if fail_count > 0:
            sys.exit(1)
        sys.exit(0)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
