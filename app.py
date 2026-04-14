import requests
import streamlit as st

BACKEND_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Sage",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    * { font-family: 'Inter', sans-serif !important; }

    /* ─── Base ─── */
    html, body,
    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"],
    [data-testid="stMain"],
    .main {
        background-color: #0e0b16 !important;
        color: #f0eeff !important;
    }

    :root {
        --primary-color: #865DFF;
    }

    a, a:hover { color: #865DFF !important; }

    *:focus-visible {
        outline-color: #865DFF !important;
    }

    /* ─── Sidebar ─── */
    [data-testid="stSidebar"] {
        background: #0a0812 !important;
        border-right: 1px solid rgba(134, 93, 255, 0.18) !important;
    }

    [data-testid="stSidebar"] .stSubheader,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div {
        color: #c5b8f0 !important;
    }

    [data-testid="stSidebar"] .stSelectbox > div > div {
        background-color: #14102a !important;
        border: 1px solid rgba(134, 93, 255, 0.3) !important;
        border-radius: 10px !important;
        color: #f0eeff !important;
        transition: border-color 0.2s ease;
    }

    [data-testid="stSidebar"] .stSelectbox > div > div:hover {
        border-color: #865DFF !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        width: 100%;
        background: rgba(134, 93, 255, 0.07) !important;
        color: #E384FF !important;
        border: 1px solid rgba(134, 93, 255, 0.3) !important;
        border-radius: 10px !important;
        padding: 0.55rem 1rem !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        letter-spacing: 0.03em;
        transition: all 0.2s ease !important;
    }

    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(134, 93, 255, 0.18) !important;
        border-color: #865DFF !important;
        color: #FFA3FD !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 18px rgba(134, 93, 255, 0.25) !important;
    }

    [data-testid="stSidebar"] .stButton > button:active {
        transform: translateY(0);
        box-shadow: none !important;
    }

    /* ─── Hide default chat avatars ─── */
    [data-testid="stChatMessageAvatarUser"],
    [data-testid="stChatMessageAvatarAssistant"],
    .stChatMessageAvatar,
    [data-testid="stAvatarIcon"] {
        display: none !important;
        width: 0 !important;
        min-width: 0 !important;
    }

    [data-testid="stChatMessage"] > div {
        gap: 0 !important;
    }

    /* ─── Chat bubbles ─── */
    .stChatMessage {
        background-color: #110e1c !important;
        border: 1px solid rgba(134, 93, 255, 0.1) !important;
        border-radius: 14px !important;
        padding: 14px 18px !important;
        margin-bottom: 10px !important;
        animation: fadeSlideIn 0.28s ease forwards;
        transition: border-color 0.25s ease;
    }

    .stChatMessage:hover {
        border-color: rgba(134, 93, 255, 0.28) !important;
    }

    /* ─── Role chips ─── */
    .role-chip {
        display: inline-block;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin-bottom: 8px;
        padding: 2px 10px;
        border-radius: 20px;
    }

    .label-you {
        color: #ffffff !important;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.14);
    }

    .label-sage {
        color: #E384FF !important;
        background: rgba(134, 93, 255, 0.1);
        border: 1px solid rgba(134, 93, 255, 0.35);
    }

    /* ─── Floating Pill Input Bar ─── */
    [data-testid="stBottom"],
    [data-testid="stBottom"] > div {
        background: transparent !important;
        padding-bottom: 20px !important;
    }

    [data-testid="stChatInput"] {
        background: #13102a !important;
        border: 1px solid transparent !important;
        border-radius: 999px !important;
        padding: 4px 6px !important;
        box-shadow:
            0 8px 32px rgba(0, 0, 0, 0.55),
            0 2px 10px rgba(0, 0, 0, 0.35) !important;
        transition: border-color 0.3s ease, box-shadow 0.35s ease !important;
        max-width: 860px !important;
        margin: 0 auto !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
    }

    [data-testid="stChatInput"]:focus-within {
        border-color: #865DFF !important;
        box-shadow:
            0 8px 32px rgba(0, 0, 0, 0.55),
            0 0 0 3px rgba(134, 93, 255, 0.14),
            0 0 24px rgba(134, 93, 255, 0.35),
            0 0 52px rgba(255, 163, 253, 0.15) !important;
    }

    [data-testid="stChatInput"]:hover:not(:focus-within) {
        border-color: rgba(134, 93, 255, 0.35) !important;
    }

    [data-testid="stChatInputTextArea"],
    [data-testid="stChatInputTextArea"] > div,
    [data-testid="stChatInputTextArea"] [data-baseweb="textarea"],
    [data-testid="stChatInputTextArea"] [data-baseweb="base-input"],
    [data-testid="stChatInputTextArea"] [data-baseweb="base-input"] > div {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }

    [data-testid="stChatInputTextArea"] textarea {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        outline: none !important;
        color: #f0eeff !important;
        font-size: 0.95rem !important;
        padding: 10px 14px !important;
        transition: none !important;
        caret-color: #865DFF !important;
    }

    [data-testid="stChatInputTextArea"] textarea:hover,
    [data-testid="stChatInputTextArea"] textarea:focus,
    [data-testid="stChatInputTextArea"] textarea:active,
    [data-testid="stChatInputTextArea"] [data-baseweb="textarea"]:hover,
    [data-testid="stChatInputTextArea"] [data-baseweb="textarea"]:focus-within,
    [data-testid="stChatInputTextArea"] [data-baseweb="base-input"]:hover,
    [data-testid="stChatInputTextArea"] [data-baseweb="base-input"]:focus-within {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }

    [data-testid="stChatInputTextArea"] textarea::placeholder {
        color: rgba(255, 255, 255, 0.35) !important;
    }

    [data-testid="stChatInputSubmitButton"] button {
        background: linear-gradient(135deg, #865DFF 0%, #6b3ee8 100%) !important;
        border: none !important;
        border-radius: 999px !important;
        width: 38px !important;
        height: 38px !important;
        flex-shrink: 0 !important;
        transition: all 0.22s ease !important;
    }

    [data-testid="stChatInputSubmitButton"] button:hover,
    [data-testid="stChatInputSubmitButton"] button:focus,
    [data-testid="stChatInputSubmitButton"] button:active,
    [data-testid="stChatInputSubmitButton"] button:focus-visible {
        background: linear-gradient(135deg, #E384FF 0%, #865DFF 100%) !important;
        border: none !important;
        outline: none !important;
        box-shadow: 0 4px 18px rgba(255, 163, 253, 0.45) !important;
    }

    [data-testid="stChatInputSubmitButton"] button:hover {
        transform: scale(1.08);
    }

    [data-testid="stChatInputSubmitButton"] button:active {
        transform: scale(0.97);
        box-shadow: none !important;
    }

    [data-testid="stChatInputSubmitButton"] button svg,
    [data-testid="stChatInputSubmitButton"] button svg path,
    [data-testid="stChatInputSubmitButton"] button svg circle {
        fill: #ffffff !important;
        stroke: #ffffff !important;
        color: #ffffff !important;
    }

    /* ─── Status badge ─── */
    .status-badge {
        display: inline-flex;
        align-items: center;
        background: rgba(134, 93, 255, 0.07);
        border: 1px solid rgba(134, 93, 255, 0.2);
        border-radius: 20px;
        padding: 3px 12px;
        font-size: 0.72rem;
        color: #865DFF !important;
        margin-top: 8px;
        letter-spacing: 0.02em;
    }

    .memory-chip {
        display: inline-flex;
        align-items: center;
        background: rgba(227, 132, 255, 0.08);
        border: 1px solid rgba(227, 132, 255, 0.2);
        border-radius: 12px;
        padding: 6px 10px;
        font-size: 0.78rem;
        color: #f0eeff !important;
        margin: 4px 0;
    }

    /* ─── Health dots ─── */
    .health-row {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 5px 0;
        font-size: 0.78rem;
        color: #6e618e !important;
    }

    .dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #865DFF;
        box-shadow: 0 0 6px rgba(134, 93, 255, 0.7);
        flex-shrink: 0;
    }

    .stAlert {
        background-color: #180d1f !important;
        border: 1px solid rgba(255, 163, 253, 0.2) !important;
        border-radius: 12px !important;
    }

    @keyframes fadeSlideIn {
        from { opacity: 0; transform: translateY(8px); }
        to   { opacity: 1; transform: translateY(0);   }
    }

    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(134, 93, 255, 0.28);
        border-radius: 10px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: rgba(227, 132, 255, 0.5);
    }

    @media (max-width: 768px) {
        .stChatMessage { padding: 10px 13px !important; border-radius: 12px !important; }
        [data-testid="stChatInputTextArea"] textarea { font-size: 16px !important; }
        [data-testid="stChatInput"] { border-radius: 999px !important; margin: 0 8px !important; }
        .status-badge { font-size: 0.67rem; }
    }

    @media (max-width: 480px) {
        .stChatMessage { margin-bottom: 8px !important; }
        .role-chip { font-size: 0.63rem; }
        [data-testid="stChatInput"] { margin: 0 4px !important; }
    }

    #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "memory_refresh_nonce" not in st.session_state:
    st.session_state.memory_refresh_nonce = 0

