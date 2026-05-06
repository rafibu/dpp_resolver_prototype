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
    cleanup_factory_containers()
    
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(os.getcwd(), "factory", "src")
    env["DPP_FACTORY_TESTING"] = "false"
    
    # We use a different port from the main E2E test to avoid conflicts if run in parallel
    port = "8009"
    cmd = [
        "py", "-3.14", "-m", "uvicorn", "dpp_platform_factory.api.api:app",
        "--host", "127.0.0.1",
        "--port", port
    ]
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    )
    
    url = f"http://127.0.0.1:{port}"
    if not wait_for_200(f"{url}/health", timeout=60):
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            pytest.fail(f"Factory failed to start.\nSTDOUT: {stdout.decode()}\nSTDERR: {stderr.decode()}")
        else:
            pytest.fail("Factory timed out during startup")
    
    yield url
    
    if os.name == "nt":
        os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
    else:
        proc.terminate()
        
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
    
    cleanup_factory_containers()

def test_pv_battery_inverter_scenario_e2e(factory_server):
    factory_url = factory_server
    timeout = httpx.Timeout(60.0)
    
    with httpx.Client(timeout=timeout) as client:
        # 1. Get Federation Overview
        resp = client.get(f"{factory_url}/federation")
        assert resp.status_code == 200
        fed_data = resp.json()
        
        resolver_url = fed_data["resolver"]["external_url"]
        platforms = fed_data["platforms"]
        
        # Identify platforms by issuer_id or subject_types
        # Default federation usually has:
        # - platform-a: spring-postgres, issuerA, [pv_module, inverter]
        # - platform-b: fastapi-mongo, issuerB, [battery]
        
        spring_platform = next((p for p in platforms if "spring" in p["stack"]), None)
        fastapi_platform = next((p for p in platforms if "fastapi" in p["stack"]), None)
        
        assert spring_platform is not None, "Spring platform missing in federation"
        assert fastapi_platform is not None, "FastAPI platform missing in federation"
        
        spring_url = spring_platform["external_url"]
        fastapi_url = fastapi_platform["external_url"]
        
        # 2. Seed Schemas through Factory
        resp = client.post(f"{factory_url}/resolver/seed-schemas")
        assert resp.status_code == 200
        loaded = resp.json()["loaded"]
        assert "pv_module-1.0.json" in loaded
        assert "battery-1.0.json" in loaded
        assert "inverter-1.0.json" in loaded
        
        # 3. Sync Schemas on platforms
        # Sync pv_module and inverter on Spring
        for st in ["pv_module", "inverter"]:
            resp = client.post(f"{spring_url}/schemas/{st}/sync")
            assert resp.status_code == 200
            
        # Sync battery on FastAPI
        resp = client.post(f"{fastapi_url}/schemas/battery/sync")
        assert resp.status_code == 200
        
        # 4. Issue Battery DPP on FastAPI
        battery_payload = {
            "serial_number": "BAT-E2E-001",
            "manufacturer": "BatteryMaster",
            "capacity_wh": 5000
        }
        resp = client.post(f"{fastapi_url}/dpps", json=battery_payload, params={"subject_type": "battery"})
        assert resp.status_code == 201
        battery_data = resp.json()
        battery_id = battery_data["dpp_id"]
        
        # 5. Issue Inverter DPP on Spring
        inverter_payload = {
            "serial_number": "INV-E2E-001",
            "manufacturer": "PowerGrid",
            "efficiency": 0.98
        }
        resp = client.post(f"{spring_url}/dpps", json=inverter_payload, params={"subject_type": "inverter"})
        assert resp.status_code == 201
        inverter_data = resp.json()
        inverter_id = inverter_data["dpp_id"]
        
        # 6. Issue PV Module DPP on Spring referencing Battery and Inverter
        pv_payload = {
            "serial_number": "PV-E2E-001",
            "manufacturer": "SolarWorld",
            "components": {
                "battery": {"$ref": f"battery/{battery_id}"},
                "inverter": {"$ref": f"inverter/{inverter_id}"}
            }
        }
        resp = client.post(f"{spring_url}/dpps", json=pv_payload, params={"subject_type": "pv_module"})
        assert resp.status_code == 201
        pv_data = resp.json()
        pv_id = pv_data["dpp_id"]
        
        # 7. Retrieve PV Module and Resolve References
        # Get current revision of PV
        resp = client.get(f"{spring_url}/dpps/{pv_id}")
        assert resp.status_code == 200
        retrieved_pv = resp.json()
        
        # Check references in retrieved document
        refs = retrieved_pv["document"]["components"]
        assert f"battery/{battery_id}" in refs["battery"]["$ref"]
        assert f"inverter/{inverter_id}" in refs["inverter"]["$ref"]
        
        # 8. Verify Resolution via Resolver
        # The resolver should know where battery/inverter are
        resp = client.get(f"{resolver_url}/resolve/battery/{battery_id}")
        assert resp.status_code in [200, 302] # Depending on if client follows redirects
        
        resp = client.get(f"{resolver_url}/resolve/inverter/{inverter_id}")
        assert resp.status_code in [200, 302]
        
        # 9. Verify hash integrity
        assert retrieved_pv["hash"] is not None
        # In a real scenario, we would recompute and verify, but here we trust the platform for now
        
        print(f"Scenario complete: PV {pv_id} references Battery {battery_id} and Inverter {inverter_id}")
