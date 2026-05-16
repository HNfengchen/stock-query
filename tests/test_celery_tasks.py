import pytest
from unittest.mock import patch, MagicMock

from backend.celery_app import is_celery_enabled, get_celery_app, init_celery


@pytest.fixture(autouse=True)
def reset_celery_state():
    import backend.celery_app as mod
    original_app = mod.celery_app
    original_enabled = mod.celery_enabled
    mod.celery_app = None
    mod.celery_enabled = False

    import backend.tasks as tasks_mod
    tasks_mod._analyze_stock_task = None
    tasks_mod._batch_analyze_task = None

    yield

    mod.celery_app = original_app
    mod.celery_enabled = original_enabled


class TestCeleryAppInit:
    def test_init_celery_disabled_by_default(self):
        result = init_celery()
        assert result is None
        assert is_celery_enabled() is False

    def test_init_celery_config_enabled_but_celery_not_installed(self):
        config = {"celery": {"enabled": True, "broker_url": "redis://localhost:6379/0"}}
        with patch("backend.celery_app._load_celery_config", return_value=config.get("celery")):
            with patch.dict("sys.modules", {"celery": None}):
                result = init_celery()
                assert result is None
                assert is_celery_enabled() is False

    def test_init_celery_successfully(self):
        try:
            from celery import Celery
        except ImportError:
            pytest.skip("Celery not installed")

        config = {
            "broker_url": "redis://localhost:6379/0",
            "result_backend": "redis://localhost:6379/1",
            "worker_concurrency": 4,
            "task_timeout": 300,
            "enabled": True,
        }
        with patch("backend.celery_app._load_celery_config", return_value=config):
            result = init_celery()
            assert result is not None
            assert is_celery_enabled() is True

    def test_get_celery_app_returns_none_when_not_initialized(self):
        assert get_celery_app() is None


class TestCeleryDisabledAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        return TestClient(app)

    def test_batch_async_returns_503_when_celery_disabled(self, client):
        response = client.post("/api/analysis/batch-async", json={
            "stock_codes": ["000001"],
            "position_type": "未持有",
        })
        assert response.status_code == 503
        assert "Celery" in response.json()["detail"]

    def test_task_status_returns_503_when_celery_disabled(self, client):
        response = client.get("/api/analysis/task/fake-task-id")
        assert response.status_code == 503
        assert "Celery" in response.json()["detail"]


class TestCeleryTasksDefinition:
    def test_get_task_raises_when_celery_not_initialized(self):
        from backend.tasks import get_analyze_stock_task, get_batch_analyze_task

        with pytest.raises(RuntimeError, match="Celery 未启用"):
            get_analyze_stock_task()

        with pytest.raises(RuntimeError, match="Celery 未启用"):
            get_batch_analyze_task()


class TestCeleryTasksWithEagerMode:
    @pytest.fixture
    def eager_celery(self):
        try:
            from celery import Celery
        except ImportError:
            pytest.skip("Celery not installed")

        app = Celery("test", broker="memory://", backend="cache+memory://")
        app.conf.update(
            task_always_eager=True,
            task_eager_propagates=False,
            task_store_eager_result=True,
            task_serializer="json",
            result_serializer="json",
        )

        from backend.tasks import register_tasks
        register_tasks(app)

        import backend.celery_app as mod
        mod.celery_app = app
        mod.celery_enabled = True

        yield app

        mod.celery_app = None
        mod.celery_enabled = False

    def test_analyze_stock_task_handles_exception(self, eager_celery):
        from backend.tasks import get_analyze_stock_task

        task = get_analyze_stock_task()
        with patch("backend.services.analysis_service.run_analysis", side_effect=ValueError("测试错误")):
            r = task.apply(args=("000001",))
            result = r.result
            assert "error" in result
            assert result["stock_code"] == "000001"
            assert "测试错误" in result["error"]

    def test_analyze_stock_task_success(self, eager_celery):
        from backend.tasks import get_analyze_stock_task

        task = get_analyze_stock_task()
        mock_result = {"stock_code": "000001", "stock_name": "测试股票", "analysis": {}}
        with patch("backend.services.analysis_service.run_analysis", return_value=mock_result):
            r = task.apply(args=("000001",))
            result = r.result
            assert result["stock_code"] == "000001"
            assert "error" not in result

    def test_batch_analyze_task_sequential(self, eager_celery):
        from backend.tasks import get_batch_analyze_task

        task = get_batch_analyze_task()
        mock_results = {
            "000001": {"stock_code": "000001", "stock_name": "股票A"},
            "000002": {"stock_code": "000002", "stock_name": "股票B"},
        }

        def side_effect(code, *args, **kwargs):
            return mock_results.get(code, {"stock_code": code})

        with patch("backend.services.analysis_service.run_analysis", side_effect=side_effect):
            r = task.apply(args=(["000001", "000002"],))
            result = r.result
            assert len(result) == 2
            assert result[0]["stock_code"] == "000001"
            assert result[1]["stock_code"] == "000002"


class TestTaskStatusEndpoint:
    @pytest.fixture
    def client_with_celery(self):
        try:
            from celery import Celery
        except ImportError:
            pytest.skip("Celery not installed")

        from fastapi.testclient import TestClient
        from backend.app import app

        test_celery = Celery("test", broker="memory://", backend="cache+memory://")
        test_celery.conf.update(
            task_always_eager=True,
            task_eager_propagates=False,
            task_store_eager_result=True,
        )

        from backend.tasks import register_tasks
        register_tasks(test_celery)

        import backend.celery_app as mod
        mod.celery_app = test_celery
        mod.celery_enabled = True

        yield TestClient(app)

        mod.celery_app = None
        mod.celery_enabled = False

    def test_task_status_pending(self, client_with_celery):
        response = client_with_celery.get("/api/analysis/task/nonexistent-task-id")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "nonexistent-task-id"
        assert data["status"] == "pending"

    def test_batch_async_submits_task(self, client_with_celery):
        with patch("backend.services.analysis_service.run_analysis", return_value={"stock_code": "000001"}):
            response = client_with_celery.post("/api/analysis/batch-async", json={
                "stock_codes": ["000001"],
                "position_type": "未持有",
            })
            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert data["status"] == "submitted"

    def test_batch_async_rejects_empty_codes(self, client_with_celery):
        response = client_with_celery.post("/api/analysis/batch-async", json={
            "stock_codes": [],
            "position_type": "未持有",
        })
        assert response.status_code == 400