def fetch_health():
    try:
        return requests.get(f"{BACKEND_URL}/health", timeout=10).json()
    except Exception:
        return None

def fetch_memories():
    try:
        resp = requests.get(
            f"{BACKEND_URL}/memory/view",
            params={"limit": 50},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("memories", [])
    except Exception:
        return []

def fetch_cartridge_names():
    try:
        resp = requests.get(f"{BACKEND_URL}/cartridges", timeout=10)
        resp.raise_for_status()
        data = resp.json().get("cartridges", {})
        # Filter to enabled, non-memory cartridges for the UI selector
        names = []
        for name, cart in data.items():
            if not cart.get("enabled", True):
                continue
            roles = cart.get("roles", [])
            if set(roles) <= {"memory", "classify"}:
                continue
            names.append(name)
        return names
    except Exception:
        return ["cloud-fast", "local-default", "local-heavy"]

with st.sidebar:
    st.subheader("Settings")

    mode = st.selectbox(
        "Mode",
        ["auto", "groq", "ollama"],
        index=0
    )

    available_cartridges = fetch_cartridge_names()
    cartridge = st.selectbox(
        "Cartridge",
        ["auto"] + available_cartridges,
        index=0
    )

    if st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()

    if st.button("Refresh memory"):
        st.session_state.memory_refresh_nonce += 1
        st.rerun()

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    health = fetch_health()
    if health:
        st.markdown(f"""
        <div class="health-row"><span class="dot"></span> Groq: {health.get('groq_configured')}</div>
        <div class="health-row"><span class="dot"></span> Cloud model: {health.get('groq_model')}</div>
        <div class="health-row"><span class="dot"></span> Local model: {health.get('ollama_model')}</div>
        <div class="health-row"><span class="dot"></span> Memory model: {health.get('memory_model')}</div>
        """, unsafe_allow_html=True)
    else:
        st.error("Backend not reachable.")

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.subheader("Memory")

    memories = fetch_memories()
    st.caption(f"{len(memories)} memories loaded")

    with st.expander("View memory", expanded=False):
        if memories:
            for mem in memories[:12]:
                summary = mem.get("summary") or mem.get("key") or "Untitled memory"
                st.markdown(f'<div class="memory-chip">#{mem["id"]} · {summary}</div>', unsafe_allow_html=True)
        else:
            st.caption("No saved memory yet.")

for msg in st.session_state.messages:
    role = msg["role"]
    label = "You" if role == "user" else "Sage"
    chip_class = "label-you" if role == "user" else "label-sage"

    with st.chat_message(role):
        st.markdown(f'<div class="role-chip {chip_class}">{label}</div>', unsafe_allow_html=True)
        st.markdown(msg["content"])

        if role == "assistant":
            used_memories = msg.get("used_memories", [])
            if used_memories:
                with st.expander("Memory used", expanded=False):
                    for mem in used_memories:
                        st.markdown(f"- {mem}")

prompt = st.chat_input("Talk to Sage...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown('<div class="role-chip label-you">You</div>', unsafe_allow_html=True)
        st.markdown(prompt)

    with st.chat_message("assistant"):
        st.markdown('<div class="role-chip label-sage">Sage</div>', unsafe_allow_html=True)
        placeholder = st.empty()

        try:
            payload = {
                "messages": st.session_state.messages,
                "mode": mode,
            }

            if cartridge != "auto":
                payload["cartridge"] = cartridge

            resp = requests.post(
                f"{BACKEND_URL}/chat",
                json=payload,
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()

            content = data["content"]
            provider = data.get("provider", "unknown")
            model = data.get("model", "unknown")
            used_cartridge = data.get("cartridge", "unknown")
            fallback = data.get("fallback", False)
            used_memories = data.get("used_memories", [])
            analysis = data.get("analysis")

            placeholder.markdown(content)

            badge_text = f"⚡ {provider} · {model} · {used_cartridge}"
            if analysis:
                task_type = analysis.get("task_type", "")
                if task_type:
                    badge_text += f" · {task_type}"
            if fallback:
                badge_text += " · fallback"

            st.markdown(f'<div class="status-badge">{badge_text}</div>', unsafe_allow_html=True)

            if used_memories:
                with st.expander("Memory used", expanded=False):
                    for mem in used_memories:
                        st.markdown(f"- {mem}")

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "used_memories": used_memories,
                }
            )

        except Exception as e:
            placeholder.empty()
            st.error(f"Request failed: {e}")