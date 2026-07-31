# Flow Vul Hunt

面向 CSV Payload 数据的多引擎检测、多智能体证据调查与风险告警系统。

当前已完成后端部分，使用 FastAPI、SQLAlchemy 和 SQLite，支持 OpenAI-compatible 大模型 API。后端运行、配置和接口说明见 [backend/README.md](backend/README.md)。

在仓库根目录启动完整后端：

```bash
python run_backend.py
```

接口文档默认位于 `http://127.0.0.1:8000/docs`。
