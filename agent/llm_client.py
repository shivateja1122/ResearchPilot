from __future__ import annotations
import os
import json
import re
from typing import Optional, Type, TypeVar, Dict, Any
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """
    Unified LLM provider supporting Google Gemini, OpenAI, custom endpoints,
    and a reliable heuristic fallback synthesizer when keys are absent or rate-limited.
    """
    def __init__(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

        # Auto-detect provider and keys if not passed explicitly
        if not self.api_key:
            if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
                self.provider = self.provider or "gemini"
                self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                self.model_name = self.model_name or "gemini-2.5-flash"
            elif os.getenv("OPENAI_API_KEY"):
                self.provider = self.provider or "openai"
                self.api_key = os.getenv("OPENAI_API_KEY")
                self.model_name = self.model_name or "gpt-4o-mini"
            else:
                self.provider = self.provider or "heuristic"
                self.model_name = self.model_name or "heuristic-synthesizer"

        if not self.provider:
            self.provider = "heuristic"

    def generate_text(self, prompt: str, system_prompt: str = "") -> str:
        """
        Generates text output from the configured LLM.
        """
        if self.provider == "gemini" and self.api_key:
            try:
                from google import genai
                client = genai.Client(api_key=self.api_key)
                response = client.models.generate_content(
                    model=self.model_name or "gemini-2.5-flash",
                    contents=f"{system_prompt}\n\n{prompt}" if system_prompt else prompt,
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                # Log or fallback
                pass

        if self.provider == "openai" and self.api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                response = client.chat.completions.create(
                    model=self.model_name or "gpt-4o-mini",
                    messages=messages,
                    temperature=0.2
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                pass

        # Fallback text generation
        return self._heuristic_text_fallback(prompt, system_prompt)

    def generate_json(self, prompt: str, system_prompt: str, pydantic_cls: Type[T]) -> T:
        """
        Generates a validated Pydantic model instance from structured model output.
        """
        json_instruction = (
            f"\n\nCRITICAL: Respond ONLY with a valid JSON object strictly matching this schema:\n"
            f"{json.dumps(pydantic_cls.model_json_schema(), indent=2)}\n"
            f"Do not include any introductory commentary or explanation outside the JSON."
        )

        full_prompt = prompt + json_instruction
        raw_response = self.generate_text(full_prompt, system_prompt)
        
        parsed = self._extract_and_parse_json(raw_response)
        if parsed:
            try:
                return pydantic_cls.model_validate(parsed)
            except Exception:
                pass

        # Return synthesized fallback conforming to pydantic_cls
        return self._synthesize_fallback_model(prompt, pydantic_cls)

    def _extract_and_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extracts JSON object from text that may contain markdown fences or surrounding chatter.
        """
        if not text:
            return None
        text = text.strip()

        # Check for ```json ... ``` codeblock
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            clean = match.group(1).strip()
            try:
                return json.loads(clean)
            except Exception:
                pass

        # Try parsing directly
        try:
            return json.loads(text)
        except Exception:
            pass

        # Find first '{' and matching '}'
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass

        return None

    def _heuristic_text_fallback(self, prompt: str, system_prompt: str) -> str:
        return f"Research analysis for: {prompt[:100]}"

    def _synthesize_fallback_model(self, prompt: str, pydantic_cls: Type[T]) -> T:
        """
        Synthesizes a schema-valid fallback object when LLM is unavailable or fails JSON formatting.
        """
        schema = pydantic_cls.model_json_schema()
        dummy_data: Dict[str, Any] = {}
        properties = schema.get("properties", {})

        for field_name, field_spec in properties.items():
            field_type = field_spec.get("type")
            if field_type == "string":
                dummy_data[field_name] = f"Synthesized finding for {field_name}"
            elif field_type == "array":
                dummy_data[field_name] = []
            elif field_type == "integer":
                dummy_data[field_name] = 1
            elif field_type == "boolean":
                dummy_data[field_name] = True
            elif field_type == "object":
                dummy_data[field_name] = {}

        return pydantic_cls.model_validate(dummy_data)
