import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FakeContainer:
    id: str
    name: str
    image: str
    status: str = "running"
    labels: Dict[str, str] = field(default_factory=dict)
    environment: Dict[str, str] = field(default_factory=dict)
    ports: Dict[str, Any] = field(default_factory=dict)
    
    def stop(self, timeout=10):
        self.status = "exited"
        
    def start(self):
        self.status = "running"
        
    def remove(self, v=False, force=False):
        pass

    def exec_run(self, cmd, demux=False):
        return 0, b"ok"

    def restart(self):
        self.status = "running"

    @property
    def short_id(self):
        return self.id[:10]

@dataclass
class FakeNetwork:
    id: str
    name: str
    short_id: str
    containers: List[Any] = field(default_factory=list)

class FakeDockerClient:
    def __init__(self):
        self.containers_list: Dict[str, FakeContainer] = {}
        self.networks_list: Dict[str, FakeNetwork] = {}
        self.volumes_list: Dict[str, bool] = {}
        self.fail_run_on: Optional[str] = None
        self.fail_wait_healthy_on: Optional[str] = None

    def ensure_network(self, name: str) -> FakeNetwork:
        if name not in self.networks_list:
            self.networks_list[name] = FakeNetwork(id=f"net-{name}", name=name, short_id=name[:5])
        return self.networks_list[name]

    def find_containers_by_label(self, label_filters: Dict[str, str]) -> List[FakeContainer]:
        results = []
        for c in self.containers_list.values():
            match = True
            for k, v in label_filters.items():
                if c.labels.get(k) != v:
                    match = False
                    break
            if match:
                results.append(c)
        return results

    def run_container(self, image, name, env, ports, volumes, network, labels, command=None) -> FakeContainer:
        if self.fail_run_on == name:
            raise RuntimeError(f"Simulated failure for {name}")

        for volume_name in volumes:
            self.volumes_list[volume_name] = True
        
        container = FakeContainer(
            id=f"id-{name}",
            name=name,
            image=image,
            labels=labels,
            environment=env,
            ports=ports
        )
        self.containers_list[name] = container
        return container

    def stop_container(self, container: FakeContainer, timeout=10):
        container.stop(timeout)

    def remove_container(self, container: FakeContainer, remove_volumes=False):
        if container.name in self.containers_list:
            del self.containers_list[container.name]

    def remove_volume(self, name: str) -> bool:
        return self.volumes_list.pop(name, None) is not None

    def start_container(self, container: FakeContainer):
        container.start()

    def wait_healthy(self, container: FakeContainer, health_url, timeout=30):
        if self.fail_wait_healthy_on == container.name:
            raise TimeoutError(f"Simulated health timeout for {container.name}")
        # In fake world, we just succeed unless told to fail
        pass

    def get_container(self, container_id_or_name: str) -> FakeContainer:
        # Simple lookup in our list
        for c in self.containers_list.values():
            if c.id == container_id_or_name or c.name == container_id_or_name:
                return c
        raise RuntimeError(f"Container {container_id_or_name} not found")

    def stop_by_id(self, container_id: str, timeout: int = 10):
        c = self.get_container(container_id)
        c.stop(timeout)

    def start_by_id(self, container_id: str):
        c = self.get_container(container_id)
        c.start()

    def stop_and_remove_by_id(self, container_id: str, remove_volumes: bool = False):
        c = self.get_container(container_id)
        c.stop()
        self.remove_container(c, remove_volumes)
