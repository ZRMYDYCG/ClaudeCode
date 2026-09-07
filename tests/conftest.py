"""
测试用环境变量：导入 core.agent / main 时会读 API_KEY / BASE_URL。
没有真实密钥时用占位值，避免模块级 RuntimeError。
"""

import os

# 必须在任何会 import core.agent.core 的测试之前生效
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("BASE_URL", "https://example.com/v1")
os.environ.setdefault("MODEL_NAME", "test-model")
