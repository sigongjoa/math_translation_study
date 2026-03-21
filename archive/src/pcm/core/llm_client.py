"""
LLM abstraction layer for the PCM Translation Pipeline.

Centralises all Ollama API calls behind a single OllamaClient so that:
  - The Ollama URL / model can be changed in one place (or via env var).
  - Unit tests can mock the client without patching requests globally.
  - Future providers (OpenAI, Anthropic, local GGUF, ...) are plug-in swaps.

Usage:
    from src.pcm.core.llm_client import OllamaClient

    client = OllamaClient()                     # defaults from env / fallback
    text   = client.generate("Explain groups")
    reply  = client.chat([{"role": "user", "content": "Hello"}])

Environment variables (all optional):
    OLLAMA_BASE_URL  — e.g. http://192.168.1.10:11434  (default: localhost)
    OLLAMA_MODEL     — e.g. qwen2.5:14b                (default: qwen2.5:7b)
"""

from __future__ import annotations

import os
import requests
from typing import Optional

# ---------------------------------------------------------------------------
# Defaults (env-override friendly)
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL: str = os.environ.get(
    "OLLAMA_BASE_URL", "http://localhost:11434"
).rstrip("/")

_DEFAULT_MODEL: str = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMClient:
    """Minimal interface that every LLM provider must implement."""

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.3,
        num_predict: int = 300,
        timeout: int = 60,
    ) -> str:
        """Single-turn text completion. Returns empty string on failure."""
        raise NotImplementedError

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.1,
        timeout: int = 120,
        json_format: bool = False,
    ) -> str:
        """Multi-turn chat completion. Returns empty string on failure."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Ollama implementation
# ---------------------------------------------------------------------------

class OllamaClient(LLMClient):
    """
    Client for a locally-running Ollama instance.

    Parameters
    ----------
    model:
        Model tag (e.g. ``"qwen2.5:7b"``). Defaults to ``OLLAMA_MODEL`` env var.
    base_url:
        Base URL of the Ollama server. Defaults to ``OLLAMA_BASE_URL`` env var.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
    ):
        self.model = model
        self._generate_url = f"{base_url}/api/generate"
        self._chat_url = f"{base_url}/api/chat"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.3,
        num_predict: int = 300,
        timeout: int = 60,
    ) -> str:
        """
        Call ``/api/generate`` (single-prompt completion).

        Returns
        -------
        str
            Model response text, or empty string on failure.
        """
        try:
            resp = requests.post(
                self._generate_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": num_predict,
                    },
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except (requests.RequestException, KeyError, ValueError):
            return ""

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.1,
        timeout: int = 120,
        json_format: bool = False,
    ) -> str:
        """
        Call ``/api/chat`` (multi-turn conversation).

        Parameters
        ----------
        messages:
            List of ``{"role": "...", "content": "..."}`` dicts.
        json_format:
            When True passes ``"format": "json"`` to request structured output.

        Returns
        -------
        str
            Assistant reply text, or empty string on failure.
        """
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_format:
            payload["format"] = "json"

        try:
            resp = requests.post(self._chat_url, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except (requests.RequestException, KeyError, ValueError):
            return ""

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def generate_or_fallback(self, prompt: str, fallback: str, **kwargs) -> str:
        """Like generate(), but returns *fallback* instead of empty string."""
        result = self.generate(prompt, **kwargs)
        return result if result else fallback

    def chat_or_fallback(self, messages: list[dict], fallback: str, **kwargs) -> str:
        """Like chat(), but returns *fallback* instead of empty string."""
        result = self.chat(messages, **kwargs)
        return result if result else fallback
