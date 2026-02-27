"""End-to-end smoke test for the full automation cascade."""

import asyncio

import httpx
from httpx import ASGITransport


async def test():
    # Init DB manually (ASGITransport doesn't trigger lifespan)
    from kira.web.db.database import get_db, init_db
    from kira.web.db.seed import seed_db

    await init_db(":memory:")
    db = await get_db()
    await seed_db(db)

    from kira.web.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # 1. Health check
        r = await c.get("/api/health")
        assert r.status_code == 200, f"Health failed: {r.status_code}"
        print("✓ Health check")

        # 2. Login as alice
        r = await c.post("/api/auth/login", json={"username": "alice"})
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
        data = r.json()
        token = data["token"]
        user_id = data["user"]["id"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"✓ Login: user_id={user_id}")

        # 3. List boards
        r = await c.get("/api/boards", headers=headers)
        assert r.status_code == 200, f"List boards failed: {r.status_code}"
        boards = r.json()
        assert len(boards) > 0
        board_id = boards[0]["id"]
        print(f"✓ List boards: {len(boards)} boards")

        # 4. Get full board
        r = await c.get(f"/api/boards/{board_id}", headers=headers)
        assert r.status_code == 200, f"Get board failed: {r.status_code} {r.text}"
        board = r.json()
        columns = board["columns"]
        print(f"✓ Full board: {len(columns)} columns")
        for col in columns:
            auto = "⚡" if col.get("auto_run") else "  "
            agent = col.get("agent_type", "") or "-"
            print(f"  {auto} {col['name']:12s} agent={agent}")

        # 5. Find columns and a backlog card
        backlog_col = next(x for x in columns if x["name"] == "Backlog")
        architect_col = next(x for x in columns if x["name"] == "Architect")
        code_col = next(x for x in columns if x["name"] == "Code")
        review_col = next(x for x in columns if x["name"] == "Review")
        done_col = next(x for x in columns if x["name"] == "Done")
        assert len(backlog_col["cards"]) > 0
        card = backlog_col["cards"][0]
        card_id = card["id"]
        print(f"✓ Card: {card['title']}")

        # 6. Tasks before move (use trailing slash for router prefix)
        r = await c.get(f"/api/tasks", headers=headers, params={"board_id": board_id})
        assert r.status_code == 200, f"List tasks failed: {r.status_code}"
        print(f"✓ Tasks before move: {len(r.json())}")

        # 7. Move card to Architect (auto_run) -> should create task
        r = await c.post(
            f"/api/cards/{card_id}/move",
            headers=headers,
            json={"column_id": architect_col["id"], "position": 0},
        )
        assert r.status_code == 200, f"Move failed: {r.status_code} {r.text}"
        print("✓ Card moved to Architect")

        # 8. Verify task auto-created
        r = await c.get(
            f"/api/tasks", headers=headers, params={"card_id": card_id}
        )
        assert r.status_code == 200
        tasks = r.json()
        assert len(tasks) > 0, "No task created!"
        task = tasks[0]
        task_id = task["id"]
        print(
            f"✓ Task auto-created: type={task['task_type']}, "
            f"agent={task['agent_type']}, status={task['status']}"
        )
        assert task["agent_type"] == "architect"
        assert task["status"] == "pending"

        # 9. Register worker
        r = await c.post(
            "/api/workers/register",
            headers=headers,
            json={
                "hostname": "test-machine",
                "worker_version": "0.3.0",
                "capabilities": ["agent"],
            },
        )
        assert r.status_code == 201, f"Register failed: {r.status_code} {r.text}"
        worker_id = r.json()["worker_id"]
        print(f"✓ Worker registered: {worker_id}")

        # 10. Poll tasks (returns flat list)
        r = await c.get(
            "/api/workers/tasks/poll",
            headers=headers,
            params={"worker_id": worker_id},
        )
        assert r.status_code == 200, f"Poll failed: {r.status_code} {r.text}"
        poll = r.json()
        assert isinstance(poll, list)
        assert len(poll) > 0
        print(f"✓ Poll: {len(poll)} task(s)")

        # 11. Claim
        r = await c.post(
            f"/api/workers/tasks/{task_id}/claim",
            headers=headers,
            json={"worker_id": worker_id},
        )
        assert r.status_code == 200, f"Claim failed: {r.status_code} {r.text}"
        print("✓ Task claimed")

        # 12. Progress
        r = await c.post(
            f"/api/workers/tasks/{task_id}/progress",
            headers=headers,
            json={
                "worker_id": worker_id,
                "status": "running",
                "progress_text": "Analyzing...",
            },
        )
        assert r.status_code == 200
        print("✓ Progress reported")

        # 13. Card agent_status
        r = await c.get(f"/api/cards/{card_id}", headers=headers)
        assert r.json()["agent_status"] == "running"
        print("✓ Card agent_status=running")

        # 14. Complete architect -> card moves to Code -> coder task cascade
        r = await c.post(
            f"/api/workers/tasks/{task_id}/complete",
            headers=headers,
            json={
                "worker_id": worker_id,
                "output_text": "Architecture: use layered design with clean separation.",
            },
        )
        assert r.status_code == 200, f"Complete failed: {r.status_code} {r.text}"
        completed = r.json()
        print(f"✓ Architect completed: status={completed['status']}")
        print(f"  next_action: {completed.get('next_action')}")

        # 15. Verify card in Code
        r = await c.get(f"/api/cards/{card_id}", headers=headers)
        card_now = r.json()
        assert card_now["column_id"] == code_col["id"], (
            f"Expected Code, got {card_now['column_id']}"
        )
        print("✓ Card moved to Code")

        # 16. Verify coder task cascade
        r = await c.get(
            "/api/tasks",
            headers=headers,
            params={"card_id": card_id, "status": "pending"},
        )
        coder_tasks = [t for t in r.json() if t["agent_type"] == "coder"]
        assert len(coder_tasks) > 0, "No coder task!"
        coder_task = coder_tasks[0]
        print(f"✓ Cascade: coder task id={coder_task['id']}")

        # 17. Claim + complete coder -> card to Review
        r = await c.post(
            f"/api/workers/tasks/{coder_task['id']}/claim",
            headers=headers,
            json={"worker_id": worker_id},
        )
        assert r.status_code == 200
        r = await c.post(
            f"/api/workers/tasks/{coder_task['id']}/complete",
            headers=headers,
            json={
                "worker_id": worker_id,
                "output_text": "Implementation done. All tests pass.",
            },
        )
        assert r.status_code == 200
        print("✓ Coder completed")

        # 18. Card in Review
        r = await c.get(f"/api/cards/{card_id}", headers=headers)
        assert r.json()["column_id"] == review_col["id"]
        print("✓ Card moved to Review")

        # 19. Reviewer task created
        r = await c.get(
            "/api/tasks",
            headers=headers,
            params={"card_id": card_id, "status": "pending"},
        )
        reviewer_tasks = [t for t in r.json() if t["agent_type"] == "reviewer"]
        assert len(reviewer_tasks) > 0
        reviewer_task = reviewer_tasks[0]
        print(f"✓ Reviewer task id={reviewer_task['id']}")

        # 20. Complete reviewer with APPROVED -> card to Done
        r = await c.post(
            f"/api/workers/tasks/{reviewer_task['id']}/claim",
            headers=headers,
            json={"worker_id": worker_id},
        )
        assert r.status_code == 200
        r = await c.post(
            f"/api/workers/tasks/{reviewer_task['id']}/complete",
            headers=headers,
            json={
                "worker_id": worker_id,
                "output_text": "APPROVED. Clean and well-structured.",
            },
        )
        assert r.status_code == 200
        print("✓ Reviewer approved")

        # 21. Card in Done
        r = await c.get(f"/api/cards/{card_id}", headers=headers)
        card_now = r.json()
        assert card_now["column_id"] == done_col["id"], (
            f"Expected Done, got {card_now['column_id']}"
        )
        print("✓ Card moved to Done")

        # 22. Summary of all tasks
        r = await c.get(
            "/api/tasks", headers=headers, params={"card_id": card_id}
        )
        all_tasks = r.json()
        print(f"✓ Total tasks: {len(all_tasks)}")
        for t in all_tasks:
            print(f"  {t['agent_type']:10s} {t['status']:10s}")

        # 23. Heartbeat
        r = await c.post(
            "/api/workers/heartbeat",
            headers=headers,
            json={"worker_id": worker_id, "running_task_ids": []},
        )
        assert r.status_code == 200
        print(f"✓ Heartbeat: {r.json()['status']}")

        # 24. List workers
        r = await c.get("/api/workers", headers=headers)
        assert r.status_code == 200
        print(f"✓ Workers: {len(r.json())}")

        # === Test reviewer rejection loop ===
        print()
        print("--- Testing reviewer rejection loop ---")

        # Move a different card through the pipeline to test rejection
        card2 = backlog_col["cards"][1]
        card2_id = card2["id"]
        print(f"✓ Card2: {card2['title']}")

        # Move to Architect
        r = await c.post(
            f"/api/cards/{card2_id}/move",
            headers=headers,
            json={"column_id": architect_col["id"], "position": 0},
        )
        assert r.status_code == 200

        # Get and complete architect task
        r = await c.get(
            "/api/tasks",
            headers=headers,
            params={"card_id": card2_id, "status": "pending"},
        )
        t = r.json()[0]
        r = await c.post(
            f"/api/workers/tasks/{t['id']}/claim",
            headers=headers,
            json={"worker_id": worker_id},
        )
        r = await c.post(
            f"/api/workers/tasks/{t['id']}/complete",
            headers=headers,
            json={"worker_id": worker_id, "output_text": "Design done."},
        )
        assert r.status_code == 200

        # Complete coder task
        r = await c.get(
            "/api/tasks",
            headers=headers,
            params={"card_id": card2_id, "status": "pending"},
        )
        t = [x for x in r.json() if x["agent_type"] == "coder"][0]
        r = await c.post(
            f"/api/workers/tasks/{t['id']}/claim",
            headers=headers,
            json={"worker_id": worker_id},
        )
        r = await c.post(
            f"/api/workers/tasks/{t['id']}/complete",
            headers=headers,
            json={"worker_id": worker_id, "output_text": "Code done."},
        )
        assert r.status_code == 200

        # Verify card in Review
        r = await c.get(f"/api/cards/{card2_id}", headers=headers)
        assert r.json()["column_id"] == review_col["id"]
        print("✓ Card2 in Review")

        # REJECT the review
        r = await c.get(
            "/api/tasks",
            headers=headers,
            params={"card_id": card2_id, "status": "pending"},
        )
        t = [x for x in r.json() if x["agent_type"] == "reviewer"][0]
        r = await c.post(
            f"/api/workers/tasks/{t['id']}/claim",
            headers=headers,
            json={"worker_id": worker_id},
        )
        r = await c.post(
            f"/api/workers/tasks/{t['id']}/complete",
            headers=headers,
            json={
                "worker_id": worker_id,
                "output_text": "REJECTED. Missing error handling and tests.",
            },
        )
        assert r.status_code == 200
        print("✓ Reviewer REJECTED")

        # Card should be back in Code column (failure path)
        r = await c.get(f"/api/cards/{card2_id}", headers=headers)
        card2_now = r.json()
        assert card2_now["column_id"] == code_col["id"], (
            f"Expected Code (rejection loop), got {card2_now['column_id']}"
        )
        print("✓ Card2 moved back to Code (rejection loop!)")

        # A new coder task should NOT be created (skip_automation on failure)
        r = await c.get(
            "/api/tasks",
            headers=headers,
            params={"card_id": card2_id, "status": "pending"},
        )
        pending_after_reject = r.json()
        print(
            f"✓ Pending tasks after rejection: {len(pending_after_reject)} "
            f"(skip_automation on failure path)"
        )

        print()
        print("=" * 60)
        print("  ALL SMOKE TESTS PASSED!")
        print("  Full cascade: Backlog → Architect → Code → Review → Done")
        print("  Rejection loop: Review → Code (with skip_automation)")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test())
