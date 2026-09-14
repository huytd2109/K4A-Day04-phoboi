from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from chat import (
    now_iso,
    run_model_tool_loop,
    safe_slug,
    trim_history,
    write_transcript,
)
from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version


ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
TRANSCRIPTS_DIR = ROOT / "transcripts"

load_lab_env(ROOT)

st.set_page_config(
    page_title="IT Helpdesk Agent",
    page_icon="🛠️",
    layout="wide",
)


def render_trace(rounds: list[dict[str, Any]]) -> None:
    for round_item in rounds:
        round_number = round_item.get("round", "?")

        with st.expander(f"Round {round_number} — tool trace"):
            intermediate_text = round_item.get("assistant_text")
            if intermediate_text:
                st.caption("Assistant intermediate response")
                st.write(intermediate_text)

            calls = round_item.get("tool_calls") or []
            if calls:
                st.caption("Tool calls")
                st.json(calls)

            for event in round_item.get("tool_results") or []:
                tool_name = event.get("tool", "unknown")
                st.markdown(f"**Tool: `{tool_name}`**")

                st.caption("Arguments")
                st.json(event.get("args") or {})

                result = event.get("result")
                if isinstance(result, dict) and result.get("error"):
                    st.error(
                        f"{result.get('error')}: "
                        f"{result.get('message', 'Unknown tool error')}"
                    )

                st.caption("Result")
                st.json(result)


def create_transcript(
    *,
    version: str,
    provider_name: str,
    model_name: str | None,
    artifact: Any,
    history_window: int,
    max_tool_rounds: int,
) -> tuple[Path, dict[str, Any]]:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join(
        [
            safe_slug(version),
            safe_slug(provider_name),
            timestamp,
        ]
    )
    transcript_path = (
        TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
    )

    transcript = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact),
        "provider": provider_name,
        "model": model_name,
        "system_prompt": str(ARTIFACTS_DIR / "system_prompt.md"),
        "tools": str(ARTIFACTS_DIR / "tools.yaml"),
        "history_window": history_window,
        "max_tool_rounds": max_tool_rounds,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }
    return transcript_path, transcript


def reset_conversation() -> None:
    for key in [
        "model_history",
        "ui_messages",
        "transcript",
        "transcript_path",
        "turn_index",
        "conversation_config",
    ]:
        st.session_state.pop(key, None)


st.title("🛠️ Northstar Labs IT Helpdesk Agent")
st.caption("Chat UI with auditable tool calls and artifact versioning")

with st.sidebar:
    st.header("Runtime")

    provider_name = st.selectbox(
        "Provider",
        ["openrouter", "openai", "anthropic", "gemini"],
    )
    model_override = st.text_input(
        "Model override",
        placeholder="Để trống để dùng model mặc định",
    )
    version_label = st.text_input(
        "Version label",
        value="v4",
    )
    history_window = st.number_input(
        "History window",
        min_value=1,
        max_value=20,
        value=5,
    )
    max_tool_rounds = st.number_input(
        "Max tool rounds",
        min_value=1,
        max_value=10,
        value=4,
    )

    if st.button("New conversation", use_container_width=True):
        reset_conversation()
        st.rerun()


system_prompt_path = ARTIFACTS_DIR / "system_prompt.md"
tools_path = ARTIFACTS_DIR / "tools.yaml"

system_prompt = system_prompt_path.read_text(encoding="utf-8")
tool_declarations = load_tool_declarations(tools_path)
openai_tools = to_openai_tools(tool_declarations)

artifact = build_artifact_version(
    version_label,
    system_prompt_path,
    tools_path,
)

st.sidebar.subheader("Artifact")
st.sidebar.code(artifact.artifact_version)
st.sidebar.caption(f"Prompt hash: {artifact.prompt_hash}")
st.sidebar.caption(f"Tools hash: {artifact.tools_hash}")

if "model_history" not in st.session_state:
    st.session_state.model_history = []

if "ui_messages" not in st.session_state:
    st.session_state.ui_messages = []

if "turn_index" not in st.session_state:
    st.session_state.turn_index = 0

current_config = (
    provider_name,
    model_override,
    version_label,
    artifact.artifact_version,
)

previous_config = st.session_state.get("conversation_config")
if (
    previous_config
    and previous_config != current_config
    and st.session_state.model_history
):
    st.warning(
        "Provider/model/artifact đã thay đổi. "
        "Hãy chọn New conversation trước khi tiếp tục."
    )
    st.stop()

st.session_state.conversation_config = current_config

for item in st.session_state.ui_messages:
    with st.chat_message(item["role"]):
        st.markdown(item["content"])
        if item.get("rounds"):
            render_trace(item["rounds"])
        if item.get("status"):
            st.caption(f"Status: {item['status']}")

user_text = st.chat_input("Mô tả vấn đề IT cần hỗ trợ...")

if user_text:
    st.session_state.ui_messages.append(
        {"role": "user", "content": user_text}
    )

    with st.chat_message("user"):
        st.markdown(user_text)

    started_at = now_iso()
    st.session_state.turn_index += 1

    try:
        provider = make_provider(provider_name)
        selected_model = (
            model_override.strip()
            or getattr(provider, "default_model", None)
        )

        if "transcript" not in st.session_state:
            path, transcript = create_transcript(
                version=version_label,
                provider_name=provider_name,
                model_name=selected_model,
                artifact=artifact,
                history_window=int(history_window),
                max_tool_rounds=int(max_tool_rounds),
            )
            st.session_state.transcript_path = path
            st.session_state.transcript = transcript

        messages = [
            {"role": "system", "content": system_prompt},
            *trim_history(
                st.session_state.model_history,
                int(history_window),
            ),
            {"role": "user", "content": user_text},
        ]

        with st.spinner("Agent đang xử lý..."):
            result = run_model_tool_loop(
                provider=provider,
                messages=messages,
                tools=openai_tools,
                model=model_override.strip() or None,
                max_tool_rounds=int(max_tool_rounds),
            )

        assistant_text = result.get("assistant_text") or ""
        status = result.get("status", "unknown")
        rounds = result.get("rounds") or []

        st.session_state.model_history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        )

        st.session_state.ui_messages.append(
            {
                "role": "assistant",
                "content": assistant_text,
                "status": status,
                "rounds": rounds,
            }
        )

        turn_record = {
            "turn_index": st.session_state.turn_index,
            "started_at": started_at,
            "ended_at": now_iso(),
            "user": user_text,
            **result,
        }

        st.session_state.transcript["turns"].append(turn_record)
        write_transcript(
            st.session_state.transcript_path,
            st.session_state.transcript,
        )

        with st.chat_message("assistant"):
            st.markdown(assistant_text)
            render_trace(rounds)
            st.caption(f"Status: {status}")

        st.caption(
            f"Transcript: {st.session_state.transcript_path}"
        )

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"

        st.session_state.ui_messages.append(
            {
                "role": "assistant",
                "content": error_message,
                "status": "provider_error",
            }
        )

        with st.chat_message("assistant"):
            st.error(error_message)
            st.caption("Status: provider_error")