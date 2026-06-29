"""
API接口测试
"""

import pytest
from fastapi.testclient import TestClient

from elagent.main import app
from elagent.core.knowledge_base import knowledge_base


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


class TestAPI:
    """API测试类"""

    def test_root(self, client):
        """测试根目录"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    def test_health(self, client):
        """测试健康检查"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "kb_loaded" in data

    def test_kb_stats(self, client):
        """测试知识库统计"""
        response = client.get("/kb/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_entities" in data
        assert "entity_types" in data

    def test_link_endpoint_exists(self, client):
        """测试链接接口存在"""
        # 注意：如果知识库未加载，会返回503
        response = client.post("/link", json={
            "text": "测试文本",
            "mention": {
                "text": "测试",
                "start_pos": 0,
                "end_pos": 2
            }
        })
        # 可能是503（知识库未加载）或200（已加载）
        assert response.status_code in [200, 503]

    def test_batch_link_endpoint_exists(self, client):
        """测试批量链接接口存在"""
        response = client.post("/batch_link", json={
            "items": [
                {
                    "text": "测试文本",
                    "mention": {
                        "text": "测试",
                        "start_pos": 0,
                        "end_pos": 2
                    }
                }
            ]
        })
        # 可能是503（知识库未加载）或200（已加载）
        assert response.status_code in [200, 503]
