import os
import subprocess
import time
import pytest
import httpx
import signal
from tests.helpers.docker_env import is_docker_available, has_required_images, cleanup_factory_containers
from tests.helpers.http_wait import wait_for_200

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not is_docker_available(), reason="Docker not available"),
    pytest.mark.skipif(not has_required_images(), reason="Required images missing")
]

@pytest.fixture(scope="module")
def factory_server():
    # Cleanup before start
    cleanup_factory_containers()
    
    # Start Factory via subprocess
    # We need to make sure we are in the right directory or use PYTHONPATH
    env = os.environ.copy()
    # Add src to PYTHONPATH so 'factory' can be imported
    env["PYTHONPATH"] = os.path.join(os.getcwd(), "factory", "src")
    env["DPP_FACTORY_TESTING"] = "false" # Real run
    
    cmd = [
        "py", "-3.14", "-m", "uvicorn", "dpp_platform_factory.api.api:app",
        "--host", "127.0.0.1",
        "--port", "8008"
    ]
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    )
    
    # Wait for factory to be healthy
    if not wait_for_200("http://127.0.0.1:8008/health", timeout=30):
        stdout, stderr = proc.communicate(timeout=1)
        pytest.fail(f"Factory failed to start.\nSTDOUT: {stdout.decode()}\nSTDERR: {stderr.decode()}")
    
    yield "http://127.0.0.1:8008"
    
    # Shutdown
    if os.name == "nt":
        os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
    else:
        proc.terminate()
        
    proc.wait(timeout=30)
    
    # Final cleanup
    cleanup_factory_containers()

def test_full_factory_lifecycle_e2e(factory_server):
    url = factory_server
    timeout = httpx.Timeout(60.0)
    
    with httpx.Client(base_url=url, timeout=timeout) as client:
        # 1. Check federation
        resp = client.get("/federation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolver"]["status"] == "RUNNING"
        
        # 2. Spawn additional platform
        resp = client.post("/platforms", json={
            "stack": "fastapi-mongo",
            "issuer_id": "e2e-issuer",
            "subject_types": ["e2e-type"]
        })
        assert resp.status_code == 200
        platform_id = resp.json()["platform_id"]
        platform_url = resp.json()["external_url"]
        
        # 3. Verify new platform is reachable
        assert wait_for_200(f"{platform_url}/health", timeout=30)
        
        # 4. Pause
        resp = client.post(f"/platforms/{platform_id}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "PAUSED"
        
        # 5. Resume
        resp = client.post(f"/platforms/{platform_id}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "RUNNING"
        assert wait_for_200(f"{platform_url}/health", timeout=30)
        
        # 6. Seed schemas
        resp = client.post("/resolver/seed-schemas")
        assert resp.status_code == 200
        assert "battery-1.0.json" in resp.json()["loaded"]
        
        # 7. Reset
        resp = client.post(f"/platforms/{platform_id}/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "RUNNING"
        
        # 8. Delete
        resp = client.delete(f"/platforms/{platform_id}")
        assert resp.status_code == 200
        
        # 9. Verify gone
        resp = client.get(f"/platforms/{platform_id}")
        assert resp.status_code == 404

def test_orphan_handling_e2e():
    # 1. Start Factory with KEEP_RUNNING=true
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(os.getcwd(), "factory", "src")
    env["DPP_FACTORY_TESTING"] = "false"
    env["DPP_FACTORY_KEEP_RUNNING"] = "true"
    
    cleanup_factory_containers()
    
    cmd = ["py", "-3.14", "-m", "uvicorn", "dpp_platform_factory.api.api:app", "--host", "127.0.0.1", "--port", "8009"]
    proc = subprocess.Popen(cmd, env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    
    assert wait_for_200("http://127.0.0.1:8009/health", timeout=30)
    
    # 2. Kill Factory (KEEP_RUNNING=true should preserve containers)
    if os.name == "nt":
        os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
    else:
        proc.terminate()
    proc.wait(timeout=10)
    
    # Verify containers still exist
    import docker
    d_client = docker.from_env()
    containers = d_client.containers.list(all=True, filters={"label": "managed-by=dpp-factory"})
    assert len(containers) > 0
    
    # 3. Restart Factory with orphans=reuse
    env["DPP_FACTORY_ORPHANS"] = "reuse"
    env["DPP_FACTORY_KEEP_RUNNING"] = "false" # Cleanup on next shutdown
    
    proc2 = subprocess.Popen(cmd, env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    assert wait_for_200("http://127.0.0.1:8009/health", timeout=30)
    
    # 4. Check federation - should have reconstructed state
    with httpx.Client(base_url="http://127.0.0.1:8009", timeout=30.0) as client:
        resp = client.get("/federation")
        assert resp.status_code == 200
        assert len(resp.json()["platforms"]) >= 2 # default platforms
        
    # 5. Final shutdown with cleanup
    if os.name == "nt":
        os.kill(proc2.pid, signal.CTRL_BREAK_EVENT)
    else:
        proc2.terminate()
    proc2.wait(timeout=30)
    
    # Verify containers are gone
    containers = d_client.containers.list(all=True, filters={"label": "managed-by=dpp-factory"})
    assert len(containers) == 0
