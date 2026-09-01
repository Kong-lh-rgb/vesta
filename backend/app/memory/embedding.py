"""普通长期记忆检索使用的 Embedding 独立分层。

设计边界：
- 只定义最小 ``EmbeddingAdapter`` Protocol，不修改现有 Model Adapter 的
  公共接口（chat 语义与向量语义分离）；
- Embedding Provider 可以与主模型 Provider 完全不同，独立配置 base_url /
  api_key / model / dimensions；
- ``FakeEmbeddingAdapter`` 提供确定性离线向量（基于哈希的 n-gram 袋），
  供离线测试使用，禁止测试调用真实 API；
- 任何向量服务失败都只影响检索降级，不影响 Markdown 记忆读写。
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class MemoryEmbeddingSettings(BaseSettings):
    """Embedding 服务的独立运行配置（与主模型 Provider 解耦）。"""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="MEMORY_EMBEDDING_",
        extra="ignore",
    )

    # 总开关；关闭或缺少 model/api_key 时不构建真实 Adapter，检索降级 FTS5。
    enabled: bool = False
    # OpenAI 兼容 /embeddings 端点配置。
    base_url: str | None = None
    api_key: SecretStr | None = None
    model: str | None = None
    dimensions: int | None = Field(default=None, gt=0)
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=1, ge=0)
    # 单次请求最多打包的文本条数。
    batch_size: int = Field(default=16, ge=1)

    @field_validator("base_url", "model", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("embedding base_url and model must be strings")
        return value.strip() or None

    def adapter_configured(self) -> bool:
        """判断是否具备构建真实 Adapter 的最小配置。"""

        return self.enabled and bool(self.model) and self.api_key is not None


@runtime_checkable
class EmbeddingAdapter(Protocol):
    """最小 Embedding 接口：模型名 + 两个向量化入口。"""

    @property
    def model_name(self) -> str:
        """用于索引对账的模型标识；换模型触发全量重算。"""

    @property
    def dimensions(self) -> int | None:
        """已知向量维度；未知返回 None（由首批结果确定）。"""

    async def embed_documents(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        """把一批记忆 Chunk 文本向量化（索引写入路径）。"""

    async def embed_query(self, text: str) -> tuple[float, ...]:
        """把检索 Query 向量化（查询路径）。"""

    async def close(self) -> None:
        """释放底层客户端资源。"""


class OpenAICompatibleEmbeddingAdapter:
    """通过 OpenAI 兼容 /embeddings 端点提供向量服务。"""

    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str,
        model: str,
        dimensions: int | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
        batch_size: int = 16,
    ) -> None:
        from openai import AsyncOpenAI

        if not model:
            raise ValueError("embedding model is required")
        client_kwargs: dict[str, object] = {
            "api_key": api_key,
            "timeout": timeout_seconds,
            "max_retries": max_retries,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**client_kwargs)
        self._model = model
        self._dimensions = dimensions
        self._batch_size = max(1, batch_size)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int | None:
        return self._dimensions

    async def embed_documents(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(await self._embed(list(batch)))
        return tuple(vectors)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        vectors = await self._embed([text])
        return vectors[0]

    async def _embed(
        self,
        texts: list[str],
    ) -> list[tuple[float, ...]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return tuple(
            tuple(float(value) for value in item.embedding) for item in ordered
        )

    async def close(self) -> None:
        await self._client.close()


class FakeEmbeddingAdapter:
    """确定性离线向量：哈希 n-gram 袋 + L2 归一化。

    不调用任何外部服务；语义上等价于"共享词元越多越相似"，足以驱动
    离线召回 / 排名 / 降级测试。相同文本永远得到相同向量。
    """

    def __init__(
        self,
        *,
        dimensions: int = 1024,
        model_name: str = "fake-embedding",
    ) -> None:
        if dimensions <= 0:
            raise ValueError("fake embedding dimensions must be positive")
        self._dimensions = dimensions
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int | None:
        return self._dimensions

    async def embed_documents(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(self._vector(text) for text in texts)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return self._vector(text)

    async def close(self) -> None:
        return None

    def _vector(self, text: str) -> tuple[float, ...]:
        counts: dict[int, float] = {}
        for token in _semantic_tokens(text):
            bucket = _hash_bucket(token, self._dimensions)
            counts[bucket] = counts.get(bucket, 0.0) + 1.0
        vector = [0.0] * self._dimensions
        for bucket, weight in counts.items():
            vector[bucket] = weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return tuple(vector)


_TOKEN_SEPARATOR = re.compile(
    r"[\s,.;:!?，。；：！？、()\[\]{}\"'`|/\\<>@#$%^&*+=~\-_""]+"
)


def _semantic_tokens(text: str) -> list[str]:
    """提取词元 + CJK bigram，让中文改写查询仍能命中主题相近的记忆。"""

    tokens: list[str] = []
    for raw in _TOKEN_SEPARATOR.split(text.casefold()):
        if not raw:
            continue
        if raw.isascii():
            tokens.append(raw)
            continue
        tokens.extend(raw[i : i + 2] for i in range(len(raw) - 1))
        if len(raw) == 1:
            tokens.append(raw)
    return tokens


def _hash_bucket(token: str, dimensions: int) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dimensions


def build_embedding_adapter(
    settings: MemoryEmbeddingSettings,
) -> OpenAICompatibleEmbeddingAdapter | None:
    """按配置构建真实 Embedding Adapter；配置不完整时返回 None。"""

    if not settings.adapter_configured():
        return None
    return OpenAICompatibleEmbeddingAdapter(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value(),  # type: ignore[union-attr]
        model=settings.model or "",  # type: ignore[arg-type]
        dimensions=settings.dimensions,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
        batch_size=settings.batch_size,
    )


__all__ = [
    "EmbeddingAdapter",
    "FakeEmbeddingAdapter",
    "MemoryEmbeddingSettings",
    "OpenAICompatibleEmbeddingAdapter",
    "build_embedding_adapter",
]
