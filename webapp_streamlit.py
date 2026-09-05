import os

import streamlit as st

from agent import build_agent
from utils import retry


st.set_page_config(page_title="OpenRouter Agent", page_icon="🤖", layout="centered")


@st.cache_resource(show_spinner=False)
def get_agent(model: str):
    return build_agent(model)


@retry(max_retries=3)
def invoke_agent(agent, prompt: str):
    """Send a user prompt to the backend agent."""
    return agent.invoke({"messages": [("user", prompt)]})


def render_ui():
    st.title("OpenRouter Agent")

    model = st.text_input(
        "Model",
        value=os.getenv("OPENROUTER_MODEL", ""),
        help="Enter an OpenRouter model name",
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_model" not in st.session_state:
        st.session_state.agent_model = None
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask the agent...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                agent = get_agent(model)
                try:
                    response = invoke_agent(agent, prompt)
                    final_text = ""
                    for message in response.get("messages", []):
                        content = getattr(message, "content", None)
                        if content:
                            final_text = str(content)
                    if final_text:
                        st.markdown(final_text)
                        st.session_state.messages.append({"role": "assistant", "content": final_text})
                    else:
                        st.markdown("No response generated.")
                        st.session_state.messages.append({"role": "assistant", "content": "No response generated."})
                except Exception as exc:
                    st.error(str(exc))
                    st.session_state.messages.append({"role": "assistant", "content": str(exc)})


def run_app():
    render_ui()


if __name__ == "__main__":
    run_app()
